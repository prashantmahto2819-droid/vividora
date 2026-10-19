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


def enqueue(c, project_id: str, kind: str, payload: dict | None = None) -> dict:
    job = {"id": db.new_id(), "project_id": project_id, "kind": kind, "status": "queued",
           "payload": payload or {}, "created_at": db.now()}
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


def claim(c, kinds: list[str], worker: str) -> dict | None:
    requeue_stale(c)
    marks = ", ".join("?" for _ in kinds)
    job = db.row(c.execute(
        f"SELECT * FROM jobs WHERE status = 'queued' AND kind IN ({marks}) "
        "ORDER BY created_at LIMIT 1", kinds).fetchone())
    if job is None:
        return None
    n = c.execute(
        "UPDATE jobs SET status='running', worker=?, attempts=attempts+1, started_at=?, "
        "heartbeat_at=?, progress=0, message='शुरू', error=NULL WHERE id=? AND status='queued'",
        (worker, db.now(), db.now(), job["id"])).rowcount
    if n != 1:
        return None
    return db.row(c.execute("SELECT * FROM jobs WHERE id = ?", (job["id"],)).fetchone())


def heartbeat(c, job_id: str, progress: int | None, message: str | None) -> None:
    data: dict = {"heartbeat_at": db.now()}
    if progress is not None:
        data["progress"] = max(0, min(100, int(progress)))
    if message:
        data["message"] = message[:250]
    db.update(c, "jobs", job_id, data)
