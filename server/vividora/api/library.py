"""Workspace asset library: music, SFX, B-roll clips, images, logos, LUTs.

Files live under MEDIA_ROOT/ws_<ws>/library/<kind>/ and are reused across
projects (render payloads reference them by id).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from starlette.requests import Request
from starlette.responses import FileResponse
from starlette.routing import Route

from .. import db, service, storage
from ..security import media_token, read_token
from .deps import ApiError, ok, require, require_worker

KINDS = {
    "music": {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"},
    "sfx": {".mp3", ".wav", ".m4a", ".ogg"},
    "broll": {".mp4", ".mov", ".mkv", ".webm", ".m4v"},
    "image": {".png", ".jpg", ".jpeg", ".webp", ".gif"},
    "logo": {".png", ".webp", ".svg"},
    "lut": {".cube"},
    "font": {".ttf", ".otf"},
}
MAX_SIZE = 2 * 1024 ** 3


def _probe_meta(path: Path, kind: str) -> dict:
    if kind in ("lut", "font"):
        return {}
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format",
                              "-show_streams", str(path)], capture_output=True, text=True, timeout=60)
        data = json.loads(out.stdout or "{}")
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}
    meta: dict = {"duration": round(float(data.get("format", {}).get("duration") or 0), 2)}
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and s.get("width"):
            meta.update(width=int(s["width"]), height=int(s["height"]))
    return meta


def _url(item: dict) -> str:
    return f"/api/library/{item['id']}/file?t={media_token(item['id'])}"


def _view(item: dict) -> dict:
    return {**{k: v for k, v in item.items() if k != "path"}, "url": _url(item)}


@require("viewer")
async def list_items(request: Request, user: dict):
    q = "SELECT * FROM library WHERE workspace_id = ?"
    args: list = [user["workspace_id"]]
    kind = request.query_params.get("kind")
    if kind in KINDS:
        q += " AND kind = ?"
        args.append(kind)
    rows = db.rows(db.conn().execute(q + " ORDER BY created_at DESC LIMIT 500", args))
    return ok([_view(r) for r in rows])


@require("editor")
async def upload(request: Request, user: dict):
    """PUT the file body. Query: kind, filename."""
    kind = request.query_params.get("kind", "")
    if kind not in KINDS:
        raise ApiError(422, f"kind must be one of {', '.join(KINDS)}")
    name = storage.safe_name(request.query_params.get("filename", ""), f"{kind}.bin")
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in KINDS[kind]:
        raise ApiError(422, f"{kind} के लिए {', '.join(sorted(KINDS[kind]))} फ़ाइलें ही चलेंगी")
    try:
        size = int(request.headers.get("content-length", "0"))
    except ValueError:
        size = 0
    if size > MAX_SIZE:
        raise ApiError(413, "file too large")
    item_id = db.new_id()
    rel = str(Path(f"ws_{user['workspace_id']}") / "library" / kind / f"{item_id[:8]}_{name}")
    path = storage.ensure_parent(rel)
    written = 0
    with path.open("wb") as f:
        async for part in request.stream():
            written += len(part)
            if written > MAX_SIZE:
                f.close()
                path.unlink(missing_ok=True)
                raise ApiError(413, "file too large")
            f.write(part)
    item = {"id": item_id, "workspace_id": user["workspace_id"], "kind": kind, "name": name,
            "path": rel, "size": written, "mime": storage.guess_mime(rel),
            "meta": _probe_meta(path, kind), "created_by": user["id"], "created_at": db.now()}
    with db.tx() as c:
        db.insert(c, "library", item)
        service.log(c, user["workspace_id"], "library.add", user_id=user["id"],
                    detail={"kind": kind, "name": name})
    return ok(_view(item), 201)


def _item(request: Request, user: dict | None = None) -> dict:
    item = db.get("library", request.path_params["item_id"])
    if not item or (user and item["workspace_id"] != user["workspace_id"]):
        raise ApiError(404, "library item not found")
    return item


@require("editor")
async def rename(request: Request, user: dict):
    item = _item(request, user)
    data = json.loads(await request.body() or b"{}")
    changes = {}
    if data.get("name"):
        changes["name"] = str(data["name"])[:120]
    if isinstance(data.get("meta"), dict):
        changes["meta"] = {**item["meta"], **data["meta"]}
    if changes:
        with db.tx() as c:
            db.update(c, "library", item["id"], changes)
    return ok(_view(db.get("library", item["id"])))


@require("editor")
async def delete(request: Request, user: dict):
    item = _item(request, user)
    with db.tx() as c:
        c.execute("DELETE FROM library WHERE id = ?", (item["id"],))
    try:
        storage.abs_path(item["path"]).unlink(missing_ok=True)
    except (ValueError, OSError):
        pass
    return ok()


async def file(request: Request):
    """Browser preview/download: token in ?t= (same scheme as /api/media)."""
    item = db.get("library", request.path_params["item_id"])
    tok = request.query_params.get("t")
    data = read_token(tok, kind="media") if tok else None
    if not item or not data or data.get("sub") != item["id"]:
        raise ApiError(401, "media link expired")
    path = storage.abs_path(item["path"])
    if not path.exists():
        raise ApiError(404, "file missing on disk")
    return FileResponse(path, media_type=item["mime"] or "application/octet-stream")


@require_worker
async def worker_file(request: Request):
    item = db.get("library", request.path_params["item_id"])
    if not item:
        raise ApiError(404, "library item not found")
    path = storage.abs_path(item["path"])
    if not path.exists():
        raise ApiError(404, "file missing")
    return FileResponse(path, media_type=item["mime"] or "application/octet-stream")


routes = [
    Route("/library", list_items),
    Route("/library", upload, methods=["PUT"]),
    Route("/library/{item_id}", rename, methods=["PATCH"]),
    Route("/library/{item_id}", delete, methods=["DELETE"]),
    Route("/library/{item_id}/file", file),
    Route("/worker/library/{item_id}", worker_file),
]
