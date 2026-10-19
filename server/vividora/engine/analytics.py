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
