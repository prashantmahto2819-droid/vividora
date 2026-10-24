"""Endpoints the CPU worker (Docker) and GPU worker (Windows) talk to.

Workers never touch the database; they claim a job, download what they need
through /worker/files, upload results through /worker/jobs/{id}/upload and
report done or failed.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import FileResponse
from starlette.routing import Route

from .. import db, queue, service, storage
from .deps import ApiError, body, ok, require, require_worker


@require_worker
async def claim(request: Request):
    data = await body(request)
    kinds = data.get("kinds") or []
    name = (data.get("worker") or "worker")[:120]
    if not isinstance(kinds, list) or not kinds:
        raise ApiError(422, "kinds required")
    with db.tx() as c:
        queue.touch_worker(c, name, kinds, data.get("info"))
        job = queue.claim(c, kinds, name)
    if job is None:
        return ok({"job": None})
    project = db.get("projects", job["project_id"])
    assets = db.rows(db.conn().execute("SELECT id, kind, label, path, mime, meta FROM assets "
                                       "WHERE project_id = ? AND archived = 0", (project["id"],)))
    from .. import saas
    return ok({"job": job, "project": {k: project[k] for k in
                                       ("id", "workspace_id", "title", "language", "meta", "transcript",
                                        "edl", "settings")},
               "assets": assets, "quota": {"ai_credits": saas.ai_credits_left(project["workspace_id"])}})


def _job(request: Request) -> dict:
    job = db.get("jobs", request.path_params["job_id"])
    if not job:
        raise ApiError(404, "job not found")
    return job


def job_workspace(request: Request) -> str | None:
    """The workspace of the job a worker is working on (X-Job header, set by worker/client.py).
    Old workers without the header are not scoped (None) — a warning is logged once per worker."""
    jid = request.headers.get("x-job")
    if not jid:
        return None
    job = db.get("jobs", jid)
    if not job:
        raise ApiError(403, "job not found")
    p = db.get("projects", job["project_id"])
    return p["workspace_id"] if p else None


@require_worker
async def heartbeat(request: Request):
    job = _job(request)
    data = await body(request)
    with db.tx() as c:
        queue.heartbeat(c, job["id"], data.get("progress"), data.get("message"))
    cancelled = db.get("jobs", job["id"])["status"] == "cancelled"
    return ok({"cancelled": cancelled})


@require_worker
async def done(request: Request):
    job = _job(request)
    if job["status"] == "cancelled":
        return ok({"cancelled": True})  # the creator stopped it meanwhile — the result is thrown away
    if job["status"] != "running":
        raise ApiError(409, f"job is {job['status']}")
    data = await body(request)
    result = data.get("result") or {}
    with db.tx() as c:
        db.update(c, "jobs", job["id"], {"status": "done", "result": result, "progress": 100,
                                         "message": "पूरा", "finished_at": db.now()})
        if result.get("llm_calls") and job["kind"] != "render":  # render counts its own calls in after_job
            from .. import saas
            p = db.get("projects", job["project_id"])
            if p:
                saas.add_usage(c, p["workspace_id"], ai_calls=int(result["llm_calls"]))
        service.after_job(c, job, result)
    return ok()


@require_worker
async def failed(request: Request):
    job = _job(request)
    data = await body(request)
    err = str(data.get("error") or "unknown error")
    if job["status"] == "cancelled":
        return ok({"cancelled": True})  # a cancelled job must not come back as "queued"
    with db.tx() as c:
        if job["attempts"] < service.settings.max_job_attempts and data.get("retry", True):
            db.update(c, "jobs", job["id"], {"status": "queued", "worker": None, "error": err[:4000],
                                             "message": f"कोशिश {job['attempts']} असफल — दोबारा"})
        else:
            service.fail_job(c, job, err)
    return ok()


@require_worker
async def file(request: Request):
    """Download one of the project's files (raw, audio, …) by asset id."""
    a = db.get("assets", request.path_params["asset_id"])
    if not a:
        raise ApiError(404, "asset not found")
    ws = job_workspace(request)
    if ws is not None:
        p = db.get("projects", a["project_id"])
        if not p or p["workspace_id"] != ws:
            raise ApiError(404, "asset not found")
    path = storage.abs_path(a["path"])
    if not path.exists():
        raise ApiError(404, "file missing")
    return FileResponse(path, media_type=a["mime"] or "application/octet-stream")


@require_worker
async def upload(request: Request):
    """Store a result file for a job. Query: kind, name, label (optional)."""
    job = _job(request)
    project = db.get("projects", job["project_id"])
    kind = request.query_params.get("kind", "work")
    name = storage.safe_name(request.query_params.get("name", f"{kind}.bin"))
    sub = "out" if kind in ("render", "subtitle") else "work"
    rel = str(storage.project_dir(project["workspace_id"], project["id"]) / sub / name)
    path = storage.ensure_parent(rel)
    with path.open("wb") as f:
        async for part in request.stream():
            f.write(part)
    return ok({"path": rel, "size": path.stat().st_size})


@require("viewer")
async def workers_status(request: Request, user: dict):
    ws = db.rows(db.conn().execute("SELECT * FROM workers ORDER BY last_seen_at DESC"))
    q = db.conn().execute("SELECT status, COUNT(*) FROM jobs GROUP BY status").fetchall()
    from .. import archive
    return ok({"workers": ws, "jobs": {r[0]: r[1] for r in q}, "disk": storage.disk_usage(),
               "archive": {"backend": archive.backend(), "remote": archive.REMOTE or None, "after_days": service.settings.archive_after_days}})


@require("viewer")
async def activity(request: Request, user: dict):
    rows = db.rows(db.conn().execute(
        "SELECT a.*, u.name AS user_name FROM activity a LEFT JOIN users u ON u.id = a.user_id "
        "WHERE a.workspace_id = ? ORDER BY a.id DESC LIMIT 100", (user["workspace_id"],)))
    return ok(rows)


routes = [
    Route("/worker/claim", claim, methods=["POST"]),
    Route("/worker/jobs/{job_id}/heartbeat", heartbeat, methods=["POST"]),
    Route("/worker/jobs/{job_id}/done", done, methods=["POST"]),
    Route("/worker/jobs/{job_id}/failed", failed, methods=["POST"]),
    Route("/worker/jobs/{job_id}/upload", upload, methods=["PUT"]),
    Route("/worker/files/{asset_id}", file),
    Route("/status", workers_status),
    Route("/activity", activity),
]
