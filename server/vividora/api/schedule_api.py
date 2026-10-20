"""Posting schedule per channel + calendar of scheduled/published posts."""

from __future__ import annotations

from starlette.requests import Request
from starlette.routing import Route

from .. import db, service
from ..engine import schedule as sch
from .channels import get_channel
from .deps import ApiError, body, ok, own_project, require


@require("viewer")
async def get_schedule(request: Request, user: dict):
    ch = get_channel(user["workspace_id"], request.query_params.get("channel"))
    if not ch:
        raise ApiError(404, "channel नहीं मिला")
    s = sch.settings_of(ch.get("settings") or {})
    # suggestion from own analytics (views per day by posting hour)
    rows = db.rows(db.conn().execute(
        "SELECT p.finished_at, MAX(s.views) AS views FROM publications p JOIN stats s ON s.publication_id = p.id "
        "WHERE p.workspace_id = ? AND p.remote_id IS NOT NULL GROUP BY p.id", (user["workspace_id"],)))
    vids = [{"published": r["finished_at"], "views": r["views"]} for r in rows if r.get("finished_at")]
    return ok({"channel_id": ch["id"], "schedule": s, "defaults": sch.DEFAULT, "days": sch.DAYS,
               "suggested": sch.best_slots(vids, s.get("timezone") or "Asia/Kolkata")})


@require("admin")
async def put_schedule(request: Request, user: dict):
    data = await body(request)
    ch = get_channel(user["workspace_id"], data.get("channel_id") or request.query_params.get("channel"))
    if not ch:
        raise ApiError(404, "channel नहीं मिला")
    new = {k: v for k, v in (data.get("schedule") or {}).items() if k in sch.DEFAULT}
    st = ch.get("settings") or {}
    st["schedule"] = {**(st.get("schedule") or {}), **new}
    with db.tx() as c:
        db.update(c, "channels", ch["id"], {"settings": st, "updated_at": db.now()})
        service.log(c, user["workspace_id"], "schedule.update", user_id=user["id"], detail={"channel": ch["id"]})
    return ok({"schedule": sch.settings_of(st)})


@require("viewer")
async def calendar(request: Request, user: dict):
    """Scheduled + published posts between from/to (ISO dates), for the calendar page."""
    q = request.query_params
    rows = db.rows(db.conn().execute(
        "SELECT p.id, p.project_id, p.platform, p.status, p.payload, p.url, p.created_at, p.finished_at, pr.title AS project_title, "
        "pr.channel_id, a.label FROM publications p JOIN projects pr ON pr.id = p.project_id LEFT JOIN assets a ON a.id = p.asset_id "
        "WHERE p.workspace_id = ? ORDER BY p.created_at DESC LIMIT 500", (user["workspace_id"],)))
    ch = q.get("channel")
    out = []
    for r in rows:
        if ch and r.get("channel_id") not in (ch, None):
            continue
        pl = r.get("payload") or {}
        when = pl.get("when") or pl.get("publish_at") or r.get("finished_at") or r.get("created_at")
        if q.get("from") and str(when) < q["from"]:
            continue
        if q.get("to") and str(when) > q["to"] + "T23:59:59":
            continue
        out.append({"id": r["id"], "project_id": r["project_id"], "project_title": r["project_title"], "platform": r["platform"],
                    "label": r.get("label"), "status": r["status"], "title": pl.get("title"), "when": when, "url": r.get("url"),
                    "scheduled": bool(pl.get("when"))})
    out.sort(key=lambda x: str(x["when"]))
    return ok(out)


@require("editor")
async def reschedule_plan(request: Request, user: dict):
    """(Re)compute posting times for a project's publish plan from the channel's slots."""
    p = own_project(request, user)
    data = await body(request)
    items = data.get("items") or (p.get("meta") or {}).get("publish_plan") or []
    ch = service.project_channel(p)
    s = sch.settings_of(ch.get("settings") or {})
    if data.get("now"):
        for it in items:
            it.pop("when", None)
    else:
        items = sch.assign(items, s, booked=service.booked_times(p["workspace_id"], ch.get("id")))
    with db.tx() as c:
        cur = db.get("projects", p["id"])
        db.update(c, "projects", p["id"], {"meta": {**(cur.get("meta") or {}), "publish_plan": items}})
    return ok({"items": items})


routes = [
    Route("/schedule", get_schedule),
    Route("/schedule", put_schedule, methods=["PUT"]),
    Route("/schedule/calendar", calendar),
    Route("/projects/{project_id}/publish-plan/schedule", reschedule_plan, methods=["POST"]),
]
