"""YouTube Analytics cache: retention curve, watch time and CTR per published YouTube video.

Results live in the `yt_analytics` table (one row per publication). A video is fetched
at most every 6 h (MIN_AGE_H), whoever asks. The hourly scheduler calls tick(), which
re-fetches videos published in the last 30 days once their cache is a day old — i.e.
a daily refresh. Read-only: nothing here changes anything on YouTube.

Quota: the YouTube Analytics API has its own quota (separate from the Data API's
10 000 units), each reports.query is cheap; we make ≤ 4 queries per video.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from . import db
from .engine import analytics
from .publish import youtube
from .publish.http import PublishError

log = logging.getLogger("vividora.retention")

MIN_AGE_H = 6        # never ask Google about the same video more often than this
DAILY_AGE_H = 23     # scheduler: once a day
RECENT_DAYS = 30     # scheduler: only recently published videos keep changing


def _age_h(ts: str | None) -> float:
    if not ts:
        return 1e9
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(ts.replace("Z", "+00:00"))).total_seconds() / 3600
    except ValueError:
        return 1e9


def cached(pub_ids: list[str]) -> dict[str, dict]:
    if not pub_ids:
        return {}
    q = ",".join("?" for _ in pub_ids)
    return {r["publication_id"]: r for r in db.rows(db.conn().execute(
        f"SELECT * FROM yt_analytics WHERE publication_id IN ({q})", pub_ids))}


def _save(pub_id: str, video_id: str, data: dict | None, error: str | None) -> None:
    with db.tx() as c:
        if data is None:  # keep the last good numbers, just note the error and the attempt time
            c.execute("INSERT INTO yt_analytics (publication_id, video_id, fetched_at, error) VALUES (?,?,?,?) "
                      "ON CONFLICT(publication_id) DO UPDATE SET fetched_at = excluded.fetched_at, error = excluded.error",
                      (pub_id, video_id, db.now(), error))
            return
        c.execute("INSERT OR REPLACE INTO yt_analytics (publication_id, video_id, fetched_at, metrics, retention, dropinfo, error) "
                  "VALUES (?,?,?,?,?,?,?)",
                  (pub_id, video_id, db.now(), db.enc({**data["metrics"], "_unavailable": data.get("unavailable") or []}),
                   db.enc(data["retention"]), db.enc(data.get("drop")) if data.get("drop") else None, error))


def _mark_reauth(conn_id: str, flag: bool) -> None:
    cn = db.get("connections", conn_id)
    if cn and bool((cn.get("meta") or {}).get("needs_reauth")) != flag:
        with db.tx() as c:
            db.update(c, "connections", conn_id, {"meta": {**(cn.get("meta") or {}), "needs_reauth": flag}})


def refresh(workspace_id: str | None = None, *, max_age_h: float = MIN_AGE_H, recent_days: int | None = None) -> dict:
    """Fetch analytics for published YouTube videos whose cache is older than max_age_h (≥ 6 h)."""
    max_age_h = max(MIN_AGE_H, max_age_h)
    q = ("SELECT p.id, p.remote_id, p.connection_id, p.finished_at, p.workspace_id, a.meta AS asset_meta FROM publications p "
         "LEFT JOIN assets a ON a.id = p.asset_id "
         "WHERE p.platform = 'youtube' AND p.status = 'done' AND p.remote_id IS NOT NULL AND p.remote_id != 'dry-run'")
    args: list = []
    if workspace_id:
        q += " AND p.workspace_id = ?"
        args.append(workspace_id)
    if recent_days:
        q += " AND p.finished_at >= ?"
        args.append((datetime.now(timezone.utc) - timedelta(days=recent_days)).isoformat(timespec="seconds"))
    pubs = db.rows(db.conn().execute(q, args))
    have = cached([p["id"] for p in pubs])
    due = [p for p in pubs if _age_h((have.get(p["id"]) or {}).get("fetched_at")) >= max_age_h]
    out = {"updated": 0, "skipped": len(pubs) - len(due), "errors": [], "reauth": False}
    by_conn: dict[str, list[dict]] = {}
    for p in due:
        by_conn.setdefault(p["connection_id"], []).append(p)
    today = datetime.now(timezone.utc).date().isoformat()
    for conn_id, items in by_conn.items():
        cn = db.get("connections", conn_id)
        if not cn:
            continue
        if youtube.missing_scope(cn.get("secrets"), youtube.SCOPE_ANALYTICS):
            for p in items:
                _save(p["id"], p["remote_id"], None, youtube.REAUTH_NOTE)
            _mark_reauth(conn_id, True)
            out["reauth"] = True
            continue
        try:
            tok, sec = youtube.access_token(cn["secrets"])
            if sec != cn["secrets"]:
                with db.tx() as c:
                    db.update(c, "connections", conn_id, {"secrets": sec, "updated_at": db.now()})
        except PublishError as e:
            out["errors"].append(f"{cn['name']}: {e}")
            continue
        for p in items:
            start = (p.get("finished_at") or today)[:10]
            meta = p.get("asset_meta")
            if isinstance(meta, str):
                import json
                meta = json.loads(meta or "{}")
            try:
                data = analytics.yt_video_analytics(tok, p["remote_id"], start, max(start, today))
                data["drop"] = analytics.biggest_drop(data["retention"], float((meta or {}).get("duration") or 0) or None)
                _save(p["id"], p["remote_id"], data, None)
                out["updated"] += 1
            except PublishError as e:
                if youtube.is_scope_error(e):
                    for q2 in items:
                        _save(q2["id"], q2["remote_id"], None, youtube.REAUTH_NOTE)
                    _mark_reauth(conn_id, True)
                    out["reauth"] = True
                    break
                _save(p["id"], p["remote_id"], None, str(e)[:300])
                out["errors"].append(f"{p['remote_id']}: {e}"[:200])
    if out["reauth"]:
        out["errors"].insert(0, youtube.REAUTH_NOTE)
    return out


def tick() -> None:
    """From app._scheduler (hourly): daily refresh of videos published in the last 30 days."""
    try:
        r = refresh(max_age_h=DAILY_AGE_H, recent_days=RECENT_DAYS)
        if r["updated"] or r["errors"]:
            log.info("retention: %s updated, %s", r["updated"], "; ".join(r["errors"])[:300] or "ok")
    except Exception as e:  # noqa: BLE001
        log.warning("retention tick: %s", e)
