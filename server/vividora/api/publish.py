"""Connections (YouTube / Meta OAuth) and publications (upload jobs).

Flow: admin connects a channel once (/api/connect/<platform>/start → OAuth →
callback stores the refresh/page token). Later, for an APPROVED project, an
editor picks an output + connection, writes title/description, and a
`publish` job uploads it. Instagram/Facebook fetch the file themselves from
/pub/<token>, a signed public link that is valid for two days.
"""

from __future__ import annotations

import secrets as pysecrets
from pathlib import Path

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.routing import Route

from .. import db, queue, service, storage, thumbs
from ..config import settings
from ..engine import metadata
from ..publish import meta as metaapi
from ..publish import youtube
from ..publish.http import PublishError
from ..security import make_token, read_token
from .deps import ApiError, body, need, ok, own_project, require

PLATFORMS = ("youtube", "instagram", "facebook")
_states: dict[str, dict] = {}  # oauth state → {workspace_id, user_id, platform}


def conn_view(c: dict) -> dict:
    return {k: c.get(k) for k in ("id", "platform", "name", "external_id", "meta", "created_at", "updated_at", "channel_id")}


def _platform_status() -> dict:
    return {"youtube": youtube.configured(), "meta": metaapi.configured(), "public_url": settings.public_url,
            "dry_run": settings.publish_dry_run}


@require("viewer")
async def list_connections(request: Request, user: dict):
    rows = db.rows(db.conn().execute("SELECT * FROM connections WHERE workspace_id = ? ORDER BY created_at",
                                     (user["workspace_id"],)))
    return ok({"connections": [conn_view(r) for r in rows], "setup": _platform_status()})


@require("admin")
async def move_connection(request: Request, user: dict):
    cid = request.path_params["conn_id"]
    c0 = db.get("connections", cid)
    if not c0 or c0["workspace_id"] != user["workspace_id"]:
        raise ApiError(404, "connection not found")
    data = await body(request)
    with db.tx() as t:
        db.update(t, "connections", cid, {"channel_id": data.get("channel_id") or None, "updated_at": db.now()})
    return ok()


@require("admin")
async def delete_connection(request: Request, user: dict):
    cid = request.path_params["conn_id"]
    c = db.get("connections", cid)
    if not c or c["workspace_id"] != user["workspace_id"]:
        raise ApiError(404, "connection not found")
    with db.tx() as t:
        t.execute("DELETE FROM connections WHERE id = ?", (cid,))
        service.log(t, user["workspace_id"], "connection.delete", user_id=user["id"], detail={"platform": c["platform"]})
    return ok()


@require("admin")
async def connect_start(request: Request, user: dict):
    platform = request.path_params["platform"]
    if platform == "youtube":
        if not youtube.configured():
            raise ApiError(400, ".env में YT_CLIENT_ID / YT_CLIENT_SECRET / PUBLIC_URL सेट करें")
        state = pysecrets.token_urlsafe(24)
        _states[state] = {"workspace_id": user["workspace_id"], "user_id": user["id"], "platform": platform, "channel_id": request.query_params.get("channel")}
        return ok({"url": youtube.auth_url(state)})
    if platform == "meta":
        if not metaapi.configured():
            raise ApiError(400, ".env में META_APP_ID / META_APP_SECRET / PUBLIC_URL सेट करें")
        state = pysecrets.token_urlsafe(24)
        _states[state] = {"workspace_id": user["workspace_id"], "user_id": user["id"], "platform": platform, "channel_id": request.query_params.get("channel")}
        return ok({"url": metaapi.auth_url(state)})
    raise ApiError(404, "unknown platform")


def _done_page(msg: str, okay: bool = True) -> HTMLResponse:
    color = "#7FC48A" if okay else "#D86B6B"
    return HTMLResponse(f"""<!doctype html><meta charset=utf-8><body style="font-family:system-ui;background:#141A24;color:#ECE6DA;display:grid;place-items:center;height:100vh;margin:0">
<div style="text-align:center;max-width:460px"><h2 style="color:{color}">{msg}</h2><p>यह tab बंद करके Vividora में वापस जाएँ।</p>
<a href="/#/settings" style="color:#F2B33D">Settings खोलें</a></div><script>setTimeout(()=>{{location.href='/#/settings'}},2500)</script>""")


async def youtube_callback(request: Request):
    st = _states.pop(request.query_params.get("state", ""), None)
    code = request.query_params.get("code")
    if not st or not code:
        return _done_page("लिंक पुराना है — दोबारा Connect दबाएँ", False)
    try:
        sec = youtube.exchange_code(code)
        tok, sec = youtube.access_token(sec)
        ch = youtube.channel_info(tok)
    except PublishError as e:
        return _done_page(f"YouTube जोड़ नहीं पाए: {e}", False)
    with db.tx() as c:
        existing = db.row(c.execute("SELECT * FROM connections WHERE workspace_id=? AND platform='youtube' AND external_id=?",
                                    (st["workspace_id"], ch["id"])).fetchone())
        row = {"platform": "youtube", "name": ch["title"], "external_id": ch["id"], "secrets": sec,
               "meta": {"thumbnail": ch.get("thumbnail"), "subscribers": ch.get("subscribers")},
               "channel_id": st.get("channel_id"), "updated_at": db.now()}
        if existing:
            db.update(c, "connections", existing["id"], row)
        else:
            db.insert(c, "connections", {"id": db.new_id(), "workspace_id": st["workspace_id"],
                                         "created_by": st["user_id"], "created_at": db.now(), **row})
        service.log(c, st["workspace_id"], "connection.add", user_id=st["user_id"], detail={"platform": "youtube", "name": ch["title"]})
    return _done_page(f"YouTube channel “{ch['title']}” जुड़ गया ✓")


async def meta_callback(request: Request):
    st = _states.pop(request.query_params.get("state", ""), None)
    code = request.query_params.get("code")
    if not st or not code:
        return _done_page("लिंक पुराना है — दोबारा Connect दबाएँ", False)
    try:
        sec = metaapi.exchange_code(code)
        pages = metaapi.pages(sec["user_token"])
    except PublishError as e:
        return _done_page(f"Meta जोड़ नहीं पाए: {e}", False)
    if not pages:
        return _done_page("इस account पर कोई Facebook Page नहीं मिला (Page + linked Instagram Business account चाहिए)", False)
    added = []
    with db.tx() as c:
        for p in pages:
            rows = [{"platform": "facebook", "name": p["page_name"], "external_id": p["page_id"],
                     "secrets": {"page_id": p["page_id"], "page_token": p["page_token"], "expires_at": sec["expires_at"]},
                     "meta": {}}]
            if p.get("ig_id"):
                rows.append({"platform": "instagram", "name": "@" + (p.get("ig_username") or p["ig_id"]),
                             "external_id": p["ig_id"],
                             "secrets": {"ig_id": p["ig_id"], "page_id": p["page_id"], "page_token": p["page_token"],
                                         "expires_at": sec["expires_at"]}, "meta": {"page": p["page_name"]}})
            for row in rows:
                ex = db.row(c.execute("SELECT * FROM connections WHERE workspace_id=? AND platform=? AND external_id=?",
                                      (st["workspace_id"], row["platform"], row["external_id"])).fetchone())
                row["updated_at"] = db.now()
                row["channel_id"] = st.get("channel_id")
                if ex:
                    db.update(c, "connections", ex["id"], row)
                else:
                    db.insert(c, "connections", {"id": db.new_id(), "workspace_id": st["workspace_id"],
                                                 "created_by": st["user_id"], "created_at": db.now(), **row})
                added.append(row["name"])
        service.log(c, st["workspace_id"], "connection.add", user_id=st["user_id"], detail={"platform": "meta", "name": ", ".join(added)})
    return _done_page("जुड़ गया ✓ " + ", ".join(added))


# ---- publications
def _timing(platform: str, when: str | None, payload: dict) -> tuple[dict, str | None, int]:
    """Scheduled time → platform fields. YouTube: publishAt (native). Facebook: scheduled_publish_time (native).
    Instagram: no API scheduling → the job waits in our queue (run_after). Returns (payload, run_after, link_hours)."""
    from datetime import datetime, timezone
    from ..engine.schedule import _parse
    t = _parse(when)
    if not t or t <= datetime.now(timezone.utc):
        return payload, None, 48
    hours = int((t - datetime.now(timezone.utc)).total_seconds() // 3600) + 48
    iso = t.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    payload = {**payload, "when": iso}
    if platform == "youtube":
        payload["publish_at"] = iso
        payload["privacy"] = "private"
        return payload, None, hours
    if platform == "facebook" and (t - datetime.now(timezone.utc)).total_seconds() > 700:
        payload["scheduled_at"] = int(t.timestamp())
        return payload, None, hours
    return payload, iso, hours


def _yt_category(p: dict, requested: str | None) -> str:
    """Explicit category wins; else 27 (Education) if the brand says so; else 22 (People & Blogs)."""
    c = str(requested or "").strip().lower()
    if c in youtube.CATEGORIES or c.isdigit():
        return c
    b = metadata._brand(p)
    said = " ".join(str(b.get(k) or "") for k in ("yt_category", "category")).strip().lower()
    return "education" if ("education" in said or said == "27" or "शिक्षा" in said) else "people"


def _playlist_id(v: str | None) -> str | None:
    """Accepts a playlist id or a youtube.com/playlist?list=… link."""
    v = (v or "").strip()
    if "list=" in v:
        import urllib.parse
        v = (urllib.parse.parse_qs(urllib.parse.urlparse(v).query).get("list") or [""])[0]
    return v[:64] or None


def _srt_for(p: dict, asset: dict) -> str | None:
    """Captions for YouTube: the render's own sidecar SRT if there is one (exact output timeline),
    else built from the transcript after cuts (and inside the Short's clip window)."""
    sub = db.row(db.conn().execute("SELECT * FROM assets WHERE project_id = ? AND kind = 'subtitle' AND label = ? "
                                   "ORDER BY created_at DESC LIMIT 1", (p["id"], asset.get("label"))).fetchone())
    if sub:
        try:
            txt = storage.abs_path(sub["path"]).read_text(encoding="utf-8")
            if txt.strip():
                return txt
        except OSError:
            pass
    tr = p.get("transcript")
    if not tr:
        return None
    from ..engine.autocut import keep_segments, remap_words, words_of
    from ..engine.captions import build_srt
    dur = float((p.get("meta") or {}).get("duration") or 0)
    edl = p.get("edl") or {"duration": dur, "cuts": []}
    try:
        keep = keep_segments({**edl, "duration": edl.get("duration") or dur})
    except (KeyError, TypeError, ValueError):
        return None
    clip = (asset.get("meta") or {}).get("clip") or {}
    if clip and float(clip.get("end", 0)) > float(clip.get("start", 0)):
        cs, ce = float(clip["start"]), float(clip["end"])
        keep = [(max(a, cs), min(b, ce)) for a, b in keep if b > cs and a < ce]
    words = remap_words(words_of(tr), keep)
    return build_srt(words) if words else None


def youtube_extras(p: dict, asset: dict, data: dict) -> tuple[dict, str | None]:
    """YouTube-only payload fields + the SRT for captions.insert. Blocking (may read the AI pack)."""
    brand = metadata._brand(p)
    extra: dict = {"ai_content": bool(data.get("ai_content", False)),
                   "category": _yt_category(p, data.get("category")),
                   "playlist_id": _playlist_id(data.get("playlist_id")) or _playlist_id(brand.get("yt_playlist_id"))}
    fc = data.get("first_comment")
    if fc is None:  # not sent → the AI pack's pinned comment (empty string = user wants no comment)
        try:
            from ..engine import aipack
            fc = (aipack.get(p) or {}).get("pinned_comment") if p.get("transcript") else None
        except Exception:  # noqa: BLE001
            fc = None
    extra["first_comment"] = str(fc or "").strip()[:2000] or None
    loc = data.get("localizations")
    if isinstance(loc, dict) and loc:
        extra["localizations"] = {str(k)[:10]: {"title": str((v or {}).get("title") or "")[:100],
                                               "description": str((v or {}).get("description") or "")[:5000]}
                                  for k, v in loc.items() if isinstance(v, dict)}
    srt = None
    if data.get("captions", True):
        try:
            srt = _srt_for(p, asset)
        except Exception:  # noqa: BLE001 — no captions is fine, never block a publish on it
            srt = None
    return extra, srt


@require("editor")
async def list_playlists(request: Request, user: dict):
    """The connected channel's playlists for the publish form (playlists.list, 1 unit)."""
    c0 = db.get("connections", request.path_params["conn_id"])
    if not c0 or c0["workspace_id"] != user["workspace_id"] or c0["platform"] != "youtube":
        raise ApiError(404, "connection not found")
    if settings.publish_dry_run or not youtube.configured():
        return ok({"playlists": [], "default": None})

    def work():
        tok, sec = youtube.access_token(c0["secrets"])
        return youtube.list_playlists(tok), sec
    note = None
    items: list = []
    try:
        items, sec = await run_in_threadpool(work)
        if sec != c0["secrets"]:
            with db.tx() as c:
                db.update(c, "connections", c0["id"], {"secrets": sec, "updated_at": db.now()})
    except PublishError as e:
        note = youtube.REAUTH_NOTE if youtube.is_scope_error(e) else str(e)
    ch = db.get("channels", c0.get("channel_id") or "") or {}
    return ok({"playlists": items, "default": ((ch.get("settings") or {}).get("brand") or {}).get("yt_playlist_id"), "note": note})


def pub_view(p: dict) -> dict:
    return {k: p.get(k) for k in ("id", "project_id", "asset_id", "connection_id", "platform", "status", "payload",
                                  "remote_id", "url", "error", "created_at", "finished_at")}


@require("viewer")
async def list_publications(request: Request, user: dict):
    p = own_project(request, user)
    rows = db.rows(db.conn().execute("SELECT * FROM publications WHERE project_id = ? ORDER BY created_at DESC",
                                     (p["id"],)))
    return ok([pub_view(r) for r in rows])


@require("editor")
async def create_publication(request: Request, user: dict):
    p = own_project(request, user)
    if p["status"] != "approved":
        raise ApiError(400, "publish से पहले admin की मंज़ूरी चाहिए")
    data = await body(request)
    need(data, "asset_id", "connection_id", "title")
    asset = db.get("assets", data["asset_id"])
    if not asset or asset["project_id"] != p["id"] or asset["kind"] != "render":
        raise ApiError(404, "output not found")
    conn = db.get("connections", data["connection_id"])
    if not conn or conn["workspace_id"] != user["workspace_id"]:
        raise ApiError(404, "connection not found")
    payload = {"title": str(data["title"])[:100], "description": str(data.get("description") or "")[:5000],
               "tags": [str(t)[:40] for t in (data.get("tags") or [])][:60],
               "privacy": data.get("privacy", "private"), "publish_at": data.get("publish_at") or None,
               "scheduled_at": data.get("scheduled_at") or None, "category": data.get("category", "people"),
               "language": p.get("language") if p.get("language") in ("hi", "en") else None,
               "kind": "video" if asset["meta"].get("width", 0) > asset["meta"].get("height", 0) else "reel"}
    srt = None
    if conn["platform"] == "youtube":
        extra, srt = await run_in_threadpool(youtube_extras, p, asset, data)
        payload.update(extra)
    payload, run_after, link_h = _timing(conn["platform"], data.get("when") or data.get("publish_at"), payload)
    pub = {"id": db.new_id(), "workspace_id": user["workspace_id"], "project_id": p["id"], "asset_id": asset["id"],
           "connection_id": conn["id"], "platform": conn["platform"], "status": "queued", "payload": payload,
           "remote_id": None, "url": None, "error": None, "created_by": user["id"], "created_at": db.now(),
           "finished_at": None}
    # thumbnail studio: the selected 1280×720 thumbnail (auto-made if none) — never the 360p preview still
    thumb_id = await run_in_threadpool(thumbs.publish_thumb_asset_id, p) if conn["platform"] == "youtube" else None
    with db.tx() as c:
        db.insert(c, "publications", pub)
        job = queue.enqueue(c, p["id"], "publish", {
            "publication_id": pub["id"], "platform": conn["platform"], "asset_id": asset["id"],
            "secrets": conn["secrets"], "payload": payload,
            "public_url": f"{settings.public_url}/pub/{make_token(asset['id'], kind='pub', hours=link_h)}" if settings.public_url else None,
            "thumb_asset_id": thumb_id, "captions_srt": srt,
            "dry_run": settings.publish_dry_run})
        service.log(c, user["workspace_id"], "publish.queue", user_id=user["id"], project_id=p["id"],
                    detail={"platform": conn["platform"], "title": payload["title"]})
    return ok({"publication": pub_view(pub), "job": job}, 201)


@require("editor")
async def publish_plan_run(request: Request, user: dict):
    """Queue every selected item of the autopilot publish plan (after approval)."""
    p = own_project(request, user)
    if p["status"] != "approved":
        raise ApiError(400, "पहले मंज़ूरी दें")
    data = await body(request)
    items = data.get("items") or (p.get("meta") or {}).get("publish_plan") or []
    queued = []
    yt = any((db.get("connections", it.get("connection_id") or "") or {}).get("platform") == "youtube" for it in items if it.get("selected", True))
    thumb_id = await run_in_threadpool(thumbs.publish_thumb_asset_id, p) if yt else None
    yt_extra: dict[int, tuple[dict, str | None]] = {}  # computed outside the write transaction (may read the AI pack)
    for i, it in enumerate(items):
        a0, c0 = db.get("assets", it.get("asset_id") or ""), db.get("connections", it.get("connection_id") or "")
        if it.get("selected", True) and a0 and c0 and c0["platform"] == "youtube" and a0["project_id"] == p["id"]:
            yt_extra[i] = await run_in_threadpool(youtube_extras, p, a0, it)
    with db.tx() as c:
        for i, it in enumerate(items):
            if not it.get("selected", True):
                continue
            asset = db.get("assets", it.get("asset_id")); conn = db.get("connections", it.get("connection_id"))
            if not asset or asset["project_id"] != p["id"] or not conn or conn["workspace_id"] != user["workspace_id"]:
                continue
            payload = {"title": str(it.get("title") or p["title"])[:100], "description": str(it.get("description") or "")[:5000],
                       "tags": [str(t)[:40] for t in (it.get("tags") or [])][:60], "privacy": it.get("privacy") or "public",
                       "publish_at": it.get("publish_at") or None, "scheduled_at": it.get("scheduled_at") or None,
                       "category": "people", "language": p.get("language") if p.get("language") in ("hi", "en") else None,
                       "kind": "video" if asset["meta"].get("width", 0) > asset["meta"].get("height", 0) else "reel"}
            extra, srt = yt_extra.get(i, ({}, None))
            payload.update(extra)
            pub = {"id": db.new_id(), "workspace_id": user["workspace_id"], "project_id": p["id"], "asset_id": asset["id"],
                   "connection_id": conn["id"], "platform": conn["platform"], "status": "queued", "payload": payload,
                   "remote_id": None, "url": None, "error": None, "created_by": user["id"], "created_at": db.now(), "finished_at": None}
            payload, run_after, link_h = _timing(conn["platform"], it.get("when") or it.get("publish_at"), payload)
            pub["payload"] = payload
            db.insert(c, "publications", pub)
            queue.enqueue(c, p["id"], "publish", {
                "publication_id": pub["id"], "platform": conn["platform"], "asset_id": asset["id"], "secrets": conn["secrets"],
                "payload": payload, "public_url": f"{settings.public_url}/pub/{make_token(asset['id'], kind='pub', hours=link_h)}" if settings.public_url else None,
                "thumb_asset_id": thumb_id if conn["platform"] == "youtube" else None, "captions_srt": srt,
                "dry_run": settings.publish_dry_run},
                run_after=run_after)
            queued.append(pub["id"])
        service.log(c, user["workspace_id"], "publish.plan", user_id=user["id"], project_id=p["id"], detail={"count": len(queued)})
    return ok({"queued": queued})


@require("editor")
async def suggest_metadata(request: Request, user: dict):
    """Title / description / tags drafted from the transcript (LLM if a key is set, else heuristics)."""
    p = own_project(request, user)
    data = await body(request)
    return ok(metadata.suggest(p, platform=data.get("platform", "youtube"), label=data.get("label")))


async def public_file(request: Request):
    """Signed public link used by Instagram/Facebook to fetch a finished render."""
    data = read_token(request.path_params["token"], kind="pub")
    if not data:
        raise ApiError(404, "link expired")
    a = db.get("assets", data["sub"])
    if not a:
        raise ApiError(404, "not found")
    path = storage.abs_path(a["path"])
    if not path.exists():
        raise ApiError(404, "file missing")
    return FileResponse(path, media_type=a["mime"] or "video/mp4", filename=Path(a["path"]).name)


routes = [
    Route("/connections", list_connections),
    Route("/connections/{conn_id}", delete_connection, methods=["DELETE"]),
    Route("/connections/{conn_id}", move_connection, methods=["PATCH"]),
    Route("/connections/{conn_id}/playlists", list_playlists),
    Route("/connect/{platform}/start", connect_start, methods=["POST"]),
    Route("/connect/youtube/callback", youtube_callback),
    Route("/connect/meta/callback", meta_callback),
    Route("/projects/{project_id}/publications", list_publications),
    Route("/projects/{project_id}/publications", create_publication, methods=["POST"]),
    Route("/projects/{project_id}/metadata", suggest_metadata, methods=["POST"]),
    Route("/projects/{project_id}/publish-plan", publish_plan_run, methods=["POST"]),
]
public_routes = [Route("/pub/{token}", public_file)]
