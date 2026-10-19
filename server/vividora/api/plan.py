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
    rows = db.rows(db.conn().execute(
        "SELECT * FROM ideas WHERE workspace_id = ? AND status != 'dropped' ORDER BY updated_at DESC LIMIT 300",
        (user["workspace_id"],)))
    return ok(rows)


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
    lang = data.get("language") or "hi"
    ideas = await run_in_threadpool(lambda: planner.ideas(topics, count=count, fmt=fmt, language=lang,
                                                          topic=(data.get("topic") or "").strip() or None, recent_titles=recent))
    out = []
    with db.tx() as c:
        for i in ideas:
            row = {"id": db.new_id(), "workspace_id": user["workspace_id"], "title": i["title"], "hook": i.get("hook"),
                   "angle": i.get("angle"), "outline": i.get("outline"), "script": None, "format": fmt, "status": "new",
                   "source": i.get("source"), "project_id": None, "due_at": None, "meta": {}, "created_by": user["id"],
                   "created_at": db.now(), "updated_at": db.now()}
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
           "created_at": db.now(), "updated_at": db.now()}
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
    notify.send("✅ Vividora जुड़ा हुआ है — यह test message है।")
    return ok()


async def inbound(request: Request):
    """WhatsApp reply → approval. Body: {"from": "...", "text": "ok 7F3A"}."""
    secret = request.headers.get("x-hook-secret", "")
    if not settings.notify_inbound_secret or not hmac.compare_digest(secret, settings.notify_inbound_secret):
        raise ApiError(401, "bad secret")
    data = await body(request)
    text = str(data.get("text") or data.get("message") or "").strip()
    m = re.search(r"\b(ok|okay|approve|हाँ|ha|yes)\s+([0-9a-f]{4})\b", text, re.I)
    if not m:
        return ok({"matched": False})
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
]
