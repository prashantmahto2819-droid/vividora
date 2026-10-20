"""Trend radar settings + run now + outliers list."""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.routing import Route

from .. import db, radar_job, service
from ..config import settings
from ..engine import radar
from .channels import get_channel
from .deps import ApiError, body, ok, require


@require("viewer")
async def get_radar(request: Request, user: dict):
    ch = get_channel(user["workspace_id"], request.query_params.get("channel"))
    if not ch:
        raise ApiError(404, "channel नहीं मिला")
    rows = db.rows(db.conn().execute(
        "SELECT * FROM trends WHERE workspace_id = ? AND (channel_id = ? OR channel_id IS NULL) ORDER BY score DESC LIMIT 200",
        (user["workspace_id"], ch["id"])))
    outs = [r for r in rows if (r.get("meta") or {}).get("outlier")]
    return ok({"settings": radar.settings_of(ch.get("settings") or {}), "last": (ch.get("settings") or {}).get("radar_last"),
               "outliers": outs[:30], "has_yt_key": bool(settings.yt_api_key)})


@require("admin")
async def put_radar(request: Request, user: dict):
    data = await body(request)
    ch = get_channel(user["workspace_id"], data.get("channel_id"))
    if not ch:
        raise ApiError(404, "channel नहीं मिला")
    new = {k: v for k, v in (data.get("settings") or {}).items() if k in radar.DEFAULT}
    st = ch.get("settings") or {}
    st["radar"] = {**(st.get("radar") or {}), **new}
    with db.tx() as c:
        db.update(c, "channels", ch["id"], {"settings": st, "updated_at": db.now()})
    return ok({"settings": radar.settings_of(st)})


@require("editor")
async def run_radar(request: Request, user: dict):
    data = await body(request)
    ch = get_channel(user["workspace_id"], data.get("channel_id"))
    if not ch:
        raise ApiError(404, "channel नहीं मिला")
    r = await run_in_threadpool(lambda: radar_job.run_channel(user["workspace_id"], ch, send=bool(data.get("send"))))
    return ok({"trends": r["trends"], "outliers": r["outliers"][:12], "ideas": r["ideas"]})


routes = [
    Route("/radar", get_radar),
    Route("/radar", put_radar, methods=["PUT"]),
    Route("/radar/run", run_radar, methods=["POST"]),
]
