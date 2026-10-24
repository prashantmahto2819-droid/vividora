"""Video compressor (standalone tool): shrink any video to a target size for WhatsApp / email /
social sharing. Sources: a library upload (POST /library/upload?kind=broll) or a project's render.
Jobs run on the CPU worker (kind "compress") under the workspace's hidden tools project; the
result lands in the library as a new "broll" item — the original is never touched.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.routing import Route

from .. import db, service
from ..engine import compress as cmp
from .deps import ApiError, body, ok, require
from .library import _view


def _rows(workspace_id: str) -> list[dict]:
    cn = db.conn()
    tp = db.row(cn.execute("SELECT id FROM projects WHERE workspace_id = ? AND kind = 'tools' LIMIT 1", (workspace_id,)).fetchone())
    if not tp:
        return []
    jobs = db.rows(cn.execute("SELECT * FROM jobs WHERE project_id = ? AND kind = 'compress' ORDER BY created_at DESC LIMIT 40", (tp["id"],)))
    out = []
    ahead = {j["id"]: i for i, j in enumerate(db.rows(cn.execute(
        "SELECT id FROM jobs WHERE status = 'queued' AND kind IN ('render','montage','matte','dub','compress') ORDER BY created_at")))}
    for j in jobs:
        res = j.get("result") or {}
        item = db.get("library", res["library_id"]) if res.get("library_id") else None
        out.append({"id": j["id"], "status": j["status"], "progress": j.get("progress"), "message": j.get("message"),
                    "error": j.get("error"), "created_at": j["created_at"], "finished_at": j.get("finished_at"),
                    "payload": {k: v for k, v in (j.get("payload") or {}).items() if k != "user_id"},
                    "result": {k: v for k, v in res.items() if k != "files"},
                    "queue_position": (ahead.get(j["id"], 0) + 1) if j["status"] == "queued" else None,
                    "item": _view(item) if item else None})
    return out


@require("viewer")
async def list_jobs(request: Request, user: dict):
    return ok({"jobs": _rows(user["workspace_id"]), "presets": {k: {"label": v["label"], "target_mb": v["target_mb"], "max_h": v["max_h"], "fps": v["fps"]}
                                                                for k, v in cmp.PRESETS.items()}})


@require("editor")
async def start(request: Request, user: dict):
    data = await body(request)
    try:
        with db.tx() as c:
            job = service.request_compress(c, user["workspace_id"], user["id"],
                                           {"library_id": data.get("library_id"), "asset_id": data.get("asset_id")}, data)
    except ValueError as e:
        raise ApiError(422, str(e))
    return ok({"job": job}, 201)


@require("editor")
async def cancel(request: Request, user: dict):
    job = db.get("jobs", request.path_params["job_id"])
    pr = db.get("projects", job["project_id"]) if job else None
    if not job or not pr or pr["workspace_id"] != user["workspace_id"] or job["kind"] != "compress":
        raise ApiError(404, "job not found")
    with db.tx() as c:
        if job["status"] in ("queued", "running"):
            db.update(c, "jobs", job["id"], {"status": "cancelled", "finished_at": db.now(), "message": "रद्द"})
    return ok()


@require("viewer")
async def sources(request: Request, user: dict):
    """Renders of this workspace's projects that can be compressed without re-uploading."""
    rows = db.rows(db.conn().execute(
        "SELECT a.id, a.label, a.size, a.meta, p.title FROM assets a JOIN projects p ON p.id = a.project_id "
        "WHERE p.workspace_id = ? AND a.kind = 'render' AND a.archived = 0 ORDER BY a.created_at DESC LIMIT 60", (user["workspace_id"],)))
    return ok([{"id": r["id"], "title": r["title"], "label": r["label"], "size": r["size"],
                "duration": (r.get("meta") or {}).get("duration")} for r in rows])


routes = [
    Route("/compress", list_jobs),
    Route("/compress", start, methods=["POST"]),
    Route("/compress/sources", sources),
    Route("/compress/{job_id}/cancel", cancel, methods=["POST"]),
]
