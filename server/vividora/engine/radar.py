"""Daily trend radar for the channel's niche ("the research layer").

* niche_search()  — YouTube search for the channel's niche queries, last 7 days, by views
                    (needs YT_API_KEY; ~100 quota units per query, so a few queries a day)
* outliers()      — videos doing ≥ 2× their channel's usual views-per-day (competitor feeds)
                    or the top views-per-day in niche search
* daily()         — refresh → outliers → 5 ideas (via planner) → short WhatsApp digest
Ideas are suggestions only; nothing is made or posted without the creator.
"""

from __future__ import annotations

import json
import statistics
import urllib.parse
from datetime import datetime, timedelta, timezone

from ..config import settings
from . import trends

DEFAULT = {"daily": True, "hour": 8, "queries": ["hindi motivational story", "मोटिवेशनल कहानी", "success motivation hindi"],
           "watch": [], "ideas": 5, "outlier_x": 2.0}


def settings_of(channel_settings: dict | None) -> dict:
    return {**DEFAULT, **((channel_settings or {}).get("radar") or {})}


def niche_search(queries: list[str], region: str = "IN", days: int = 7, per_query: int = 15) -> list[dict]:
    if not settings.yt_api_key or not queries:
        return []
    after = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds").replace("+00:00", "Z")
    ids: list[str] = []
    for q in queries[:4]:
        try:
            data = json.loads(trends._get("https://www.googleapis.com/youtube/v3/search?" + urllib.parse.urlencode({
                "part": "snippet", "q": q, "type": "video", "order": "viewCount", "publishedAfter": after,
                "regionCode": region, "relevanceLanguage": "hi", "maxResults": per_query, "key": settings.yt_api_key})))
        except Exception:  # noqa: BLE001
            continue
        ids += [it["id"]["videoId"] for it in data.get("items", []) if it.get("id", {}).get("videoId")]
    out = []
    for i in range(0, len(ids), 50):
        try:
            data = json.loads(trends._get("https://www.googleapis.com/youtube/v3/videos?" + urllib.parse.urlencode({
                "part": "snippet,statistics,contentDetails", "id": ",".join(dict.fromkeys(ids[i:i + 50])), "key": settings.yt_api_key})))
        except Exception:  # noqa: BLE001
            continue
        now = datetime.now(timezone.utc)
        for v in data.get("items", []):
            sn, st = v.get("snippet", {}), v.get("statistics", {})
            views = float(st.get("viewCount", 0) or 0)
            try:
                age = max(.2, (now - datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))).total_seconds() / 86400)
            except (KeyError, ValueError):
                age = 3.0
            dur = v.get("contentDetails", {}).get("duration", "")
            out.append({"source": "yt_niche", "title": sn.get("title", ""), "url": f"https://youtu.be/{v['id']}",
                        "score": views / age / 100,
                        "meta": {"channel": sn.get("channelTitle"), "views": int(views), "published": sn.get("publishedAt"),
                                 "views_per_day": int(views / age), "short": "M" not in dur.replace("PT", "") or dur in ("PT1M",),
                                 "thumb": (sn.get("thumbnails") or {}).get("medium", {}).get("url")}})
    return out


def outliers(rows: list[dict], x: float = 2.0, top: int = 12) -> list[dict]:
    by_ch: dict[str, list[float]] = {}
    for r in rows:
        if r.get("source") == "yt_channel":
            by_ch.setdefault(r["meta"].get("channel") or "", []).append(float(r["meta"].get("views_per_day") or 0))
    out = []
    for r in rows:
        m = r.get("meta") or {}
        vpd = float(m.get("views_per_day") or 0)
        if r.get("source") == "yt_channel":
            base = statistics.median(by_ch.get(m.get("channel") or "", [0]) or [0])
            if base > 0 and vpd >= x * base:
                out.append({**r, "meta": {**m, "outlier_x": round(vpd / base, 1)}})
        elif r.get("source") == "yt_niche" and vpd > 0:
            out.append({**r, "meta": {**m, "outlier_x": None}})
    out.sort(key=lambda r: -float(r["meta"].get("views_per_day") or 0))
    return out[:top]


def collect(radar: dict) -> list[dict]:
    rows = trends.refresh_all()
    for ch in (radar.get("watch") or [])[:20]:
        rows += trends.yt_channel_feed(ch)
    rows += niche_search(radar.get("queries") or [])
    return [r for r in rows if not (r.get("meta") or {}).get("error")]


def digest_text(channel_name: str, outs: list[dict], ideas: list[dict], link: str = "") -> str:
    lines = [f"🔥 {channel_name} — आज का trend radar"]
    if outs:
        lines.append("\nजो अभी चल रहा है:")
        for r in outs[:3]:
            m = r["meta"]
            lines.append(f"• {r['title'][:70]} — {m.get('views_per_day', 0):,}/दिन" + (f" ({m['outlier_x']}× उनके normal से)" if m.get("outlier_x") else ""))
    if ideas:
        lines.append("\nआपके लिए ideas:")
        for i, idea in enumerate(ideas[:5], 1):
            lines.append(f"{i}. {idea['title']}" + (f"\n   Hook: {idea['hook']}" if idea.get("hook") else ""))
    if link:
        lines.append(f"\nPlan में देखें: {link}")
    return "\n".join(lines)
