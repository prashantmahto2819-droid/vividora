"""Published-video stats + what-works learning + apply recommendations."""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.routing import Route

from .. import db, service
from ..engine import analytics
from ..engine.presets import caption_styles
from ..publish.http import PublishError
from .deps import ApiError, ok, require


def _rows(workspace_id: str, channel_id: str | None = None) -> list[dict]:
    cn = db.conn()
    q = ("SELECT p.*, pr.title AS project_title, pr.settings AS project_settings, pr.channel_id AS channel_id, a.meta AS asset_meta, a.label AS asset_label "
         "FROM publications p JOIN projects pr ON pr.id = p.project_id LEFT JOIN assets a ON a.id = p.asset_id "
         "WHERE p.workspace_id = ? AND p.status = 'done' AND p.remote_id IS NOT NULL")
    args: list = [workspace_id]
    if channel_id:
        q += " AND pr.channel_id = ?"
        args.append(channel_id)
    pubs = db.rows(cn.execute(q + " ORDER BY p.finished_at DESC", args))
    out = []
    for p in pubs:
        import json
        st = db.row(cn.execute("SELECT * FROM stats WHERE publication_id = ? ORDER BY fetched_at DESC LIMIT 1", (p["id"],)).fetchone())
        meta = p["asset_meta"] if isinstance(p["asset_meta"], dict) else json.loads(p["asset_meta"] or "{}")
        rs = (p["project_settings"] if isinstance(p["project_settings"], dict) else json.loads(p["project_settings"] or "{}")).get("render", {})
        published_at = (st or {}).get("extra", {}).get("published") or p["finished_at"]
        out.append({"id": p["id"], "project_id": p["project_id"], "title": p["payload"].get("title") or p["project_title"],
                    "platform": p["platform"], "url": p["url"], "label": p["asset_label"], "published_at": published_at,
                    "views": (st or {}).get("views", 0), "likes": (st or {}).get("likes", 0), "comments": (st or {}).get("comments", 0),
                    "fetched_at": (st or {}).get("fetched_at"), "features": analytics.features(meta, rs, published_at)})
    # YouTube Analytics cache (retention curve, avg % viewed, CTR) — see retention_job
    from ..retention_job import cached
    yta = cached([r["id"] for r in out if r["platform"] == "youtube"])
    for r in out:
        y = yta.get(r["id"])
        if y:
            m = y.get("metrics") or {}
            r["yta"] = {"metrics": {k: v for k, v in m.items() if not k.startswith("_")}, "unavailable": m.get("_unavailable") or [],
                        "retention": y.get("retention") or [], "drop": y.get("dropinfo"), "error": y.get("error"),
                        "fetched_at": y.get("fetched_at")}
    return out


def _learn(rows: list[dict]) -> dict:
    """What-works learning + retention notes (biggest drop, hook) as plain-language lessons."""
    L = analytics.learn(rows)
    L["notes"] = analytics.retention_notes(rows)
    return L


@require("viewer")
async def overview(request: Request, user: dict):
    from .channels import get_channel
    ch = get_channel(user["workspace_id"], request.query_params.get("channel"))
    rows = _rows(user["workspace_id"], ch["id"] if ch else None)
    return ok({"videos": rows, "learn": _learn(rows), "channel": ch["id"] if ch else None,
               "defaults": ((ch or {}).get("settings") or {}).get("render_defaults", {})})


@require("editor")
async def refresh(request: Request, user: dict):
    cn = db.conn()
    pubs = db.rows(cn.execute("SELECT * FROM publications WHERE workspace_id = ? AND status = 'done' AND remote_id IS NOT NULL",
                              (user["workspace_id"],)))
    conns = {c["id"]: c for c in db.rows(cn.execute("SELECT * FROM connections WHERE workspace_id = ?", (user["workspace_id"],)))}

    def work() -> tuple[int, list[str]]:
        n, errors = 0, []
        yt = [p for p in pubs if p["platform"] == "youtube"]
        results: dict[str, dict] = {}
        if yt:
            sec = next((conns[p["connection_id"]]["secrets"] for p in yt if p["connection_id"] in conns), None)
            try:
                got = analytics.yt_stats([p["remote_id"] for p in yt], sec)
                for p in yt:
                    if p["remote_id"] in got:
                        results[p["id"]] = got[p["remote_id"]]
            except PublishError as e:
                errors.append(f"YouTube: {e}")
        for p in pubs:
            if p["platform"] in ("instagram", "facebook") and p["connection_id"] in conns:
                tok = conns[p["connection_id"]]["secrets"].get("page_token")
                try:
                    results[p["id"]] = (analytics.ig_stats if p["platform"] == "instagram" else analytics.fb_stats)(p["remote_id"], tok)
                except PublishError as e:
                    errors.append(f"{p['platform']}: {e}")
        with db.tx() as c:
            for pid, st in results.items():
                db.insert(c, "stats", {"publication_id": pid, "fetched_at": db.now(), "views": st.get("views", 0),
                                       "likes": st.get("likes", 0), "comments": st.get("comments", 0),
                                       "extra": {k: v for k, v in st.items() if k not in ("views", "likes", "comments")}})
                n += 1
            service.log(c, user["workspace_id"], "analytics.refresh", user_id=user["id"], detail={"count": n})
        # retention / watch time / CTR (YouTube Analytics API) — cached, at most every 6 h per video
        from .. import retention_job
        try:
            rr = retention_job.refresh(user["workspace_id"])
            errors += rr["errors"][:5]
        except Exception as e:  # noqa: BLE001
            errors.append(f"retention: {e}")
        return n, errors

    n, errors = await run_in_threadpool(work)
    return ok({"updated": n, "errors": errors})


@require("admin")
async def apply_defaults(request: Request, user: dict):
    """Turn the recommendation into the workspace's default render settings for new projects."""
    from .channels import get_channel
    ch = get_channel(user["workspace_id"], request.query_params.get("channel"))
    rows = _rows(user["workspace_id"], ch["id"] if ch else None)
    rec = analytics.learn(rows).get("recommend", {})
    defaults: dict = {}
    if rec.get("caption_style") in caption_styles():
        defaults["caption_style"] = rec["caption_style"]
    eff: dict = {}
    if rec.get("zoom"):
        eff["zoom"] = {"enabled": rec["zoom"] == "on", "strength": 1.0}
    if rec.get("look"):
        eff["look"] = rec["look"]
    if eff:
        defaults["effects"] = eff
    with db.tx() as c:
        if ch:
            db.update(c, "channels", ch["id"], {"settings": {**(ch.get("settings") or {}), "render_defaults": defaults, "recommend": rec},
                                                "updated_at": db.now()})
        service.log(c, user["workspace_id"], "analytics.apply", user_id=user["id"], detail=defaults)
    return ok({"defaults": defaults, "recommend": rec})


routes = [
    Route("/analytics", overview),
    Route("/analytics/refresh", refresh, methods=["POST"]),
    Route("/analytics/apply", apply_defaults, methods=["POST"]),
]
