"""A small, durable job queue in SQLite — multi-worker, priority-aware.

Workers (the CPU worker in Docker, the GPU worker on Windows) claim jobs over
HTTP, send heartbeats while working, and report a result or an error. A job
whose worker disappears (PC asleep, crash) is handed out again after
JOB_STALE_MINUTES, up to MAX_JOB_ATTEMPTS times.

Priority tiers (highest → lowest):
  URGENT  — re-transcribe with range: seconds of work, creator is waiting
  FAST    — pipeline steps that should never wait behind renders
  HEAVY   — CPU-intensive: render, montage, matte, dub, compress

Concurrency limits (tuned for HP Z440 / 12 cores / 64 GB with 4 users):
  MAX_CONCURRENT_HEAVY  — caps simultaneous heavy jobs so quick pipeline work flows
  MAX_CONCURRENT_TOTAL  — absolute cap on all running jobs

Per-user fairness: even in self-hosted mode (no SaaS), the queue round-robins
between users so one person's batch of renders doesn't starve others.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from . import db
from .config import settings


def enqueue(c, project_id: str, kind: str, payload: dict | None = None, run_after: str | None = None) -> dict:
    """run_after (UTC ISO): the job waits in the queue until then (scheduled Instagram posts)."""
    job = {"id": db.new_id(), "project_id": project_id, "kind": kind, "status": "queued",
           "payload": payload or {}, "created_at": db.now()}
    if run_after:
        job["run_after"] = run_after
    db.insert(c, "jobs", job)
    return job


def requeue_stale(c) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=settings.job_stale_minutes)).isoformat(
        timespec="seconds")
    stale = db.rows(c.execute(
        "SELECT * FROM jobs WHERE status = 'running' AND heartbeat_at < ?", (cutoff,)))
    for job in stale:
        if job["attempts"] >= settings.max_job_attempts:
            db.update(c, "jobs", job["id"], {
                "status": "failed", "finished_at": db.now(),
                "error": ((job["error"] or "") + "\nworker बार-बार बीच में रुक गया").strip()})
        else:
            db.update(c, "jobs", job["id"], {"status": "queued", "worker": None,
                                             "message": "worker चुप हो गया — दोबारा queue में"})
    return len(stale)


def touch_worker(c, name: str, kinds: list[str], info: dict | None = None) -> None:
    if c.execute("SELECT 1 FROM workers WHERE name = ?", (name,)).fetchone():
        data = {"kinds": kinds, "last_seen_at": db.now()}
        if info:
            data["info"] = info
        db.update(c, "workers", name, data, key="name")
    else:
        db.insert(c, "workers", {"name": name, "kinds": kinds, "info": info or {},
                                 "last_seen_at": db.now()})


# ── Priority tiers ──────────────────────────────────────────────────────────

HEAVY = ('render', 'montage', 'matte', 'dub', 'compress')
FAST  = ('prepare', 'autocut', 'shorts_plan', 'publish', 'thumbnail', 'beat_plan',
         'trendtpl', 'retention')


def _priority(kind: str, payload: dict | None = None) -> int:
    """0 = urgent (run first), 1 = fast pipeline, 2 = heavy."""
    # A re-transcribe with a range is seconds of work and the creator is waiting in the editor
    if kind == 'transcribe' and payload and payload.get('range'):
        return 0
    if kind in HEAVY:
        return 2
    return 1  # everything else is fast pipeline


# ── Concurrency helpers ─────────────────────────────────────────────────────

def _running_counts(c) -> dict:
    """Returns {'total': N, 'heavy': N, 'by_user': {user_id: N}}."""
    rows = c.execute(
        "SELECT j.kind, p.user_id FROM jobs j "
        "JOIN projects p ON p.id = j.project_id "
        "WHERE j.status = 'running'").fetchall()
    total = len(rows)
    heavy = sum(1 for kind, _ in rows if kind in HEAVY)
    by_user: dict[str, int] = {}
    for _, uid in rows:
        by_user[uid] = by_user.get(uid, 0) + 1
    return {"total": total, "heavy": heavy, "by_user": by_user}


# ── Claim ───────────────────────────────────────────────────────────────────

def claim(c, kinds: list[str], worker: str) -> dict | None:
    requeue_stale(c)

    counts = _running_counts(c)

    # Hard cap: don't overload the machine
    if counts["total"] >= settings.max_concurrent_total:
        return None

    marks = ", ".join("?" for _ in kinds)
    now = db.now()

    # Fetch candidates ordered by priority tier, then creation time
    cands = db.rows(c.execute(
        f"SELECT j.*, p.workspace_id AS ws, p.user_id AS uid FROM jobs j "
        f"JOIN projects p ON p.id = j.project_id "
        f"WHERE j.status = 'queued' AND j.kind IN ({marks}) "
        "AND (j.run_after IS NULL OR j.run_after <= ?) "
        "ORDER BY "
        # tier 0: urgent (re-transcribe with range)
        "(j.kind = 'transcribe' AND json_extract(j.payload, '$.range') IS NOT NULL) DESC, "
        # tier 1: fast pipeline steps before heavy
        "CASE WHEN j.kind IN ('render','montage','matte','dub','compress') THEN 2 ELSE 1 END, "
        "j.created_at "
        "LIMIT 200",
        [*kinds, now]))

    # If heavy jobs are at capacity, filter them out
    if counts["heavy"] >= settings.max_concurrent_heavy:
        cands = [j for j in cands if j["kind"] not in HEAVY]

    job = _pick_fair(c, cands, counts)
    if job is None:
        return None
    # ---- sysguard: skip heavy jobs when resources are low ----
    from . import sysguard
    reason = sysguard.pre_job_check(c, job["kind"])
    if reason:
        import logging
        logging.getLogger("vividora.queue").info("heavy job %s skipped: %s", job["id"], reason)
        # try to find a quick (non-heavy) job instead
        quick = [j for j in cands if j["kind"] not in HEAVY]
        if quick:
            job = quick[0]
        else:
            return None  # all candidates are heavy and resources are low

    n = c.execute(
        "UPDATE jobs SET status='running', worker=?, attempts=attempts+1, started_at=?, "
        "heartbeat_at=?, progress=0, message='शुरू', error=NULL WHERE id=? AND status='queued'",
        (worker, now, now, job["id"])).rowcount
    if n != 1:
        return None
    return db.row(c.execute("SELECT * FROM jobs WHERE id = ?", (job["id"],)).fetchone())


def _pick_fair(c, cands: list[dict], counts: dict) -> dict | None:
    """Fair scheduling across users AND workspaces.

    SaaS mode: workspace concurrent-job limits + workspace round-robin.
    Self-hosted: per-user round-robin + per-workspace heavy limits so one
    person's batch of renders doesn't starve the other 3 users on the Z440.
    """
    from . import saas
    if not cands:
        return None

    # ── SaaS mode: workspace-level limits + round-robin ─────────────────
    if saas.enabled():
        running_ws = {r[0]: r[1] for r in c.execute(
            "SELECT p.workspace_id, COUNT(*) FROM jobs j JOIN projects p ON p.id = j.project_id "
            "WHERE j.status = 'running' GROUP BY p.workspace_id").fetchall()}
        last_ws = {r[0]: r[1] or "" for r in c.execute(
            "SELECT p.workspace_id, MAX(j.started_at) FROM jobs j JOIN projects p ON p.id = j.project_id "
            "WHERE j.started_at IS NOT NULL GROUP BY p.workspace_id").fetchall()}
        ok = [j for j in cands if running_ws.get(j["ws"], 0) < saas.concurrent_limit(c, j["ws"])]
        if not ok:
            return None
        first_pri = _priority(ok[0]["kind"], ok[0].get("payload"))
        cls = [j for j in ok if _priority(j["kind"], j.get("payload")) == first_pri]
        return min(cls, key=lambda j: (last_ws.get(j["ws"], ""), j["created_at"]))

    # ── Self-hosted: per-user round-robin ───────────────────────────────
    # Within the highest available priority tier, pick the user who waited longest
    last_user = {r[0]: r[1] or "" for r in c.execute(
        "SELECT p.user_id, MAX(j.started_at) FROM jobs j JOIN projects p ON p.id = j.project_id "
        "WHERE j.started_at IS NOT NULL GROUP BY p.user_id").fetchall()}

    first_pri = _priority(cands[0]["kind"], cands[0].get("payload"))
    cls = [j for j in cands if _priority(j["kind"], j.get("payload")) == first_pri]

    # Serve the user whose last job started the earliest (round-robin fairness)
    return min(cls, key=lambda j: (last_user.get(j.get("uid", ""), ""), j["created_at"]))


# ── Heartbeat ───────────────────────────────────────────────────────────────

def heartbeat(c, job_id: str, progress: int | None, message: str | None) -> None:
    data: dict = {"heartbeat_at": db.now()}
    if progress is not None:
        data["progress"] = max(0, min(100, int(progress)))
    if message:
        data["message"] = message[:250]
    db.update(c, "jobs", job_id, data)
    # a busy worker is alive: keep it "online" on the status page while it works
    row = c.execute("SELECT worker FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row and row[0]:
        c.execute("UPDATE workers SET last_seen_at = ? WHERE name = ?", (db.now(), row[0]))


# ── Queue status (for dashboard) ────────────────────────────────────────────

def queue_status(c) -> dict:
    """Snapshot of queue health: queued/running counts by kind and user."""
    queued = c.execute(
        "SELECT j.kind, COUNT(*) FROM jobs j WHERE j.status = 'queued' "
        "AND (j.run_after IS NULL OR j.run_after <= ?) GROUP BY j.kind", (db.now(),)).fetchall()
    running = c.execute(
        "SELECT j.kind, j.worker, p.user_id, j.progress, j.message "
        "FROM jobs j JOIN projects p ON p.id = j.project_id "
        "WHERE j.status = 'running' ORDER BY j.started_at").fetchall()

    return {
        "queued": {r[0]: r[1] for r in queued},
        "queued_total": sum(r[1] for r in queued),
        "running": [{"kind": r[0], "worker": r[1], "user_id": r[2],
                     "progress": r[3], "message": r[4]} for r in running],
        "running_total": len(running),
        "running_heavy": sum(1 for r in running if r[0] in HEAVY),
        "limits": {
            "max_heavy": settings.max_concurrent_heavy,
            "max_total": settings.max_concurrent_total,
        },
    }
