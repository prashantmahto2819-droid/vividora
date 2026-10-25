"""Workspace asset library: music, SFX, B-roll clips, images, logos, LUTs.

Files live under MEDIA_ROOT/ws_<ws>/library/<kind>/ and are reused across
projects (render payloads reference them by id).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.parse
from pathlib import Path

from starlette.concurrency import run_in_threadpool
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


def check_cube(path: Path) -> dict:
    """Validate a .cube LUT (Adobe/Resolve text format). Raises ApiError with a plain reason for a bad file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as ex:
        raise ApiError(422, f"LUT पढ़ नहीं सकी: {ex}")
    size = None
    dim = None
    rows = 0
    for ln in text.splitlines():
        t = ln.strip()
        if not t or t.startswith("#") or t.startswith("TITLE") or t.startswith("DOMAIN_"):
            continue
        if t.startswith("LUT_3D_SIZE"):
            dim = 3
            try:
                size = int(t.split()[1])
            except (IndexError, ValueError):
                raise ApiError(422, "LUT ख़राब है: LUT_3D_SIZE के बाद संख्या चाहिए")
            continue
        if t.startswith("LUT_1D_SIZE"):
            dim = 1
            try:
                size = int(t.split()[1])
            except (IndexError, ValueError):
                raise ApiError(422, "LUT ख़राब है: LUT_1D_SIZE के बाद संख्या चाहिए")
            continue
        parts = t.split()
        if len(parts) != 3:
            raise ApiError(422, f"LUT ख़राब है: हर पंक्ति में 3 संख्याएँ चाहिए (मिला: “{t[:40]}”)")
        try:
            [float(x) for x in parts]
        except ValueError:
            raise ApiError(422, f"LUT ख़राब है: संख्या नहीं पढ़ी गई (“{t[:40]}”)")
        rows += 1
    if not size or dim is None:
        raise ApiError(422, "LUT ख़राब है: LUT_3D_SIZE (या LUT_1D_SIZE) नहीं मिला — .cube format ही चलेगा")
    want = size ** 3 if dim == 3 else size
    if rows != want:
        raise ApiError(422, f"LUT अधूरी है: {want} पंक्तियाँ चाहिए, {rows} मिलीं")
    if dim == 3 and not (2 <= size <= 65):
        raise ApiError(422, f"LUT size {size} नहीं चलेगा (2–65)")
    return {"lut_dim": dim, "lut_size": size}


def _probe_meta(path: Path, kind: str) -> dict:
    if kind == "font":
        try:  # family name as libass / CSS will know it
            fam = subprocess.run(["fc-scan", "--format", "%{family[0]}", str(path)], capture_output=True, text=True, timeout=30).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            fam = ""
        return {"family": fam or path.stem}
    if kind == "lut":
        return check_cube(path)
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
    from .. import cutout
    alpha = f"/api/library/{item['id']}/alpha?t={media_token(item['id'])}"
    return {**{k: v for k, v in item.items() if k != "path"}, "url": _url(item), "meta": cutout.view_meta(item, alpha)}


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
              license: str, channel_id: str | None = None, move: bool = False, analyse: bool = True) -> dict:
    import shutil
    item_id = db.new_id()
    rel = str(Path(f"ws_{workspace_id}") / "library" / kind / f"{item_id[:8]}_{storage.safe_name(src.name)}")
    dst = storage.ensure_parent(rel)
    (shutil.move if move else shutil.copy2)(str(src), str(dst))
    meta = _probe_meta(dst, kind)
    if kind == "music" and analyse:
        meta = {**meta, **_music_meta(dst, name, tags)}
    item = {"id": item_id, "workspace_id": workspace_id, "kind": kind, "name": name[:120], "path": rel,
            "size": dst.stat().st_size, "mime": storage.guess_mime(rel), "meta": meta,
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
                      source="starter", license=cfg["license"], analyse=False)  # music is tagged lazily (Audio tab)
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

# ---- YouTube Audio (yt-dlp) helpers ----
# Channels well-known for royalty-free music (YouTube Audio Library, NCS, etc.)
_YT_FREE_CHANNELS = {
    "UCht8qITGkBvXKsR1Byln-wA",  # YouTube Audio Library
    "UC_aEa8K-EOJ3D6gOs7HcyNg",  # NoCopyrightSounds
    "UCQ2-dDlL1MOT-jGBROoJcSQ",  # Audio Library — Music for content creators
    "UCHEioEoqyFPk0j2Iani1bvg",  # Vlog No Copyright Music
    "UCByJTOhXUPnFBSy5C5OQSmA",  # Infraction — No Copyright Music
    "UCx5VxJh2lYMYpKsbYwjEJIA",  # Chillhop Music
}


def _yt_search(q: str) -> list[dict]:
    """Search YouTube via yt-dlp for royalty-free / CC music."""
    try:
        proc = subprocess.run(
            ["yt-dlp", "--dump-json", f"ytsearch30:{q} royalty free", "--flat-playlist"],
            capture_output=True, text=True, timeout=45,
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise ApiError(502, f"yt-dlp search विफल: {e}")
    out: list[dict] = []
    for line in proc.stdout.strip().splitlines():
        try:
            r = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        # Keep only CC-licensed videos or videos from known free-music channels
        lic = (r.get("license") or "").lower()
        channel_id = r.get("channel_id") or ""
        is_cc = "creative commons" in lic or lic == "cc-by"
        is_free_ch = channel_id in _YT_FREE_CHANNELS
        if not is_cc and not is_free_ch:
            continue
        vid_url = r.get("webpage_url") or r.get("url") or f"https://www.youtube.com/watch?v={r.get('id')}"
        thumb = (r.get("thumbnails") or [{}])[-1].get("url") or r.get("thumbnail") or ""
        out.append({
            "title": r.get("title") or "untitled",
            "url": vid_url,
            "preview": thumb,
            "duration": r.get("duration"),
            "license": "Creative Commons" if is_cc else f"Free music — {r.get('channel') or r.get('uploader') or ''}",
            "creator": r.get("channel") or r.get("uploader") or "",
            "page": vid_url,
            "kind": "music",
            "source": "youtube-audio",
            "yt_id": r.get("id"),
        })
    return out


def _yt_extract_audio(url: str, dst: Path) -> Path:
    """Extract audio from a YouTube URL into dst directory. Returns the output file path."""
    out_tpl = str(dst / "%(title).60s.%(ext)s")
    try:
        proc = subprocess.run(
            ["yt-dlp", "-x", "--audio-format", "mp3", "--audio-quality", "192K",
             "--max-filesize", str(MAX_SIZE), "-o", out_tpl, url],
            capture_output=True, text=True, timeout=300,
        )
    except subprocess.TimeoutExpired:
        raise ApiError(504, "YouTube audio extract में बहुत समय लगा")
    except (OSError, subprocess.SubprocessError) as e:
        raise ApiError(502, f"yt-dlp extract विफल: {e}")
    if proc.returncode != 0:
        err = (proc.stderr or "").strip()[-200:]
        raise ApiError(502, f"yt-dlp extract error: {err}")
    # find the output file
    for f in dst.iterdir():
        if f.suffix.lower() in {".mp3", ".m4a", ".opus", ".ogg", ".wav"}:
            return f
    raise ApiError(502, "yt-dlp ने कोई audio file नहीं बनाई")


# ---- Freesound.org helpers ----

def _freesound_search(q: str) -> list[dict]:
    """Search Freesound.org for CC0 sounds."""
    key = os.getenv("FREESOUND_API_KEY")
    if not key:
        raise ApiError(400, ".env में FREESOUND_API_KEY डालें (freesound.org/apiv2 — free)")
    url = (
        f"https://freesound.org/apiv2/search/text/"
        f"?query={urllib.parse.quote(q)}"
        f'&filter=license:"Creative Commons 0"'
        f"&fields=id,name,tags,duration,previews,username,license,url"
        f"&page_size=30"
        f"&token={key}"
    )
    data = _http_json(url)
    out: list[dict] = []
    for r in data.get("results", []):
        previews = r.get("previews") or {}
        preview_url = previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3") or ""
        out.append({
            "title": r.get("name") or "untitled",
            "url": preview_url,
            "preview": preview_url,
            "duration": round(r.get("duration") or 0, 2),
            "license": "CC0 1.0",
            "creator": r.get("username") or "",
            "page": r.get("url") or f"https://freesound.org/people/{r.get('username')}/sounds/{r.get('id')}/",
            "kind": "sfx",
            "source": "freesound",
            "freesound_id": r.get("id"),
            "tags": ",".join((r.get("tags") or [])[:10]),
        })
    return out


def _freesound_download(sound_id: int, dst: Path) -> Path:
    """Download the full-quality file from Freesound."""
    key = os.getenv("FREESOUND_API_KEY")
    if not key:
        raise ApiError(400, "FREESOUND_API_KEY not configured")
    import urllib.request
    # get download URL
    info = _http_json(f"https://freesound.org/apiv2/sounds/{sound_id}/?fields=name,download&token={key}")
    dl_url = info.get("download")
    if not dl_url:
        raise ApiError(502, "Freesound download URL नहीं मिला")
    name = storage.safe_name(info.get("name") or f"freesound_{sound_id}")[:60]
    ext = Path(dl_url.split("?")[0]).suffix.lower() or ".wav"
    out = dst / f"{name}{ext}"
    req = urllib.request.Request(dl_url, headers={"Authorization": f"Token {key}", "User-Agent": "Vividora/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, out.open("wb") as o:
        sz = 0
        while chunk := r.read(1 << 20):
            sz += len(chunk)
            if sz > 300 * 1024 * 1024:
                raise ApiError(413, "file बहुत बड़ी")
            o.write(chunk)
    return out


# ---- Trending Audio Discovery ----
_trending_cache: dict = {"ts": 0, "data": []}
_TRENDING_TTL = 6 * 3600  # 6 hours


def _fetch_trending() -> list[dict]:
    """Fetch trending music from YouTube Music charts (India) via yt-dlp. Cached for 6h."""
    now = time.time()
    if _trending_cache["data"] and now - _trending_cache["ts"] < _TRENDING_TTL:
        return _trending_cache["data"]
    try:
        proc = subprocess.run(
            ["yt-dlp", "--dump-json",
             "https://www.youtube.com/feed/trending?bp=4gINGgt5dG1hX2NoYXJ0cw%3D%3D",
             "--flat-playlist", "--playlist-items", "1-20"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        # fallback: try YouTube Music charts
        try:
            proc = subprocess.run(
                ["yt-dlp", "--dump-json", "https://music.youtube.com/playlist?list=RDCLAK5uy_k2a",
                 "--flat-playlist", "--playlist-items", "1-20"],
                capture_output=True, text=True, timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            return _trending_cache["data"]  # return stale cache on failure
    out: list[dict] = []
    for line in proc.stdout.strip().splitlines():
        try:
            r = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        vid_url = r.get("webpage_url") or r.get("url") or f"https://www.youtube.com/watch?v={r.get('id')}"
        thumb = (r.get("thumbnails") or [{}])[-1].get("url") or r.get("thumbnail") or ""
        out.append({
            "title": r.get("title") or "untitled",
            "artist": r.get("channel") or r.get("uploader") or "",
            "duration": r.get("duration"),
            "thumbnail": thumb,
            "url": vid_url,
            "yt_id": r.get("id"),
        })
    if out:
        _trending_cache["ts"] = now
        _trending_cache["data"] = out
    return out or _trending_cache["data"]


@require("viewer")
async def search_free(request: Request, user: dict):
    """Search free libraries. source: openverse-audio | openverse-image | pixabay-video | pixabay-image | jamendo | youtube-audio | freesound"""
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
        elif src == "youtube-audio":
            out.extend(_yt_search(q))
        elif src == "freesound":
            out.extend(_freesound_search(q))
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
    data = json.loads(await request.body() or b"{}")
    url, kind = data.get("url"), data.get("kind")
    source = data.get("source") or "web"

    # YouTube audio: url is a YouTube page, not a direct file
    if source == "youtube-audio":
        if not url:
            raise ApiError(422, "url गलत")
        kind = kind or "music"
        if kind not in KINDS:
            raise ApiError(422, "kind गलत")

        def work() -> dict:
            with tempfile.TemporaryDirectory() as td:
                f = _yt_extract_audio(url, Path(td))
                credit = f"{data.get('title') or ''} by {data.get('creator') or 'unknown'} ({data.get('license') or 'YouTube'}) {data.get('page') or url}".strip()
                return _add_file(user["workspace_id"], user["id"], kind, f, name=(data.get("title") or f.stem)[:120],
                                 tags=",".join(filter(None, ["youtube-audio", *(str(data.get("tags") or "").split(","))])),
                                 source="youtube-audio", license=credit[:500], channel_id=data.get("channel_id"), move=True)
        try:
            item = await run_in_threadpool(work)
        except ApiError:
            raise
        except Exception as e:  # noqa: BLE001
            raise ApiError(502, f"YouTube extract नहीं हुआ: {e}")
        return ok(_view(item), 201)

    # Freesound: download full quality via API
    if source == "freesound" and data.get("freesound_id"):
        kind = kind or "sfx"
        if kind not in KINDS:
            raise ApiError(422, "kind गलत")

        def work() -> dict:
            with tempfile.TemporaryDirectory() as td:
                f = _freesound_download(int(data["freesound_id"]), Path(td))
                credit = f"{data.get('title') or ''} by {data.get('creator') or 'unknown'} (CC0 1.0) {data.get('page') or ''}".strip()
                return _add_file(user["workspace_id"], user["id"], kind, f, name=(data.get("title") or f.stem)[:120],
                                 tags=",".join(filter(None, ["freesound", *(str(data.get("tags") or "").split(","))])),
                                 source="freesound", license=credit[:500], channel_id=data.get("channel_id"), move=True)
        try:
            item = await run_in_threadpool(work)
        except ApiError:
            raise
        except Exception as e:  # noqa: BLE001
            raise ApiError(502, f"Freesound download नहीं हुआ: {e}")
        return ok(_view(item), 201)

    # Default: direct HTTP download (openverse, pixabay, jamendo, etc.)
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


@require("viewer")
async def trending(request: Request, user: dict):
    """Trending music from YouTube Music charts — metadata only (no download)."""
    try:
        items = await run_in_threadpool(_fetch_trending)
    except Exception as e:  # noqa: BLE001
        raise ApiError(502, f"trending नहीं मिला: {e}")
    return ok(items)


@require("editor")
async def import_playlist(request: Request, user: dict):
    """Import audio from a YouTube playlist (up to 50 tracks)."""
    import tempfile
    data = json.loads(await request.body() or b"{}")
    pl_url = (data.get("url") or "").strip()
    if not pl_url or "youtube.com" not in pl_url and "youtu.be" not in pl_url:
        raise ApiError(422, "YouTube playlist URL डालें")
    max_tracks = min(int(data.get("max") or 50), 50)

    def work() -> list[dict]:
        # Step 1: list playlist entries
        try:
            proc = subprocess.run(
                ["yt-dlp", "--dump-json", "--flat-playlist", "--playlist-items", f"1-{max_tracks}", pl_url],
                capture_output=True, text=True, timeout=60,
            )
        except (OSError, subprocess.SubprocessError) as e:
            raise ApiError(502, f"playlist पढ़ नहीं सकी: {e}")
        entries = []
        for line in proc.stdout.strip().splitlines():
            try:
                entries.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                continue
        if not entries:
            raise ApiError(404, "playlist में कोई video नहीं मिला")
        # Step 2: extract audio one by one
        imported: list[dict] = []
        errors: list[str] = []
        for entry in entries[:max_tracks]:
            vid_url = entry.get("webpage_url") or entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id')}"
            title = entry.get("title") or "untitled"
            artist = entry.get("channel") or entry.get("uploader") or ""
            try:
                with tempfile.TemporaryDirectory() as td:
                    f = _yt_extract_audio(vid_url, Path(td))
                    credit = f"{title} by {artist} (YouTube playlist) {vid_url}".strip()
                    item = _add_file(
                        user["workspace_id"], user["id"], "music", f,
                        name=title[:120],
                        tags=",".join(filter(None, ["youtube-audio", "playlist", artist[:40]])),
                        source="youtube-audio", license=credit[:500],
                        channel_id=data.get("channel_id"), move=True,
                    )
                    imported.append({"id": item["id"], "name": item["name"]})
            except Exception as e:  # noqa: BLE001
                errors.append(f"{title[:40]}: {str(e)[:80]}")
        return imported, errors

    try:
        imported, errors = await run_in_threadpool(work)
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ApiError(502, f"playlist import नहीं हुआ: {e}")
    with db.tx() as c:
        service.log(c, user["workspace_id"], "library.playlist_import", user_id=user["id"],
                    detail={"imported": len(imported), "errors": len(errors)})
    return ok({"imported": imported, "errors": errors}, 201)


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
    from .. import saas
    saas.check_storage(db.conn(), user["workspace_id"], size)
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
    try:
        meta = _probe_meta(path, kind)
        storage.validate_media(path, kind)  # the bytes must really be the media type the name claims
    except ApiError:
        path.unlink(missing_ok=True)  # a rejected LUT / fake file never stays in the library
        raise
    tags = (request.query_params.get("tags") or "")[:200]
    if kind == "music":
        meta = {**meta, **(await run_in_threadpool(_music_meta, path, name, tags))}
    item = {"id": item_id, "workspace_id": user["workspace_id"], "kind": kind, "name": name,
            "path": rel, "size": written, "mime": storage.guess_mime(rel),
            "meta": meta, "created_by": user["id"], "created_at": db.now(),
            "tags": tags, "source": "upload", "license": "own",
            "channel_id": request.query_params.get("channel") or None}
    with db.tx() as c:
        db.insert(c, "library", item)
        service.log(c, user["workspace_id"], "library.add", user_id=user["id"],
                    detail={"kind": kind, "name": name})
    return ok(_view(item), 201)


def _music_meta(path: Path, name: str = "", tags: str = "") -> dict:
    """bpm / mood / genre tags for a music file; never fails the upload."""
    from ..engine import musictag
    try:
        return musictag.analyze(path, name, tags)
    except Exception as e:  # noqa: BLE001
        return {"analysed": False, "analyse_error": str(e)[:160]}


@require("editor")
async def analyze_music(request: Request, user: dict):
    """Tag every music item that has no analysis yet (or one item: {id}, or all again: {force: true})."""
    data = json.loads(await request.body() or b"{}")
    q = "SELECT * FROM library WHERE workspace_id = ? AND kind = 'music'"
    args: list = [user["workspace_id"]]
    if data.get("id"):
        q += " AND id = ?"
        args.append(str(data["id"]))
    rows = db.rows(db.conn().execute(q + " ORDER BY created_at DESC LIMIT 400", args))
    todo = [r for r in rows if data.get("force") or data.get("id") or not (r.get("meta") or {}).get("analysed")]

    def work() -> list[dict]:
        done = []
        for r in todo[:60]:   # a big library is tagged over a few calls
            try:
                m = _music_meta(storage.abs_path(r["path"]), r["name"], r.get("tags") or "")
            except (ValueError, OSError):
                m = {"analysed": False}
            with db.tx() as c:
                db.update(c, "library", r["id"], {"meta": {**(r.get("meta") or {}), **m}})
            done.append({"id": r["id"], **{k: m.get(k) for k in ("bpm", "moods", "genres", "analysed")}})
        return done
    done = await run_in_threadpool(work)
    return ok({"analysed": done, "left": max(0, len(todo) - len(done))})


@require("viewer")
async def music_filters(request: Request, user: dict):
    """Vocabulary for the Audio tab filters (+ which licences count as commercial-safe)."""
    from ..engine import musictag
    rows = db.rows(db.conn().execute("SELECT id, license, meta FROM library WHERE workspace_id = ? AND kind = 'music'", (user["workspace_id"],)))
    return ok({"moods": musictag.MOODS, "genres": musictag.GENRES,
               "commercial": {r["id"]: musictag.commercial_ok(r.get("license")) for r in rows}})


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
        from .. import cutout
        cutout.delete_lib_alpha(item)
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


async def alpha_file(request: Request):
    """The cached person matte of a library video (gray H.264) for the editor's live cutout preview."""
    from .. import cutout
    item = db.get("library", request.path_params["item_id"])
    tok = request.query_params.get("t")
    data = read_token(tok, kind="media") if tok else None
    if not item or not data or data.get("sub") != item["id"]:
        raise ApiError(401, "media link expired")
    p = cutout.lib_alpha_path(item)
    if not p:
        raise ApiError(404, "cutout अभी नहीं बना")
    return FileResponse(p, media_type="video/mp4")


@require_worker
async def worker_alpha(request: Request):
    from .. import cutout
    p = cutout.lib_alpha_path(db.get("library", request.path_params["item_id"]))
    if not p:
        raise ApiError(404, "cutout not found")
    return FileResponse(p, media_type="video/mp4")


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
    from .workers import job_workspace
    if job_workspace(request) not in (None, item["workspace_id"]):
        raise ApiError(404, "library item not found")
    path = storage.abs_path(item["path"])
    if not path.exists():
        raise ApiError(404, "file missing")
    return FileResponse(path, media_type=item["mime"] or "application/octet-stream")


routes = [
    Route("/library/starter", starter, methods=["POST"]),
    Route("/library/search", search_free),
    Route("/library/import", import_free, methods=["POST"]),
    Route("/library/trending", trending),
    Route("/library/import-playlist", import_playlist, methods=["POST"]),
    Route("/library/analyze-music", analyze_music, methods=["POST"]),
    Route("/library/music-filters", music_filters),
    Route("/library", list_items),
    Route("/library", upload, methods=["PUT"]),
    Route("/library/{item_id}", rename, methods=["PATCH"]),
    Route("/library/{item_id}", delete, methods=["DELETE"]),
    Route("/library/{item_id}/file", file),
    Route("/library/{item_id}/frame", frame),
    Route("/library/{item_id}/alpha", alpha_file),
    Route("/worker/library/{item_id}/alpha", worker_alpha),
    Route("/worker/library/{item_id}", worker_file),
]
