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


@require("editor")
async def generate(request: Request, user: dict):
    """Accept image upload, enqueue an image-to-3D job.

    The image is saved to media, and the job payload points at it.
    The worker calls triposr.image_to_3d() and stores the GLB in the library.
    For now (no separate worker for this), we do it inline (synchronous).
    """
    # Parse multipart form
    form = await request.form()
    uploaded = form.get("file") or form.get("image")
    if not uploaded:
        raise ApiError(422, "image file upload करें (field: file या image)")

    image_bytes = await uploaded.read()
    if len(image_bytes) > _MAX_IMAGE:
        raise ApiError(413, f"image बहुत बड़ी (max {_MAX_IMAGE // (1024 * 1024)} MB)")
    if len(image_bytes) < 100:
        raise ApiError(422, "image file खाली या corrupt")

    filename = getattr(uploaded, "filename", "input.png") or "input.png"
    content_type = getattr(uploaded, "content_type", "image/png") or "image/png"

    # Check TripoSR is available
    h = triposr.health()
    if h.get("status") != "ok":
        raise ApiError(503, f"TripoSR service उपलब्ध नहीं: {h.get('error', 'offline')}")

    # Save uploaded image to media
    ws = user["workspace_id"]
    media = Path(config.settings.media_root) / ws / "triposr"
    media.mkdir(parents=True, exist_ok=True)

    img_hash = hashlib.sha256(image_bytes).hexdigest()[:12]
    img_ext = filename.rsplit(".", 1)[-1] if "." in filename else "png"
    img_path = media / f"{img_hash}.{img_ext}"
    img_path.write_bytes(image_bytes)

    # Generate GLB synchronously (CPU mode, takes 1-3 min)
    glb_id = uuid.uuid4().hex[:16]
    glb_path = media / f"{glb_id}.glb"

    try:
        triposr.image_to_3d(image_bytes, filename, content_type, out=glb_path)
    except RuntimeError as e:
        raise ApiError(502, f"3D generation failed: {e}")

    # Create library item for the GLB
    item_id = db.new_id()
    now = db.now()
    name = str(form.get("name") or filename.rsplit(".", 1)[0] or "3D Model")[:120]
    item = {
        "id": item_id,
        "workspace_id": ws,
        "kind": "3d_model",
        "name": name,
        "ext": "glb",
        "mime": "model/gltf-binary",
        "size": glb_path.stat().st_size,
        "path": str(glb_path.relative_to(config.settings.media_root)),
        "meta": {"source": "triposr", "source_image": str(img_path.relative_to(config.settings.media_root)),
                 "source_hash": img_hash},
        "created_at": now,
        "updated_at": now,
        "user_id": user["id"],
    }
    with db.tx() as c:
        db.insert(c, "library", item)
        service.log(c, ws, "triposr.generate", user_id=user["id"], detail={"item_id": item_id, "name": name})

    return ok({"item": _view(item), "glb_size": glb_path.stat().st_size}, 201)


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
    Route("/triposr/jobs", jobs),
    Route("/triposr/jobs/{job_id}/cancel", cancel, methods=["POST"]),
]
