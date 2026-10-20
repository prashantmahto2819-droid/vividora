"""Pull view counts for published videos and learn which choices work.

Stats come from YouTube (API key or the channel's OAuth token) and the Graph
API for Instagram/Facebook. Learning is deliberately simple and explainable:
views-per-day, normalised per platform, grouped by caption style / hook /
length / zoom / look — each group gets an index (1.0 = average).
"""

from __future__ import annotations

import json
import math
import urllib.parse
from datetime import datetime, timezone

from datetime import timedelta

from ..config import settings
from ..publish import youtube
from ..publish.http import PublishError, request


def yt_stats(video_ids: list[str], secrets: dict | None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not video_ids:
        return out
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        params = {"part": "statistics,snippet", "id": ",".join(batch)}
        headers = {}
        if settings.yt_api_key:
            params["key"] = settings.yt_api_key
        elif secrets:
            tok, _ = youtube.access_token(secrets)
            headers["Authorization"] = f"Bearer {tok}"
        else:
            return out
        data = request("GET", f"{youtube.API}/videos", params=params, headers=headers)
        for v in data.get("items", []):
            st = v.get("statistics", {})
            out[v["id"]] = {"views": int(st.get("viewCount", 0) or 0), "likes": int(st.get("likeCount", 0) or 0),
                            "comments": int(st.get("commentCount", 0) or 0),
                            "published": (v.get("snippet") or {}).get("publishedAt")}
    return out


def ig_stats(media_id: str, page_token: str) -> dict:
    base = request("GET", f"https://graph.facebook.com/v21.0/{media_id}",
                   params={"fields": "like_count,comments_count,timestamp", "access_token": page_token})
    out = {"likes": int(base.get("like_count", 0) or 0), "comments": int(base.get("comments_count", 0) or 0),
           "published": base.get("timestamp")}
    try:
        ins = request("GET", f"https://graph.facebook.com/v21.0/{media_id}/insights",
                      params={"metric": "plays,reach,shares,saved", "access_token": page_token})
        for m in ins.get("data", []):
            val = (m.get("values") or [{}])[0].get("value", 0)
            out[{"plays": "views", "reach": "reach", "shares": "shares", "saved": "saves"}.get(m["name"], m["name"])] = int(val or 0)
    except PublishError:
        pass
    return out


def fb_stats(video_id: str, page_token: str) -> dict:
    r = request("GET", f"https://graph.facebook.com/v21.0/{video_id}",
                params={"fields": "views,created_time,likes.summary(true),comments.summary(true)", "access_token": page_token})
    return {"views": int(r.get("views", 0) or 0), "likes": int(((r.get("likes") or {}).get("summary") or {}).get("total_count", 0)),
            "comments": int(((r.get("comments") or {}).get("summary") or {}).get("total_count", 0)),
            "published": r.get("created_time")}


IST = timezone(timedelta(hours=5, minutes=30))


# ---- YouTube Analytics API (retention / watch time / CTR) — needs yt-analytics.readonly
YTA = "https://youtubeanalytics.googleapis.com/v2/reports"
BASE_METRICS = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained"
CTR_METRICS = "impressions,impressionClickThroughRate"  # not always offered by the API → optional


def _report(token: str, **params) -> list[dict]:
    """One reports.query call → list of {columnName: value} rows."""
    r = request("GET", YTA, params={"ids": "channel==MINE", **params}, headers={"Authorization": f"Bearer {token}"})
    names = [h.get("name") for h in r.get("columnHeaders") or []]
    return [dict(zip(names, row)) for row in r.get("rows") or []]


def yt_video_analytics(token: str, video_id: str, start: str, end: str) -> dict:
    """Per-video totals + audience retention curve. Dates YYYY-MM-DD. Scope errors propagate
    (caller marks the connection for re-auth); a metric the API refuses is just left out."""
    out: dict = {"metrics": {}, "retention": [], "unavailable": []}
    rows = _report(token, startDate=start, endDate=end, metrics=BASE_METRICS, filters=f"video=={video_id}")
    if rows:
        out["metrics"] = {k: rows[0].get(k) for k in BASE_METRICS.split(",")}
    try:
        rows = _report(token, startDate=start, endDate=end, metrics=CTR_METRICS, filters=f"video=={video_id}")
        if rows:
            out["metrics"].update({k: rows[0].get(k) for k in CTR_METRICS.split(",")})
    except PublishError as e:
        if youtube.is_scope_error(e):
            raise
        out["unavailable"] += CTR_METRICS.split(",")
    for metrics in ("audienceWatchRatio,relativeRetentionPerformance", "audienceWatchRatio"):
        try:
            rows = _report(token, startDate=start, endDate=end, dimensions="elapsedVideoTimeRatio", metrics=metrics,
                           filters=f"video=={video_id}", sort="elapsedVideoTimeRatio")
            out["retention"] = [[round(float(r["elapsedVideoTimeRatio"]), 4), round(float(r.get("audienceWatchRatio") or 0), 4),
                                 (round(float(r["relativeRetentionPerformance"]), 3) if r.get("relativeRetentionPerformance") is not None else None)]
                                for r in rows if r.get("elapsedVideoTimeRatio") is not None]
            break
        except PublishError as e:
            if youtube.is_scope_error(e):
                raise
            if "relativeRetentionPerformance" in metrics:
                out["unavailable"].append("relativeRetentionPerformance")
                continue
            out["unavailable"].append("audienceWatchRatio")
    return out


def _mmss(sec: float) -> str:
    sec = max(0, int(round(sec)))
    return f"{sec // 60}:{sec % 60:02d}"


def biggest_drop(curve: list, duration: float | None = None) -> dict | None:
    """Where the most viewers leave. curve: [[ratio 0..1, audienceWatchRatio, rel?], ...].
    Looks at the fall over a ~5 % window (single-point noise ignored) and skips the last 5 %
    (everyone leaves at the end screen). Returns {at, sec, pct, hint} or None."""
    pts = sorted((float(p[0]), float(p[1])) for p in curve or [] if p and p[1] is not None)
    if len(pts) < 5:
        return None
    w = max(1, len(pts) // 20)
    best = None
    for i in range(w, len(pts)):
        x0, y0 = pts[i - w]
        x1, y1 = pts[i]
        if x1 > 0.95:
            break
        d = y0 - y1
        if best is None or d > best[0]:
            best = (d, x0, x1, y0)
    if not best or best[0] <= 0.01:
        return None
    d, x0, x1, y0 = best
    pct = round(d * 100)
    at = round((x0 + x1) / 2, 3)
    out = {"at": at, "from": x0, "to": x1, "pct": pct, "start": x0 < 0.12}
    where = f"{_mmss(at * duration)} के आसपास" if duration else f"{round(at * 100)}% पर"
    out["sec"] = round(at * duration, 1) if duration else None
    out["hint"] = f"{where} {pct}% लोग चले गए — इस हिस्से को छोटा करें" + (" (शुरुआत: hook तेज़ करें)" if out["start"] else "")
    return out


def retention_notes(rows: list[dict]) -> list[str]:
    """Learning notes from the retention cache: rows [{title, yta: {metrics, drop}}]."""
    with_drop = [r for r in rows if (r.get("yta") or {}).get("drop")]
    notes = []
    if with_drop:
        early = [r for r in with_drop if r["yta"]["drop"].get("start")]
        if len(with_drop) >= 2 and len(early) * 2 >= len(with_drop):
            notes.append(f"{len(early)}/{len(with_drop)} videos में सबसे बड़ी गिरावट शुरुआत (पहले ~10%) में है — hook छोटा और तेज़ रखें, intro हटाएँ")
        worst = max(with_drop, key=lambda r: r["yta"]["drop"]["pct"])
        notes.append(f"“{(worst.get('title') or '')[:60]}”: {worst['yta']['drop']['hint']}")
    avp = [float(r["yta"]["metrics"]["averageViewPercentage"]) for r in rows
           if ((r.get("yta") or {}).get("metrics") or {}).get("averageViewPercentage") is not None]
    if len(avp) >= 2:
        notes.append(f"औसतन लोग वीडियो का {sum(avp) / len(avp):.0f}% देखते हैं")
    return notes


# ---- learning
DIMENSIONS = {
    "caption_style": "caption style", "hook": "hook card", "zoom": "auto zoom", "look": "color look",
    "length": "लंबाई", "music": "background music", "weekday": "दिन", "hour": "समय",
}


def _bucket_len(sec: float) -> str:
    if sec <= 20:
        return "≤20s"
    if sec <= 40:
        return "21–40s"
    if sec <= 60:
        return "41–60s"
    if sec <= 180:
        return "1–3 min"
    if sec <= 600:
        return "3–10 min"
    return ">10 min"


def features(asset_meta: dict, render_settings: dict, published_at: str | None) -> dict:
    fx = (asset_meta.get("effects") or {})
    f = {"caption_style": asset_meta.get("captions") or "none",
         "hook": "yes" if (render_settings.get("hook") or {}).get("text") else "no",
         "zoom": "on" if fx.get("zoom") else "off", "look": fx.get("look") or "none",
         "length": _bucket_len(float(asset_meta.get("duration") or 0)),
         "music": "yes" if fx.get("music") else "no"}
    if published_at:
        try:
            d = datetime.fromisoformat(published_at.replace("Z", "+00:00")).astimezone(IST)
            f["weekday"] = ["सोम", "मंगल", "बुध", "गुरु", "शुक्र", "शनि", "रवि"][d.weekday()]
            f["hour"] = f"{(d.hour // 3) * 3:02d}–{(d.hour // 3) * 3 + 3:02d}"
        except ValueError:
            pass
    return f


def learn(rows: list[dict]) -> dict:
    """rows: [{platform, views, published_at, features}] → per-dimension indices + recommendation."""
    now = datetime.now(timezone.utc)
    scored = []
    for r in rows:
        try:
            age = max(1.0, (now - datetime.fromisoformat(r["published_at"].replace("Z", "+00:00"))).total_seconds() / 86400)
        except (ValueError, AttributeError, TypeError):
            age = 7.0
        # views per day with diminishing age (a 2-day-old video still ramping) — log-ish damping
        vpd = float(r.get("views") or 0) / math.sqrt(age)
        scored.append({**r, "vpd": vpd})
    if len(scored) < 3:
        return {"n": len(scored), "dimensions": {}, "recommend": {}, "note": "कम से कम 3 published videos चाहिए"}
    # normalise per platform so YouTube and Instagram numbers mix fairly
    by_pl: dict[str, list[float]] = {}
    for r in scored:
        by_pl.setdefault(r["platform"], []).append(r["vpd"])
    avg_pl = {k: (sum(v) / len(v) or 1.0) for k, v in by_pl.items()}
    for r in scored:
        r["index"] = r["vpd"] / (avg_pl[r["platform"]] or 1.0)
    dims: dict[str, dict] = {}
    recommend: dict[str, str] = {}
    for dim in DIMENSIONS:
        groups: dict[str, list[float]] = {}
        for r in scored:
            val = (r.get("features") or {}).get(dim)
            if val is None:
                continue
            groups.setdefault(val, []).append(r["index"])
        if len(groups) < 2:
            continue
        table = {k: {"n": len(v), "index": round(sum(v) / len(v), 2)} for k, v in groups.items()}
        dims[dim] = {"label": DIMENSIONS[dim], "groups": table}
        best = max((k for k in table if table[k]["n"] >= 2), key=lambda k: table[k]["index"], default=None)
        if best and table[best]["index"] >= 1.15:
            recommend[dim] = best
    return {"n": len(scored), "dimensions": dims, "recommend": recommend}
