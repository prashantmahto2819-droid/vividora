"""Trend radar, ideas board, scripts, inbound WhatsApp approvals."""

from __future__ import annotations

import hmac
import re

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.routing import Route

from .. import db, notify, service
from ..config import settings
from ..engine import planner, trends
from .deps import ApiError, body, need, ok, require

IDEA_STATUS = ("new", "approved", "recorded", "done", "dropped")


def _idea(i: dict) -> dict:
    return i


@require("viewer")
async def list_trends(request: Request, user: dict):
    rows = db.rows(db.conn().execute(
        "SELECT * FROM trends WHERE workspace_id = ? ORDER BY score DESC LIMIT 200", (user["workspace_id"],)))
    last = db.conn().execute("SELECT MAX(fetched_at) FROM trends WHERE workspace_id = ?", (user["workspace_id"],)).fetchone()[0]
    return ok({"trends": rows, "fetched_at": last,
               "setup": {"yt_api_key": bool(settings.yt_api_key), "region": settings.trend_region,
                         "watch_channels": settings.watch_channels, "llm": bool(planner.llm.available())}})


@require("editor")
async def refresh_trends(request: Request, user: dict):
    rows = await run_in_threadpool(trends.refresh_all)
    errors = [r["title"] for r in rows if r.get("meta", {}).get("error")]
    rows = [r for r in rows if not r.get("meta", {}).get("error")]
    now = db.now()
    with db.tx() as c:
        c.execute("DELETE FROM trends WHERE workspace_id = ?", (user["workspace_id"],))
        for r in rows:
            db.insert(c, "trends", {"id": db.new_id(), "workspace_id": user["workspace_id"], "source": r["source"],
                                    "title": r["title"][:300], "url": r.get("url"), "score": float(r.get("score") or 0),
                                    "meta": r.get("meta") or {}, "fetched_at": now})
        service.log(c, user["workspace_id"], "trends.refresh", user_id=user["id"], detail={"count": len(rows)})
    return ok({"count": len(rows), "errors": errors})


@require("viewer")
async def list_ideas(request: Request, user: dict):
    q = "SELECT * FROM ideas WHERE workspace_id = ? AND status != 'dropped'"
    args: list = [user["workspace_id"]]
    if request.query_params.get("channel"):
        q += " AND (channel_id = ? OR channel_id IS NULL)"
        args.append(request.query_params["channel"])
    return ok(db.rows(db.conn().execute(q + " ORDER BY updated_at DESC LIMIT 300", args)))


@require("editor")
async def generate_ideas(request: Request, user: dict):
    data = await body(request)
    fmt = data.get("format") if data.get("format") in planner.FORMATS else "short"
    count = max(1, min(12, int(data.get("count", 6))))
    rows = db.rows(db.conn().execute("SELECT * FROM trends WHERE workspace_id = ? ORDER BY score DESC LIMIT 60",
                                     (user["workspace_id"],)))
    topics = trends.topics_summary(rows)
    recent = [r["title"] for r in db.rows(db.conn().execute(
        "SELECT title FROM ideas WHERE workspace_id = ? ORDER BY created_at DESC LIMIT 20", (user["workspace_id"],)))]
    recent += [r["title"] for r in db.rows(db.conn().execute(
        "SELECT title FROM projects WHERE workspace_id = ? ORDER BY created_at DESC LIMIT 20", (user["workspace_id"],)))]
    from .channels import get_channel
    ch = get_channel(user["workspace_id"], data.get("channel_id"))
    lang = data.get("language") or (ch or {}).get("language") or "hi"
    niche = (ch or {}).get("niche") or ""
    topic = (data.get("topic") or "").strip() or None
    if niche and not topic:
        topic = f"(channel niche: {niche})"
    ideas = await run_in_threadpool(lambda: planner.ideas(topics, count=count, fmt=fmt, language=lang if lang != "auto" else "hi",
                                                          topic=topic, recent_titles=recent))
    out = []
    with db.tx() as c:
        for i in ideas:
            row = {"id": db.new_id(), "workspace_id": user["workspace_id"], "title": i["title"], "hook": i.get("hook"),
                   "angle": i.get("angle"), "outline": i.get("outline"), "script": None, "format": fmt, "status": "new",
                   "source": i.get("source"), "project_id": None, "due_at": None, "meta": {}, "created_by": user["id"],
                   "channel_id": (ch or {}).get("id"), "created_at": db.now(), "updated_at": db.now()}
            db.insert(c, "ideas", row)
            out.append(row)
        service.log(c, user["workspace_id"], "ideas.generate", user_id=user["id"], detail={"count": len(out)})
    return ok(out, 201)


@require("editor")
async def create_idea(request: Request, user: dict):
    data = await body(request)
    need(data, "title")
    row = {"id": db.new_id(), "workspace_id": user["workspace_id"], "title": str(data["title"])[:120],
           "hook": data.get("hook"), "angle": data.get("angle"), "outline": data.get("outline"), "script": data.get("script"),
           "format": data.get("format") if data.get("format") in planner.FORMATS else "short", "status": "new",
           "source": "manual", "project_id": None, "due_at": data.get("due_at"), "meta": {}, "created_by": user["id"],
           "channel_id": data.get("channel_id"), "created_at": db.now(), "updated_at": db.now()}
    with db.tx() as c:
        db.insert(c, "ideas", row)
    return ok(row, 201)


def _own_idea(request: Request, user: dict) -> dict:
    i = db.get("ideas", request.path_params["idea_id"])
    if not i or i["workspace_id"] != user["workspace_id"]:
        raise ApiError(404, "idea not found")
    return i


@require("editor")
async def update_idea(request: Request, user: dict):
    i = _own_idea(request, user)
    data = await body(request)
    ch = {}
    for k in ("title", "hook", "angle", "outline", "script", "due_at", "project_id"):
        if k in data:
            ch[k] = (str(data[k])[:6000] if data[k] is not None else None)
    if data.get("status") in IDEA_STATUS:
        ch["status"] = data["status"]
    if data.get("format") in planner.FORMATS:
        ch["format"] = data["format"]
    if ch:
        ch["updated_at"] = db.now()
        with db.tx() as c:
            db.update(c, "ideas", i["id"], ch)
    return ok(db.get("ideas", i["id"]))


@require("editor")
async def write_script(request: Request, user: dict):
    i = _own_idea(request, user)
    data = await body(request)
    secs = int(data["seconds"]) if data.get("seconds") else None
    r = await run_in_threadpool(lambda: planner.script(i, fmt=i["format"], language=data.get("language") or "hi",
                                                       target_seconds=secs))
    with db.tx() as c:
        db.update(c, "ideas", i["id"], {"script": r["script"], "meta": {**i["meta"], "shotlist": r.get("shotlist"),
                                                                        "overlays": r.get("overlays"),
                                                                        "title_options": r.get("title_options"),
                                                                        "script_source": r.get("source")},
                                        "updated_at": db.now()})
    return ok({**r, "idea": db.get("ideas", i["id"])})


@require("viewer")
async def notify_status(request: Request, user: dict):
    return ok({"enabled": notify.enabled(), "to": settings.notify_to[-4:] if settings.notify_to else None,
               "inbound": bool(settings.notify_inbound_secret)})


@require("admin")
async def notify_test(request: Request, user: dict):
    if not notify.enabled():
        raise ApiError(400, ".env में NOTIFY_URL और NOTIFY_TO सेट करें")
    from starlette.concurrency import run_in_threadpool
    good, info = await run_in_threadpool(notify.send_now, "✅ Vividora जुड़ा हुआ है — यह test message है।")
    if not good:
        hint = ("token गलत है — Relay में नई API key बनाकर NOTIFY_TOKEN में डालें" if " 401" in " " + info or " 403" in " " + info
                else "NOTIFY_URL में number का नाम जाँचें (Relay → Numbers)" if " 404" in " " + info else "Relay चालू है? NOTIFY_URL सही है?")
        raise ApiError(502, f"WhatsApp नहीं गया ({info}) — {hint}")
    return ok({"info": info})


def _flatten_inbound(data: dict) -> dict:
    """Gateways wrap messages differently ({data: {...}}, {message: {text}}, Baileys-style keys…) → one flat dict."""
    d = data
    for k in ("data", "payload", "event"):
        if isinstance(d.get(k), dict) and not d.get("text"):
            d = {**d, **d[k]}
    msg = d.get("message")
    if isinstance(msg, dict):
        d = {**d, "text": d.get("text") or msg.get("text") or msg.get("conversation") or msg.get("body") or msg.get("caption") or "",
             "media": d.get("media") or msg.get("media") or msg.get("audio")}
        if isinstance(msg.get("extendedTextMessage"), dict):
            d["text"] = d["text"] or msg["extendedTextMessage"].get("text", "")
    if isinstance(d.get("text"), dict):
        d["text"] = d["text"].get("body") or ""
    d["text"] = d.get("text") or d.get("body") or (msg if isinstance(msg, str) else "") or ""
    d["from"] = d.get("from_phone") or d.get("chat_phone") or d.get("from") or d.get("sender") or d.get("phone") or d.get("remoteJid") or ((d.get("key") or {}).get("remoteJid") if isinstance(d.get("key"), dict) else "") or ""
    d["from_me"] = bool(d.get("fromMe") or d.get("from_me") or ((d.get("key") or {}).get("fromMe") if isinstance(d.get("key"), dict) else False))
    return d


async def inbound_info(request: Request):
    """Opening the link in a browser: say it is alive (no secrets)."""
    return ok({"alive": True, "method": "POST", "configured": bool(settings.notify_inbound_secret),
               "how": "Vivid Relay webhook: POST JSON {from, text} या voice note {from, audio_base64 | audio_url}; header X-Hook-Secret"})


async def inbound(request: Request):
    """WhatsApp reply → approval. Body: {"from": "...", "text": "ok 7F3A"}."""
    auth = request.headers.get("authorization", "")
    secret = request.headers.get("x-hook-secret") or (auth[7:] if auth.lower().startswith("bearer ") else "") or request.query_params.get("secret", "")
    if not settings.notify_inbound_secret or not hmac.compare_digest(secret, settings.notify_inbound_secret):
        raise ApiError(401, "bad secret")
    data = _flatten_inbound(await body(request))
    if data.get("from_me"):
        return ok({"matched": False, "ignored": "own message"})
    # Vivid Relay sends every event to the webhook; only real chat messages matter here
    if data.get("event") not in (None, "", "message") or data.get("chat_type") in ("group", "channel"):
        return ok({"matched": False, "ignored": "event"})
    media = data.get("media") if isinstance(data.get("media"), dict) else {}
    has_audio = bool(data.get("audio_base64") or data.get("audio_url") or media.get("url") or media.get("base64"))
    if data.get("type") in ("voice", "audio") and not has_audio:
        notify.send("🎤 voice note अभी gateway से audio के साथ नहीं आता — कृपया लिखकर भेजें (जैसे “status बताओ”)।")
        return ok({"matched": False, "voice": "no audio"})
    text = str(data.get("text") or data.get("message") or "").strip()
    m = re.search(r"\b(ok|okay|approve|हाँ|ha|yes)\s+([0-9a-f]{4})\b", text, re.I)
    if not m:
        # not an approval → a command (typed or a voice note). Publishing still needs "ok CODE".
        allowed = [x.strip()[-10:] for x in str(settings.notify_to or "").split(",") if x.strip()]
        sender = re.sub(r"\D", "", str(data.get("from") or ""))[-10:]
        if allowed and sender and sender not in allowed:
            return ok({"matched": False, "ignored": "sender"})
        audio = data.get("audio_base64") or data.get("audio_url") or ((data.get("media") or {}) if isinstance(data.get("media"), dict) else {}).get("url") \
            or ((data.get("media") or {}) if isinstance(data.get("media"), dict) else {}).get("base64")
        if audio:
            from .. import voice_in
            text = await run_in_threadpool(voice_in.transcribe_any, audio)
            if not text:
                notify.send("🎤 voice note समझ नहीं आया — दोबारा भेजें या लिखकर भेजें।")
                return ok({"matched": False, "voice": "failed"})
        if not text:
            return ok({"matched": False})
        ws = db.row(db.conn().execute("SELECT id FROM workspaces ORDER BY created_at LIMIT 1").fetchone())
        if not ws:
            return ok({"matched": False})
        from .. import command_exec
        r = await run_in_threadpool(command_exec.run, ws["id"], None, text[:500], None, via="whatsapp")
        notify.send(("🎤 “" + text[:80] + "”\n" if audio else "") + (r.get("reply") or "✅"))
        return ok({"matched": False, "command": r.get("intent")})
    code = m.group(2).lower()
    rows = db.rows(db.conn().execute("SELECT * FROM projects WHERE status = 'review_output'"))
    p = next((r for r in rows if r["id"].startswith(code)), None)
    if not p:
        notify.send(f"कोई वीडियो code {code.upper()} के साथ मंज़ूरी का इंतज़ार नहीं कर रहा।")
        return ok({"matched": False})
    admin = db.row(db.conn().execute("SELECT * FROM users WHERE workspace_id = ? AND role = 'admin' AND active = 1 "
                                     "ORDER BY created_at LIMIT 1", (p["workspace_id"],)).fetchone())
    with db.tx() as c:
        db.update(c, "projects", p["id"], {"status": "approved", "status_note": "WhatsApp से मंज़ूर",
                                           "approved_by": admin["id"] if admin else None, "approved_at": db.now(),
                                           "updated_at": db.now()})
        service.log(c, p["workspace_id"], "project.approve", user_id=admin["id"] if admin else None,
                    project_id=p["id"], detail={"via": "whatsapp", "from": str(data.get("from") or "")[-6:]})
    notify.send(f"✅ “{p['title']}” मंज़ूर। Publish dashboard से करें: {notify.project_link(p['id'])}")
    return ok({"matched": True, "project_id": p["id"]})


REF_KINDS = ("audio", "video", "effect", "caption", "hook", "other")


@require("viewer")
async def list_refs(request: Request, user: dict):
    q = "SELECT * FROM refs WHERE workspace_id = ?"
    args: list = [user["workspace_id"]]
    pid = request.query_params.get("project_id")
    if pid:
        q += " AND (project_id = ? OR project_id IS NULL)"
        args.append(pid)
    return ok(db.rows(db.conn().execute(q + " ORDER BY created_at DESC LIMIT 300", args)))


@require("editor")
async def create_ref(request: Request, user: dict):
    data = await body(request)
    if not (data.get("url") or data.get("note")):
        raise ApiError(422, "link या note लिखें")
    row = {"id": db.new_id(), "workspace_id": user["workspace_id"], "project_id": data.get("project_id") or None,
           "channel_id": data.get("channel_id") or None,
           "kind": data.get("kind") if data.get("kind") in REF_KINDS else "other", "url": (data.get("url") or "")[:500] or None,
           "note": (data.get("note") or "")[:2000] or None, "created_by": user["id"], "created_at": db.now()}
    with db.tx() as c:
        db.insert(c, "refs", row)
    return ok(row, 201)


@require("editor")
async def delete_ref(request: Request, user: dict):
    r = db.get("refs", request.path_params["ref_id"])
    if not r or r["workspace_id"] != user["workspace_id"]:
        raise ApiError(404, "not found")
    with db.tx() as c:
        c.execute("DELETE FROM refs WHERE id = ?", (r["id"],))
    return ok()


routes = [
    Route("/refs", list_refs),
    Route("/refs", create_ref, methods=["POST"]),
    Route("/refs/{ref_id}", delete_ref, methods=["DELETE"]),
    Route("/trends", list_trends),
    Route("/trends/refresh", refresh_trends, methods=["POST"]),
    Route("/ideas", list_ideas),
    Route("/ideas", create_idea, methods=["POST"]),
    Route("/ideas/generate", generate_ideas, methods=["POST"]),
    Route("/ideas/{idea_id}", update_idea, methods=["PATCH"]),
    Route("/ideas/{idea_id}/script", write_script, methods=["POST"]),
    Route("/notify", notify_status),
    Route("/notify/test", notify_test, methods=["POST"]),
    Route("/hooks/inbound", inbound, methods=["POST"]),
    Route("/hooks/inbound", inbound_info, methods=["GET"]),
]
