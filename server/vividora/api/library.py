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
    "music": {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".mp4", ".mov", ".webm", ".opus"},  # a reel's video works as the song
    "sfx": {".mp3", ".wav", ".m4a", ".ogg"},
    "broll": {".mp4", ".mov", ".mkv", ".webm", ".m4v"},
    "image": {".png", ".jpg", ".jpeg", ".webp", ".gif"},
    "logo": {".png", ".webp", ".svg"},
    "frame": {".png", ".webp"},
    "sticker": {".png", ".webp", ".gif"},
    "lut": {".cube"},
    "font": {".ttf", ".otf"},
    "voice": {".mp3", ".wav", ".m4a"},
}
MAX_SIZE = 2 * 1024 ** 3


def _probe_meta(path: Path, kind: str) -> dict:
    if kind == "font":
        try:  # family name as libass / CSS will know it
            fam = subprocess.run(["fc-scan", "--format", "%{family[0]}", str(path)], capture_output=True, text=True, timeout=30).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            fam = ""
        return {"family": fam or path.stem}
    if kind == "lut":
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
    ch = request.query_params.get("channel")
    if ch:
        q += " AND (channel_id IS NULL OR channel_id = ?)"
        args.append(ch)
    tag = request.query_params.get("tag")
    if tag:
        q += " AND (',' || tags || ',') LIKE ?"
        args.append(f"%,{tag},%")
    text = request.query_params.get("q")
    if text:
        q += " AND (name LIKE ? OR tags LIKE ?)"
        args += [f"%{text}%", f"%{text}%"]
    rows = db.rows(db.conn().execute(q + " ORDER BY created_at DESC LIMIT 1500", args))
    return ok([_view(r) for r in rows])


STARTER = Path(__file__).resolve().parent.parent.parent / "starter"


def _add_file(workspace_id: str, user_id: str | None, kind: str, src: Path, *, name: str, tags: str, source: str,
              license: str, channel_id: str | None = None, move: bool = False) -> dict:
    import shutil
    item_id = db.new_id()
    rel = str(Path(f"ws_{workspace_id}") / "library" / kind / f"{item_id[:8]}_{storage.safe_name(src.name)}")
    dst = storage.ensure_parent(rel)
    (shutil.move if move else shutil.copy2)(str(src), str(dst))
    item = {"id": item_id, "workspace_id": workspace_id, "kind": kind, "name": name[:120], "path": rel,
            "size": dst.stat().st_size, "mime": storage.guess_mime(rel), "meta": _probe_meta(dst, kind),
            "created_by": user_id, "created_at": db.now(), "tags": tags, "source": source, "license": license,
            "channel_id": channel_id}
    with db.tx() as c:
        db.insert(c, "library", item)
    return item


def install_starter(workspace_id: str, user_id: str | None = None, only_new_since: int | None = None) -> int:
    """Copy the bundled starter pack into the workspace library (skips what's already there)."""
    man = json.loads((STARTER / "manifest.json").read_text())
    have = {(r["source"], r["name"]) for r in db.rows(db.conn().execute(
        "SELECT source, name FROM library WHERE workspace_id = ? AND source = 'starter'", (workspace_id,)))}
    n = 0
    for folder, cfg in man["folders"].items():
        d = STARTER / folder
        if not d.exists():
            continue
        for f in sorted(d.iterdir()):
            if f.suffix.lower() not in KINDS[cfg["kind"]]:
                continue
            nice = f.stem.replace("_", " ")
            if ("starter", nice) in have:
                continue
            if only_new_since is not None and int(man.get("added", {}).get(f"{folder}/{f.name}", 1)) <= only_new_since:
                continue
            sub = folder
            extra = []
            if folder == "music":
                parts = f.stem.split("_")
                extra = [p for p in parts[1:-1] if not p.endswith("bpm")]
            if folder == "frames":
                extra = ["vertical" if f.stem.endswith("_v") else "horizontal"]
            _add_file(workspace_id, user_id, cfg["kind"], f, name=nice, tags=",".join([*cfg["tags"].split(","), sub, *extra]),
                      source="starter", license=cfg["license"])
            n += 1
    return n


@require("admin")
async def starter(request: Request, user: dict):
    from starlette.concurrency import run_in_threadpool
    n = await run_in_threadpool(install_starter, user["workspace_id"], user["id"])
    with db.tx() as c:
        service.log(c, user["workspace_id"], "library.starter", user_id=user["id"], detail={"added": n})
    return ok({"added": n})


# ---- free online sources (licence-safe ones only)
def _http_json(url: str, headers: dict | None = None) -> dict:
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Vividora/1.0 (self-hosted video studio)", **(headers or {})})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


SAFE_CC = {"cc0", "pdm", "by", "by-sa"}  # commercial-safe CC (by/by-sa need credit)


@require("viewer")
async def search_free(request: Request, user: dict):
    """Search free libraries. source: openverse-audio | openverse-image | pixabay-video | pixabay-image | jamendo"""
    import os
    import urllib.parse
    from starlette.concurrency import run_in_threadpool
    src = request.query_params.get("source", "openverse-audio")
    q = (request.query_params.get("q") or "").strip()[:100]
    if not q:
        raise ApiError(422, "खोजने के लिए कुछ लिखें")

    def work() -> list[dict]:
        out: list[dict] = []
        if src.startswith("openverse"):
            kind = "audio" if src.endswith("audio") else "images"
            data = _http_json(f"https://api.openverse.org/v1/{kind}/?q={urllib.parse.quote(q)}&license_type=commercial&page_size=30")
            for r in data.get("results", []):
                lic = (r.get("license") or "").lower()
                if lic not in SAFE_CC:
                    continue
                out.append({"title": r.get("title") or "untitled", "url": r.get("url"), "preview": r.get("thumbnail") or r.get("url"),
                            "duration": (r.get("duration") or 0) / 1000 if kind == "audio" else None,
                            "license": f"CC {lic.upper()} {r.get('license_version') or ''}".strip(), "creator": r.get("creator"),
                            "attribution": r.get("attribution"), "page": r.get("foreign_landing_url"),
                            "kind": "music" if kind == "audio" else "image", "source": "openverse"})
        elif src.startswith("pixabay"):
            key = os.getenv("PIXABAY_API_KEY")
            if not key:
                raise ApiError(400, ".env में PIXABAY_API_KEY डालें (pixabay.com/api/docs — free)")
            if src.endswith("video"):
                data = _http_json(f"https://pixabay.com/api/videos/?key={key}&q={urllib.parse.quote(q)}&per_page=30&safesearch=true")
                for r in data.get("hits", []):
                    v = (r.get("videos") or {}).get("medium") or (r.get("videos") or {}).get("small") or {}
                    out.append({"title": r.get("tags"), "url": v.get("url"), "preview": v.get("thumbnail"), "duration": r.get("duration"),
                                "license": "Pixabay Content License", "creator": r.get("user"), "page": r.get("pageURL"),
                                "kind": "broll", "source": "pixabay"})
            else:
                data = _http_json(f"https://pixabay.com/api/?key={key}&q={urllib.parse.quote(q)}&per_page=30&safesearch=true&image_type=all")
                for r in data.get("hits", []):
                    out.append({"title": r.get("tags"), "url": r.get("largeImageURL") or r.get("webformatURL"), "preview": r.get("previewURL"),
                                "license": "Pixabay Content License", "creator": r.get("user"), "page": r.get("pageURL"),
                                "kind": "image", "source": "pixabay"})
        elif src == "jamendo":
            cid = os.getenv("JAMENDO_CLIENT_ID")
            if not cid:
                raise ApiError(400, ".env में JAMENDO_CLIENT_ID डालें (developer.jamendo.com — free)")
            data = _http_json(f"https://api.jamendo.com/v3.0/tracks/?client_id={cid}&format=json&limit=30&search={urllib.parse.quote(q)}"
                              f"&audioformat=mp32&include=licenses")
            for r in data.get("results", []):
                lic = (r.get("license_ccurl") or "")
                if "nc" in lic or "nd" in lic:
                    continue  # non-commercial / no-derivatives — not usable in monetised videos
                out.append({"title": f"{r.get('name')} — {r.get('artist_name')}", "url": r.get("audio"), "preview": r.get("audio"),
                            "duration": r.get("duration"), "license": lic, "creator": r.get("artist_name"), "page": r.get("shareurl"),
                            "kind": "music", "source": "jamendo"})
        return [o for o in out if o.get("url")]

    try:
        return ok(await run_in_threadpool(work))
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ApiError(502, f"search नहीं हुआ: {e}")


@require("editor")
async def import_free(request: Request, user: dict):
    """Download one search result into the library (keeps licence + credit)."""
    import tempfile
    import urllib.request
    from starlette.concurrency import run_in_threadpool
    data = json.loads(await request.body() or b"{}")
    url, kind = data.get("url"), data.get("kind")
    if not url or kind not in KINDS or not str(url).startswith("https://"):
        raise ApiError(422, "url/kind गलत")

    def work() -> dict:
        ext = Path(url.split("?")[0]).suffix.lower() or {"music": ".mp3", "broll": ".mp4", "image": ".jpg"}.get(kind, ".bin")
        if ext not in KINDS[kind]:
            ext = sorted(KINDS[kind])[0]
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / (storage.safe_name(data.get("title") or "item")[:60] + ext)
            req = urllib.request.Request(url, headers={"User-Agent": "Vividora/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r, f.open("wb") as o:
                size = 0
                while chunk := r.read(1 << 20):
                    size += len(chunk)
                    if size > 300 * 1024 * 1024:
                        raise ApiError(413, "file बहुत बड़ी")
                    o.write(chunk)
            credit = f"{data.get('title') or ''} by {data.get('creator') or 'unknown'} ({data.get('license') or ''}) {data.get('page') or ''}".strip()
            return _add_file(user["workspace_id"], user["id"], kind, f, name=(data.get("title") or f.stem)[:120],
                             tags=",".join(filter(None, [data.get("source"), *(str(data.get("tags") or "").split(","))])),
                             source=data.get("source") or "web", license=credit[:500], channel_id=data.get("channel_id"), move=True)

    try:
        item = await run_in_threadpool(work)
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ApiError(502, f"download नहीं हुआ: {e}")
    return ok(_view(item), 201)


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
            "meta": _probe_meta(path, kind), "created_by": user["id"], "created_at": db.now(),
            "tags": (request.query_params.get("tags") or "")[:200], "source": "upload", "license": "own",
            "channel_id": request.query_params.get("channel") or None}
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
    if "tags" in data:
        changes["tags"] = ",".join(t.strip() for t in str(data["tags"]).split(",") if t.strip())[:300]
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


async def frame(request: Request):
    """Small JPEG of one moment of a library video (plan thumbnails) — cached, so the editor
    never has to open dozens of <video> streams at once."""
    import hashlib
    import subprocess
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import Response
    item = db.get("library", request.path_params["item_id"])
    tok = request.query_params.get("t")
    data = read_token(tok, kind="media") if tok else None
    if not item or not data or data.get("sub") != item["id"]:
        raise ApiError(401, "media link expired")
    try:
        at = max(0.0, min(36000.0, float(request.query_params.get("at") or 0)))
    except ValueError:
        at = 0.0
    path = storage.abs_path(item["path"])
    if not path.exists():
        raise ApiError(404, "file missing on disk")
    cache = Path(storage.abs_path("cache")) / "frames"
    cache.mkdir(parents=True, exist_ok=True)
    out = cache / (hashlib.sha1(f"{item['id']}|{at:.2f}".encode()).hexdigest()[:20] + ".jpg")
    if not out.exists():
        def grab():
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.2f}", "-i", str(path), "-frames:v", "1",
                            "-vf", "scale=160:-2", "-q:v", "6", str(out)], capture_output=True, timeout=30)
        await run_in_threadpool(grab)
    if not out.exists():
        raise ApiError(404, "frame नहीं बना")
    return Response(out.read_bytes(), media_type="image/jpeg", headers={"cache-control": "private, max-age=86400"})


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
    Route("/library/starter", starter, methods=["POST"]),
    Route("/library/search", search_free),
    Route("/library/import", import_free, methods=["POST"]),
    Route("/library", list_items),
    Route("/library", upload, methods=["PUT"]),
    Route("/library/{item_id}", rename, methods=["PATCH"]),
    Route("/library/{item_id}", delete, methods=["DELETE"]),
    Route("/library/{item_id}/file", file),
    Route("/library/{item_id}/frame", frame),
    Route("/worker/library/{item_id}", worker_file),
]
