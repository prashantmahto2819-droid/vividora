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
    try:
        size = int(data["size"])
    except (TypeError, ValueError):
        raise ApiError(422, "size must be a number")
    if size <= 0 or size > MAX_UPLOAD:
        raise ApiError(422, "file size out of range")
    from .. import saas
    saas.check_storage(db.conn(), p["workspace_id"], size)
    name = storage.safe_name(data["filename"], "recording.mp4")
    if "." + name.rsplit(".", 1)[-1].lower() not in ALLOWED_EXT:
        raise ApiError(422, "सिर्फ़ वीडियो/ऑडियो फ़ाइलें (mp4, mov, mkv, webm, wav, mp3…)")
    if data.get("clip"):
        # one of several clips: numbered so the merge keeps the order they were added
        n = db.conn().execute("SELECT COUNT(*) FROM assets WHERE project_id = ? AND kind = 'clip'", (p["id"],)).fetchone()[0]
        n += db.conn().execute("SELECT COUNT(*) FROM uploads WHERE project_id = ? AND done = 0 AND filename LIKE 'clip%'", (p["id"],)).fetchone()[0]
        name = f"clip{n + 1:02d}_{name}"
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
    try:
        offset = int(request.headers.get("x-offset", "-1"))
    except (TypeError, ValueError):
        raise ApiError(422, "X-Offset must be a number")
    path = storage.abs_path(up["path"])
    have = path.stat().st_size if path.exists() else 0
    if offset != have:
        raise ApiError(409, "offset mismatch", received=have)
    # integrity: the browser sends the chunk's SHA-256; a damaged chunk is dropped (file truncated back) and re-sent
    want = (request.headers.get("x-sha256") or "").strip().lower()
    import hashlib
    h = hashlib.sha256()
    written = 0
    with path.open("ab") as f:
        async for part in request.stream():
            if have + written + len(part) > up["size"]:
                f.truncate(have)
                raise ApiError(413, "more bytes than announced", received=have)
            f.write(part)
            h.update(part)
            written += len(part)
    if want and h.hexdigest() != want:
        with path.open("r+b") as f:
            f.truncate(have)
        raise ApiError(422, "chunk corrupted in transit", code="hash", received=have)
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
    # the bytes must be a real media file (a renamed .exe/.html is refused and deleted)
    try:
        storage.validate_media(path, "video")
    except ApiError:
        path.unlink(missing_ok=True)
        with db.tx() as c:
            c.execute("DELETE FROM uploads WHERE id = ?", (up["id"],))
        raise
    data = await body(request)
    is_clip = up["filename"].startswith("clip")
    with db.tx() as c:
        db.update(c, "uploads", up["id"], {"done": True, "received": received})
        if is_clip:
            order = c.execute("SELECT COUNT(*) FROM assets WHERE project_id = ? AND kind = 'clip'", (p["id"],)).fetchone()[0]
            service.add_asset(c, p["id"], "clip", up["path"], label=up["filename"], meta={"order": order})
            job = service.start_pipeline(c, p, merge=True) if data.get("start") else None
        else:
            service.replace_assets(c, p["id"], "raw", keep_path=up["path"])
            service.add_asset(c, p["id"], "raw", up["path"])
            job = service.start_pipeline(c, p)
        service.log(c, user["workspace_id"], "upload.finish", user_id=user["id"], project_id=p["id"],
                    detail={"file": up["filename"], "size": received})
    return ok({"job": job})


@require("editor")
async def start_pipeline(request: Request, user: dict):
    """Start (or restart) the pipeline for a multi-clip project after all clips are up."""
    p = own_project(request, user)
    clips = db.rows(db.conn().execute("SELECT * FROM assets WHERE project_id = ? AND kind = 'clip'", (p["id"],)))
    if not clips:
        raise ApiError(400, "पहले clips upload करें")
    with db.tx() as c:
        job = service.start_pipeline(c, p, merge=True)
    return ok({"job": job})


@require("editor")
async def adopt_raw(request: Request, user: dict):
    """Turn a single-recording project into a multi-clip one: the raw file becomes clip 1."""
    p = own_project(request, user)
    raw = service.asset_of(p["id"], "raw")
    if not raw:
        raise ApiError(400, "कोई recording नहीं")
    if db.conn().execute("SELECT COUNT(*) FROM assets WHERE project_id = ? AND kind = 'clip'", (p["id"],)).fetchone()[0]:
        return ok({"adopted": False})
    src = storage.abs_path(raw["path"])
    src_size = src.stat().st_size if src.exists() else 0
    from .. import saas
    saas.check_storage(db.conn(), p["workspace_id"], src_size)
    name = "clip01_" + src.name
    rel = str(storage.project_dir(p["workspace_id"], p["id"]) / "raw" / name)
    dst = storage.ensure_parent(rel)
    if src.exists() and not dst.exists():
        import shutil
        shutil.copy2(src, dst)
    with db.tx() as c:
        service.add_asset(c, p["id"], "clip", rel, label=name, meta={"order": 0})
    return ok({"adopted": True})


@require("editor")
async def delete_clip(request: Request, user: dict):
    p = own_project(request, user)
    a = db.get("assets", request.path_params["asset_id"])
    if not a or a["project_id"] != p["id"] or a["kind"] != "clip":
        raise ApiError(404, "clip not found")
    with db.tx() as c:
        c.execute("DELETE FROM assets WHERE id = ?", (a["id"],))
    try:
        storage.abs_path(a["path"]).unlink(missing_ok=True)
    except (ValueError, OSError):
        pass
    return ok()


routes = [
    Route("/projects/{project_id}/uploads", start, methods=["POST"]),
    Route("/projects/{project_id}/uploads/{upload_id}", status),
    Route("/projects/{project_id}/uploads/{upload_id}/chunk", chunk, methods=["PUT"]),
    Route("/projects/{project_id}/uploads/{upload_id}/finish", finish, methods=["POST"]),
    Route("/projects/{project_id}/start", start_pipeline, methods=["POST"]),
    Route("/projects/{project_id}/clips/adopt", adopt_raw, methods=["POST"]),
    Route("/projects/{project_id}/clips/{asset_id}", delete_clip, methods=["DELETE"]),
]
