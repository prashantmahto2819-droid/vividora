"""TripoSR API — Image-to-3D GLB generation via self-hosted TripoSR.

GET  /triposr/health             service health check
POST /triposr/generate           upload image → get GLB 3D model → library item
GET  /triposr/jobs               this workspace's image-to-3D jobs
POST /triposr/jobs/{id}/cancel   cancel a running job
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from pathlib import Path

from starlette.requests import Request
from starlette.responses import FileResponse
from starlette.routing import Route

from .. import config, db, queue, service
from ..engine import triposr
from .deps import ApiError, body, ok, require
from .library import _view

log = logging.getLogger("vividora.api.triposr")

KIND = "image_to_3d"
_MAX_IMAGE = 10 * 1024 * 1024  # 10 MB


async def health_check(request: Request):
    """Public health check — no auth needed."""
    return ok(triposr.health())


_JOBS: dict[str, dict] = {}  # in-memory state of image→3D runs (a run takes 1–3 min on CPU; the browser polls)


def _run(job_id: str, ws: str, user_id: str, image_bytes: bytes, filename: str, content_type: str, name: str):
    import tempfile
    st = _JOBS[job_id]
    try:
        with tempfile.TemporaryDirectory(prefix="triposr_") as td:
            glb = Path(td) / f"{name[:60] or 'model'}.glb"
            triposr.image_to_3d(image_bytes, filename, content_type, out=glb)
            from .library import _add_file
            item = _add_file(ws, user_id, "3d_model", glb, name=name, tags="3d,glb", source="triposr",
                             license="", analyse=False)
        with db.tx() as c:
            service.log(c, ws, "triposr.generate", user_id=user_id, detail={"item_id": item["id"], "name": name})
        st.update(status="done", item=_view(item), finished=time.time())
    except Exception as e:  # noqa: BLE001 — reported to the browser
        log.warning("image→3D failed: %s", e)
        st.update(status="failed", error=str(e)[:300], finished=time.time())


@require("editor")
async def generate(request: Request, user: dict):
    """POST multipart (field: file) → 202 {job_id}. The GLB is made in the background and saved in the
    library (kind 3d_model); poll GET /triposr/job/{job_id}."""
    import threading
    form = await request.form()
    uploaded = form.get("file") or form.get("image")
    if not uploaded or not hasattr(uploaded, "read"):
        raise ApiError(422, "image file upload करें (field: file या image)")
    image_bytes = await uploaded.read()
    if len(image_bytes) > _MAX_IMAGE:
        raise ApiError(413, f"image बहुत बड़ी (max {_MAX_IMAGE // (1024 * 1024)} MB)")
    if len(image_bytes) < 100:
        raise ApiError(422, "image file खाली या corrupt")
    filename = getattr(uploaded, "filename", "input.png") or "input.png"
    content_type = getattr(uploaded, "content_type", "image/png") or "image/png"
    h = triposr.health()
    if h.get("status") != "ok":
        raise ApiError(503, f"TripoSR service उपलब्ध नहीं: {h.get('error', 'offline')}")
    if sum(1 for j in _JOBS.values() if j["status"] == "running") >= 1:
        raise ApiError(429, "एक 3D model अभी बन रहा है — ख़त्म होने दें")
    for k in [k for k, j in _JOBS.items() if j.get("finished") and time.time() - j["finished"] > 3600]:
        _JOBS.pop(k, None)
    name = str(form.get("name") or filename.rsplit(".", 1)[0] or "3D Model")[:120]
    job_id = uuid.uuid4().hex[:16]
    _JOBS[job_id] = {"status": "running", "ws": user["workspace_id"], "started": time.time()}
    threading.Thread(target=_run, args=(job_id, user["workspace_id"], user["id"], image_bytes, filename, content_type, name),
                     daemon=True).start()
    return ok({"job_id": job_id}, 202)


@require("viewer")
async def job_status(request: Request, user: dict):
    st = _JOBS.get(request.path_params["job_id"])
    if not st or st["ws"] != user["workspace_id"]:
        raise ApiError(404, "job नहीं मिला (server restart हुआ हो तो Library देखें)")
    return ok({"status": st["status"], "error": st.get("error"), "item": st.get("item"),
               "seconds": int(time.time() - st["started"])})


@require("viewer")
async def models(request: Request, user: dict):
    """The workspace's generated 3D models (newest first)."""
    rows = db.rows(db.conn().execute("SELECT * FROM library WHERE workspace_id = ? AND kind = '3d_model' ORDER BY created_at DESC LIMIT 60",
                                     (user["workspace_id"],)))
    return ok({"models": [_view(r) for r in rows]})


@require("viewer")
async def jobs(request: Request, user: dict):
    """List image-to-3D jobs for this workspace."""
    cn = db.conn()
    ws = user["workspace_id"]
    tp = db.row(cn.execute("SELECT id FROM projects WHERE workspace_id = ? AND kind = 'tools' LIMIT 1", (ws,)).fetchone())
    if not tp:
        return ok({"jobs": []})
    rows = db.rows(cn.execute(
        "SELECT * FROM jobs WHERE project_id = ? AND kind = ? ORDER BY created_at DESC LIMIT 20",
        (tp["id"], KIND)))
    out = []
    for j in rows:
        res = j.get("result") or {}
        item = db.get("library", res["library_id"]) if res.get("library_id") else None
        out.append({
            "id": j["id"], "kind": j["kind"], "status": j["status"],
            "progress": j.get("progress"), "error": j.get("error"),
            "created_at": j["created_at"], "finished_at": j.get("finished_at"),
            "result": res, "item": _view(item) if item else None,
        })
    return ok({"jobs": out})


@require("editor")
async def cancel(request: Request, user: dict):
    job = db.get("jobs", request.path_params["job_id"])
    pr = db.get("projects", job["project_id"]) if job else None
    if not job or not pr or pr["workspace_id"] != user["workspace_id"] or job["kind"] != KIND:
        raise ApiError(404, "job not found")
    with db.tx() as c:
        if job["status"] in ("queued", "running"):
            db.update(c, "jobs", job["id"], {"status": "cancelled", "finished_at": db.now(), "message": "रद्द"})
    return ok()


routes = [
    Route("/triposr/health", health_check),
    Route("/triposr/generate", generate, methods=["POST"]),
    Route("/triposr/job/{job_id}", job_status),
    Route("/triposr/models", models),
    Route("/triposr/jobs", jobs),
    Route("/triposr/jobs/{job_id}/cancel", cancel, methods=["POST"]),
]
