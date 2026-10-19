"""Trend radar — what is moving right now, from sources that need no login:

  google_trends   Google Trends daily RSS for the region (no key)
  yt_popular      YouTube "most popular" chart for the region (needs YT_API_KEY, 1 quota unit)
  yt_channel      newest videos of channels you watch (public RSS, WATCH_CHANNELS=UC…,UC…)

Everything is returned as plain rows {source, title, url, score, meta}; the
planner turns them into ideas for THIS channel.
"""

from __future__ import annotations

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from ..config import settings

UA = {"User-Agent": "Mozilla/5.0 (Vividora trend radar)"}


def _get(url: str, timeout: float = 20) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def google_trends(region: str = "IN") -> list[dict]:
    try:
        xml = _get(f"https://trends.google.com/trending/rss?geo={region}")
        root = ET.fromstring(xml)
    except Exception as e:  # noqa: BLE001
        return [{"source": "google_trends", "title": f"(fetch failed: {e})", "url": None, "score": 0, "meta": {"error": True}}]
    ns = {"ht": "https://trends.google.com/trending/rss"}
    out = []
    for i, item in enumerate(root.iter("item")):
        title = (item.findtext("title") or "").strip()
        traffic = (item.findtext("ht:approx_traffic", namespaces=ns) or "").replace("+", "").replace(",", "")
        try:
            score = float(traffic) if traffic else max(1.0, 50 - i)
        except ValueError:
            score = max(1.0, 50 - i)
        news = [{"title": n.findtext("ht:news_item_title", namespaces=ns), "url": n.findtext("ht:news_item_url", namespaces=ns)}
                for n in item.findall("ht:news_item", namespaces=ns)][:3]
        out.append({"source": "google_trends", "title": title, "url": item.findtext("link"), "score": score,
                    "meta": {"traffic": traffic, "news": news, "picture": item.findtext("ht:picture", namespaces=ns)}})
    return out


def yt_popular(region: str = "IN", category: str | None = None, limit: int = 30) -> list[dict]:
    if not settings.yt_api_key:
        return []
    q = {"part": "snippet,statistics", "chart": "mostPopular", "regionCode": region, "maxResults": min(50, limit),
         "key": settings.yt_api_key}
    if category:
        q["videoCategoryId"] = category
    try:
        import json
        data = json.loads(_get("https://www.googleapis.com/youtube/v3/videos?" + urllib.parse.urlencode(q)))
    except Exception as e:  # noqa: BLE001
        return [{"source": "yt_popular", "title": f"(fetch failed: {e})", "url": None, "score": 0, "meta": {"error": True}}]
    out = []
    for v in data.get("items", []):
        st = v.get("statistics", {})
        sn = v.get("snippet", {})
        views = float(st.get("viewCount", 0) or 0)
        out.append({"source": "yt_popular", "title": sn.get("title", ""), "url": f"https://youtu.be/{v['id']}",
                    "score": views / 1000, "meta": {"channel": sn.get("channelTitle"), "views": int(views),
                                                    "likes": int(st.get("likeCount", 0) or 0), "published": sn.get("publishedAt"),
                                                    "tags": (sn.get("tags") or [])[:10], "thumb": (sn.get("thumbnails") or {}).get("medium", {}).get("url")}})
    return out


def yt_channel_feed(channel_id: str, limit: int = 8) -> list[dict]:
    try:
        xml = _get(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}")
        root = ET.fromstring(xml)
    except Exception as e:  # noqa: BLE001
        return [{"source": "yt_channel", "title": f"(feed failed for {channel_id}: {e})", "url": None, "score": 0, "meta": {"error": True}}]
    ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015", "media": "http://search.yahoo.com/mrss/"}
    name = root.findtext("a:title", namespaces=ns) or channel_id
    out = []
    for e in root.findall("a:entry", namespaces=ns)[:limit]:
        stats = e.find("media:group/media:community/media:statistics", namespaces=ns)
        views = float(stats.get("views", 0)) if stats is not None else 0.0
        pub = e.findtext("a:published", namespaces=ns) or ""
        age_days = 1.0
        try:
            age_days = max(0.2, (datetime.now(timezone.utc) - datetime.fromisoformat(pub.replace("Z", "+00:00"))).total_seconds() / 86400)
        except ValueError:
            pass
        out.append({"source": "yt_channel", "title": e.findtext("a:title", namespaces=ns) or "",
                    "url": e.findtext("a:link", namespaces=ns) or (e.find("a:link", namespaces=ns).get("href") if e.find("a:link", namespaces=ns) is not None else None),
                    "score": views / age_days / 100, "meta": {"channel": name, "views": int(views), "published": pub,
                                                             "views_per_day": int(views / age_days)}})
    return out


def refresh_all() -> list[dict]:
    rows = google_trends(settings.trend_region)
    rows += yt_popular(settings.trend_region)
    for ch in settings.watch_channels[:20]:
        rows += yt_channel_feed(ch)
    return rows


def topics_summary(rows: list[dict], n: int = 25) -> list[str]:
    """Short list for prompts: top titles, deduped, no noise."""
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: -float(r.get("score") or 0)):
        t = re.sub(r"\s+", " ", r["title"]).strip()
        if not t or r.get("meta", {}).get("error") or t.lower() in seen:
            continue
        seen.add(t.lower())
        extra = r["meta"].get("channel")
        out.append(f"{t}" + (f" ({extra})" if extra else ""))
        if len(out) >= n:
            break
    return out
