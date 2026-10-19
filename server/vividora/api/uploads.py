"""Resumable uploads: the browser sends the file in chunks; a dropped
connection resumes from the last byte the server has."""

from __future__ import annotations

from starlette.requests import Request
from starlette.routing import Route

from .. import db, service, storage
from .deps import ApiError, body, need, ok, own_project, require

MAX_UPLOAD = 20 * 1024 ** 3  # 20 GB
ALLOWED_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".mts", ".3gp", ".wav", ".mp3", ".m4a"}


@require("editor")
async def start(request: Request, user: dict):
    p = own_project(request, user)
    data = await body(request)
    need(data, "filename", "size")
    size = int(data["size"])
    if size <= 0 or size > MAX_UPLOAD:
        raise ApiError(422, "file size out of range")
    name = storage.safe_name(data["filename"], "recording.mp4")
    if "." + name.rsplit(".", 1)[-1].lower() not in ALLOWED_EXT:
        raise ApiError(422, "सिर्फ़ वीडियो/ऑडियो फ़ाइलें (mp4, mov, mkv, webm, wav, mp3…)")
    rel = str(storage.project_dir(p["workspace_id"], p["id"]) / "raw" / name)
    path = storage.ensure_parent(rel)
    # resume if the same file is already half here
    existing = db.row(db.conn().execute(
        "SELECT * FROM uploads WHERE project_id = ? AND filename = ? AND size = ? AND done = 0",
        (p["id"], name, size)).fetchone())
    if existing:
        received = path.stat().st_size if path.exists() else 0
        with db.tx() as c:
            db.update(c, "uploads", existing["id"], {"received": received})
        return ok({"upload_id": existing["id"], "received": received, "chunk": 8 * 1024 * 1024})
    path.write_bytes(b"")
    up = {"id": db.new_id(), "project_id": p["id"], "filename": name, "size": size, "received": 0,
          "path": rel, "done": False, "created_at": db.now()}
    with db.tx() as c:
        db.insert(c, "uploads", up)
    return ok({"upload_id": up["id"], "received": 0, "chunk": 8 * 1024 * 1024}, 201)


def _upload(request: Request, user: dict) -> tuple[dict, dict]:
    p = own_project(request, user)
    up = db.get("uploads", request.path_params["upload_id"])
    if not up or up["project_id"] != p["id"]:
        raise ApiError(404, "upload not found")
    return p, up


@require("editor")
async def status(request: Request, user: dict):
    _, up = _upload(request, user)
    path = storage.abs_path(up["path"])
    received = path.stat().st_size if path.exists() else 0
    return ok({"upload_id": up["id"], "received": received, "size": up["size"], "done": up["done"]})


@require("editor")
async def chunk(request: Request, user: dict):
    """PUT raw bytes with header X-Offset. Chunks must arrive in order."""
    p, up = _upload(request, user)
    if up["done"]:
        raise ApiError(409, "upload already finished")
    offset = int(request.headers.get("x-offset", "-1"))
    path = storage.abs_path(up["path"])
    have = path.stat().st_size if path.exists() else 0
    if offset != have:
        raise ApiError(409, "offset mismatch", received=have)
    written = 0
    with path.open("ab") as f:
        async for part in request.stream():
            if have + written + len(part) > up["size"]:
                raise ApiError(413, "more bytes than announced")
            f.write(part)
            written += len(part)
    received = have + written
    with db.tx() as c:
        db.update(c, "uploads", up["id"], {"received": received})
    return ok({"received": received, "size": up["size"], "done": False})


@require("editor")
async def finish(request: Request, user: dict):
    p, up = _upload(request, user)
    path = storage.abs_path(up["path"])
    received = path.stat().st_size if path.exists() else 0
    if received != up["size"]:
        raise ApiError(409, "file incomplete", received=received)
    with db.tx() as c:
        db.update(c, "uploads", up["id"], {"done": True, "received": received})
        service.replace_assets(c, p["id"], "raw", keep_path=up["path"])
        service.add_asset(c, p["id"], "raw", up["path"])
        job = service.start_pipeline(c, p)
        service.log(c, user["workspace_id"], "upload.finish", user_id=user["id"], project_id=p["id"],
                    detail={"file": up["filename"], "size": received})
    return ok({"job": job})


routes = [
    Route("/projects/{project_id}/uploads", start, methods=["POST"]),
    Route("/projects/{project_id}/uploads/{upload_id}", status),
    Route("/projects/{project_id}/uploads/{upload_id}/chunk", chunk, methods=["PUT"]),
    Route("/projects/{project_id}/uploads/{upload_id}/finish", finish, methods=["POST"]),
]
