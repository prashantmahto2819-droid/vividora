"""Runs the daily trend radar for every channel (from the hourly scheduler) or on demand."""

from __future__ import annotations

import logging
from datetime import datetime

from . import db, notify, service
from .config import settings
from .engine import planner, radar, trends

log = logging.getLogger("vividora.radar")


def run_channel(workspace_id: str, ch: dict, *, send: bool = True) -> dict:
    rd = radar.settings_of(ch.get("settings") or {})
    rows = radar.collect(rd)
    outs = radar.outliers(rows, float(rd.get("outlier_x", 2.0)))
    out_urls = {r.get("url") for r in outs}
    now = db.now()
    with db.tx() as c:
        c.execute("DELETE FROM trends WHERE workspace_id = ? AND (channel_id = ? OR channel_id IS NULL)", (workspace_id, ch["id"]))
        for r in rows:
            meta = r.get("meta") or {}
            if r.get("url") in out_urls:
                meta = {**meta, "outlier": True, **next((o["meta"] for o in outs if o.get("url") == r.get("url")), {})}
            db.insert(c, "trends", {"id": db.new_id(), "workspace_id": workspace_id, "source": r["source"], "title": r["title"][:300],
                                    "url": r.get("url"), "score": float(r.get("score") or 0) * (3 if meta.get("outlier") else 1),
                                    "meta": meta, "fetched_at": now, "channel_id": ch["id"]})
    topics = [f"{o['title']} ({o['meta'].get('channel', '')}, {o['meta'].get('views_per_day', 0)}/day)" for o in outs] + trends.topics_summary(rows)
    recent = [r[0] for r in db.conn().execute("SELECT title FROM projects WHERE workspace_id = ? ORDER BY created_at DESC LIMIT 20", (workspace_id,))]
    ideas = planner.ideas(topics[:30], count=int(rd.get("ideas", 5)), fmt="short", language=ch.get("language") or "hi",
                          topic=f"(channel niche: {ch.get('niche') or 'motivation'})", recent_titles=recent)
    saved = []
    with db.tx() as c:
        for i in ideas:
            row = {"id": db.new_id(), "workspace_id": workspace_id, "title": i["title"], "hook": i.get("hook"), "angle": i.get("angle"),
                   "outline": i.get("outline"), "script": None, "format": "short", "status": "new", "source": "radar",
                   "project_id": None, "due_at": None, "meta": {"radar": now[:10]}, "created_by": None, "channel_id": ch["id"],
                   "created_at": db.now(), "updated_at": db.now()}
            db.insert(c, "ideas", row)
            saved.append(row)
        st = ch.get("settings") or {}
        st["radar_last"] = now
        db.update(c, "channels", ch["id"], {"settings": st})
        service.log(c, workspace_id, "radar.run", detail={"channel": ch["id"], "trends": len(rows), "outliers": len(outs), "ideas": len(saved)})
    if send and notify.enabled():
        link = f"{settings.public_url}/#/plan" if settings.public_url else ""
        notify.send(radar.digest_text(ch.get("name") or "Channel", outs, saved, link))
    return {"trends": len(rows), "outliers": outs, "ideas": saved}


def due_channels(now_local_hour: int, today: str) -> list[tuple[str, dict]]:
    out = []
    for ch in db.rows(db.conn().execute("SELECT * FROM channels")):
        rd = radar.settings_of(ch.get("settings") or {})
        last = str((ch.get("settings") or {}).get("radar_last") or "")
        if rd.get("daily") and int(rd.get("hour", 8)) == now_local_hour and not last.startswith(today):
            out.append((ch["workspace_id"], ch))
    return out


def tick() -> None:
    """Called hourly; runs radars whose hour has come (Asia/Kolkata unless the schedule says otherwise)."""
    from .engine.schedule import _tz
    loc = datetime.now(_tz("Asia/Kolkata"))
    for ws, ch in due_channels(loc.hour, datetime.utcnow().strftime("%Y-%m-%d")):
        try:
            run_channel(ws, ch)
        except Exception as e:  # noqa: BLE001
            log.warning("radar %s failed: %s", ch.get("id"), e)
