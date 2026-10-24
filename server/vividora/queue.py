"""A small, durable job queue in SQLite.

Workers (the CPU worker in Docker, the GPU worker on Windows) claim jobs over
HTTP, send heartbeats while working, and report a result or an error. A job
whose worker disappears (PC asleep, crash) is handed out again after
JOB_STALE_MINUTES, up to MAX_JOB_ATTEMPTS times.
"""

from __future__ import annotations

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


HEAVY = ('render', 'montage', 'matte', 'dub', 'compress')


def claim(c, kinds: list[str], worker: str) -> dict | None:
    requeue_stale(c)
    marks = ", ".join("?" for _ in kinds)
    # quick pipeline steps (prepare, autocut, Shorts plan, publish…) first: a new upload should not
    # wait behind a queue of long renders before its transcript / cuts / plan are made
    cands = db.rows(c.execute(
        f"SELECT j.*, p.workspace_id AS ws FROM jobs j JOIN projects p ON p.id = j.project_id "
        f"WHERE j.status = 'queued' AND j.kind IN ({marks}) "
        "AND (j.run_after IS NULL OR j.run_after <= ?) "
        # a one-line re-transcribe is seconds of work the creator waits for in the editor: first;
        # then quick pipeline steps before long renders
        "ORDER BY (j.kind = 'transcribe' AND json_extract(j.payload, '$.range') IS NOT NULL) DESC, "
        "CASE WHEN j.kind IN ('render','montage','matte','dub','compress') THEN 1 ELSE 0 END, j.created_at LIMIT 200",
        [*kinds, db.now()]))
    job = _pick_fair(c, cands)
    if job is None:
        return None
    n = c.execute(
        "UPDATE jobs SET status='running', worker=?, attempts=attempts+1, started_at=?, "
        "heartbeat_at=?, progress=0, message='शुरू', error=NULL WHERE id=? AND status='queued'",
        (worker, db.now(), db.now(), job["id"])).rowcount
    if n != 1:
        return None
    return db.row(c.execute("SELECT * FROM jobs WHERE id = ?", (job["id"],)).fetchone())


def _pick_fair(c, cands: list[dict]) -> dict | None:
    """SAAS_MODE: one workspace must not hold the whole queue. Skip workspaces at their plan's
    concurrent-job limit, then round-robin by "least recently served" workspace. Otherwise FIFO."""
    from . import saas
    if not cands:
        return None
    if not saas.enabled():
        return cands[0]
    running = {r[0]: r[1] for r in c.execute(
        "SELECT p.workspace_id, COUNT(*) FROM jobs j JOIN projects p ON p.id = j.project_id "
        "WHERE j.status = 'running' GROUP BY p.workspace_id").fetchall()}
    last = {r[0]: r[1] or "" for r in c.execute(
        "SELECT p.workspace_id, MAX(j.started_at) FROM jobs j JOIN projects p ON p.id = j.project_id "
        "WHERE j.started_at IS NOT NULL GROUP BY p.workspace_id").fetchall()}
    ok = [j for j in cands if running.get(j["ws"], 0) < saas.concurrent_limit(c, j["ws"])]
    if not ok:
        return None
    # keep the priority classes (quick before heavy) and, within the first class, serve the workspace that
    # waited longest since its last job started
    first_heavy = ok[0]["kind"] in HEAVY
    cls = [j for j in ok if (j["kind"] in HEAVY) == first_heavy]
    return min(cls, key=lambda j: (last.get(j["ws"], ""), j["created_at"]))


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
