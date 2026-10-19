from __future__ import annotations

from pathlib import Path

from starlette.requests import Request
from starlette.responses import FileResponse
from starlette.routing import Route

from .. import db, service, storage
from ..engine import autocut
from ..engine.presets import caption_styles, platforms
from ..security import media_token, read_token
from .deps import ApiError, body, need, ok, own_project, require

STATUSES = ("uploading", "preparing", "transcribing", "cutting", "review_cuts", "rendering",
            "review_output", "approved", "failed")


@require("viewer")
async def list_projects(request: Request, user: dict):
    q = "SELECT * FROM projects WHERE workspace_id = ?"
    args: list = [user["workspace_id"]]
    status = request.query_params.get("status")
    if status in STATUSES:
        q += " AND status = ?"
        args.append(status)
    q += " ORDER BY updated_at DESC LIMIT 200"
    projects = db.rows(db.conn().execute(q, args))
    thumbs = {a["project_id"]: a["id"] for a in db.rows(db.conn().execute(
        "SELECT id, project_id FROM assets WHERE kind = 'thumb'"))}
    out = []
    for p in projects:
        p.pop("transcript", None)
        p.pop("edl", None)
        tid = thumbs.get(p["id"])
        p["thumb_url"] = f"/api/media/{tid}?t={media_token(tid)}" if tid else None
        out.append(p)
    return ok(out)


@require("editor")
async def create_project(request: Request, user: dict):
    data = await body(request)
    need(data, "title")
    p = {"id": db.new_id(), "workspace_id": user["workspace_id"], "created_by": user["id"],
         "title": data["title"].strip()[:200], "kind": data.get("kind", "talking_head"),
         "language": data.get("language") or "auto", "status": "uploading", "status_note": "upload का इंतज़ार",
         "meta": {}, "transcript": None, "edl": None,
         "settings": {"render": data.get("render", {}), "autocut": data.get("autocut", {})},
         "approved_by": None, "approved_at": None, "created_at": db.now(), "updated_at": db.now()}
    with db.tx() as c:
        db.insert(c, "projects", p)
        service.log(c, user["workspace_id"], "project.create", user_id=user["id"], project_id=p["id"],
                    detail={"title": p["title"]})
    return ok(service.project_view(p), 201)


def _with_urls(view: dict) -> dict:
    for a in view["assets"]:
        a["url"] = f"/api/media/{a['id']}?t={media_token(a['id'])}"
    return view


@require("viewer")
async def get_project(request: Request, user: dict):
    p = own_project(request, user)
    return ok(_with_urls(service.project_view(p)))


@require("editor")
async def update_project(request: Request, user: dict):
    p = own_project(request, user)
    data = await body(request)
    changes: dict = {}
    if data.get("title"):
        changes["title"] = data["title"].strip()[:200]
    if "settings" in data and isinstance(data["settings"], dict):
        changes["settings"] = {**p["settings"], **data["settings"]}
    if "edl" in data and isinstance(data["edl"], dict):
        # the dashboard toggles / trims cuts; keep stats honest
        edl = {**(p["edl"] or {}), **data["edl"]}
        cuts = [c for c in edl.get("cuts", []) if float(c["end"]) > float(c["start"])]
        removed = sum(float(c["end"]) - float(c["start"]) for c in cuts if c.get("enabled", True))
        edl["cuts"] = cuts
        edl["stats"] = {**edl.get("stats", {}), "cuts": sum(1 for c in cuts if c.get("enabled", True)),
                        "removed_seconds": round(removed, 2),
                        "final_seconds": round(float(edl["duration"]) - removed, 2)}
        changes["edl"] = edl
    if "transcript" in data and isinstance(data["transcript"], dict):
        changes["transcript"] = data["transcript"]
    if changes:
        changes["updated_at"] = db.now()
        with db.tx() as c:
            db.update(c, "projects", p["id"], changes)
            service.log(c, user["workspace_id"], "project.update", user_id=user["id"],
                        project_id=p["id"], detail={"fields": list(changes)})
    return ok(_with_urls(service.project_view(db.get("projects", p["id"]))))


@require("editor")
async def delete_project(request: Request, user: dict):
    p = own_project(request, user)
    if p["status"] == "approved" and user["role"] != "admin":
        raise ApiError(403, "approved project सिर्फ़ admin हटा सकता है")
    with db.tx() as c:
        service.delete_project(c, p)
        service.log(c, user["workspace_id"], "project.delete", user_id=user["id"], project_id=p["id"],
                    detail={"title": p["title"]})
    return ok()


@require("editor")
async def recut(request: Request, user: dict):
    """Rebuild the cut list with new sensitivity (after the transcript exists)."""
    p = own_project(request, user)
    if not p.get("transcript"):
        raise ApiError(400, "transcript अभी नहीं बना")
    data = await body(request)
    opts = {**p["settings"].get("autocut", {}), **(data.get("options") or {})}
    with db.tx() as c:
        db.update(c, "projects", p["id"], {"settings": {**p["settings"], "autocut": opts}})
        service.set_status(c, p["id"], "cutting", "कट दोबारा ढूँढे जा रहे हैं")
        job = service.queue.enqueue(c, p["id"], "autocut", {"options": opts})
    return ok({"job": job})


@require("editor")
async def render(request: Request, user: dict):
    p = own_project(request, user)
    if p["status"] in ("uploading", "preparing", "transcribing", "cutting"):
        raise ApiError(400, "पहले transcript और कट पूरे होने दें")
    data = await body(request)
    try:
        with db.tx() as c:
            jobs = service.request_render(c, p, data)
            service.log(c, user["workspace_id"], "project.render", user_id=user["id"],
                        project_id=p["id"], detail={"presets": [j["payload"]["preset"] for j in jobs]})
    except ValueError as e:
        raise ApiError(422, str(e))
    return ok({"jobs": jobs})


@require("admin")
async def approve(request: Request, user: dict):
    p = own_project(request, user)
    if p["status"] != "review_output":
        raise ApiError(400, "पहले render पूरा होने दें")
    with db.tx() as c:
        db.update(c, "projects", p["id"], {"status": "approved", "status_note": "मंज़ूर",
                                           "approved_by": user["id"], "approved_at": db.now(),
                                           "updated_at": db.now()})
        service.log(c, user["workspace_id"], "project.approve", user_id=user["id"], project_id=p["id"])
    return ok(_with_urls(service.project_view(db.get("projects", p["id"]))))


@require("editor")
async def reopen(request: Request, user: dict):
    p = own_project(request, user)
    if not p.get("edl"):
        raise ApiError(400, "अभी कट नहीं बने")
    with db.tx() as c:
        service.set_status(c, p["id"], "review_cuts", "दोबारा review")
    return ok()


@require("viewer")
async def preview_keep(request: Request, user: dict):
    """The kept segments after cuts — the dashboard uses this for a scrub preview."""
    p = own_project(request, user)
    if not p.get("edl"):
        return ok({"keep": []})
    return ok({"keep": autocut.keep_segments(p["edl"])})


async def media(request: Request):
    """Serve a file. Auth is the short-lived token in ?t= (works in <video src>)."""
    aid = request.path_params["asset_id"]
    tok = request.query_params.get("t")
    data = read_token(tok, kind="media") if tok else None
    if not data or data.get("sub") != aid:
        raise ApiError(401, "media link expired")
    a = db.get("assets", aid)
    if not a or a["archived"]:
        raise ApiError(404, "file not found")
    path = storage.abs_path(a["path"])
    if not path.exists():
        raise ApiError(404, "file missing on disk")
    download = request.query_params.get("download")
    name = Path(a["path"]).name
    return FileResponse(path, media_type=a["mime"] or "application/octet-stream",
                        filename=name if download else None)


@require("viewer")
async def presets(request: Request, user: dict):
    fonts = ["Noto Sans Devanagari", "Poppins", "Baloo 2", "Mukta", "Hind"]
    return ok({"platforms": list(platforms().values()), "caption_styles": list(caption_styles().values()),
               "fonts": fonts,
               "render_defaults": service.DEFAULT_RENDER, "autocut_defaults": autocut.DEFAULTS})


routes = [
    Route("/projects", list_projects),
    Route("/projects", create_project, methods=["POST"]),
    Route("/projects/{project_id}", get_project),
    Route("/projects/{project_id}", update_project, methods=["PATCH"]),
    Route("/projects/{project_id}", delete_project, methods=["DELETE"]),
    Route("/projects/{project_id}/recut", recut, methods=["POST"]),
    Route("/projects/{project_id}/render", render, methods=["POST"]),
    Route("/projects/{project_id}/approve", approve, methods=["POST"]),
    Route("/projects/{project_id}/reopen", reopen, methods=["POST"]),
    Route("/projects/{project_id}/keep", preview_keep),
    Route("/media/{asset_id}", media),
    Route("/presets", presets),
]
