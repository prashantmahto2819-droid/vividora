"""Trending-template research: what do the thumbnails that win in the channel's niche look like?

Uses only the YouTube Data API (same key as the radar) — titles, channels and thumbnail URLs are public API
data. Each thumbnail is measured (text area, faces, dominant colours, contrast, layout) and stored as a trend
entry with a status workflow (draft → reviewed → approved → published), its source URL and date. Duplicates
are folded by a colour + layout hash. "Make an original template from this style" builds a Vividora template
from the MEASURED characteristics (colours, text side, face side, badge, contrast) — never from the image.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import urllib.request
from datetime import datetime, timezone

import numpy as np
from PIL import Image, ImageStat

from .. import db
from ..config import settings as cfg
from . import radar, thumbnail as T

log = logging.getLogger("vividora.trendtpl")
STATUSES = ("draft", "reviewed", "approved", "published", "rejected")
LICENCE = ("Reference only — thumbnail belongs to its creator (YouTube ToS). Vividora stores measurements and the "
           "public URL, never the image; the generated template is an original design.")


def _fetch(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Vividora/1.0 trend research"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def analyse(img: Image.Image) -> dict:
    """Layout statistics of one thumbnail (no copying — numbers only)."""
    im = img.convert("RGB")
    im.thumbnail((640, 640))
    W, H = im.size
    arr = np.asarray(im).astype(np.float32)
    gray = arr.mean(axis=2)
    # text-ish area: high local contrast blocks (edges), measured per 8-px cell
    gy, gx = np.gradient(gray)
    edge = np.hypot(gx, gy)
    cell = 8
    cells = edge[: H // cell * cell, : W // cell * cell].reshape(H // cell, cell, W // cell, cell).mean(axis=(1, 3))
    busy = cells > max(18.0, float(np.percentile(cells, 75)))
    text_area = float(busy.mean())
    rows = busy.mean(axis=1)
    cols = busy.mean(axis=0)
    text_side = "left" if cols[: len(cols) // 2].mean() > cols[len(cols) // 2:].mean() * 1.15 else \
        "right" if cols[len(cols) // 2:].mean() > cols[: len(cols) // 2].mean() * 1.15 else "center"
    text_band = "top" if rows[: len(rows) // 3].mean() > rows[len(rows) // 3 * 2:].mean() * 1.15 else \
        "bottom" if rows[len(rows) // 3 * 2:].mean() > rows[: len(rows) // 3].mean() * 1.15 else "middle"
    face = None
    try:
        face = T.detect_face(im)
    except Exception:  # noqa: BLE001
        face = None
    # dominant colours: 4 clusters by quantisation
    q = im.quantize(colors=5, method=Image.Quantize.MEDIANCUT).convert("RGB")
    counts = sorted(q.getcolors(W * H) or [], reverse=True)
    dom = ["#%02X%02X%02X" % c for _, c in counts[:4]]
    stat = ImageStat.Stat(im.convert("L"))
    contrast = float(stat.stddev[0]) / 128.0
    sat = float(np.asarray(im.convert("HSV"))[:, :, 1].mean()) / 255.0
    bright = float(stat.mean[0]) / 255.0
    return {"text_area": round(text_area, 3), "text_side": text_side, "text_band": text_band,
            "face": bool(face), "face_x": round(float(face["cx"]), 2) if face else None, "face_w": round(float(face.get("w", 0)), 2) if face else None,
            "colors": dom, "contrast": round(contrast, 3), "saturation": round(sat, 3), "brightness": round(bright, 3),
            "warm": bool(sum(int(c[1:3], 16) for c in dom[:2]) > sum(int(c[5:7], 16) for c in dom[:2]))}


def layout_hash(stats: dict) -> str:
    key = f"{stats.get('text_side')}|{stats.get('text_band')}|{int(bool(stats.get('face')))}|" \
          f"{round(stats.get('text_area', 0) * 5)}|{'/'.join(c[:3] for c in (stats.get('colors') or [])[:2])}|{round(stats.get('brightness', 0) * 4)}"
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def collect(workspace_id: str, queries: list[str], *, per_query: int = 10, region: str = "IN") -> dict:
    """Search the niche, measure the top thumbnails, store new trend entries (dedup by hash + video id)."""
    if not cfg.yt_api_key:
        return {"added": 0, "seen": 0, "error": "YT_API_KEY नहीं है — Settings में YouTube key डालें"}
    rows = radar.niche_search(queries, region=region, days=30, per_query=per_query)
    rows.sort(key=lambda r: -r.get("score", 0))
    added, seen, skipped = 0, 0, 0
    now = db.now()
    with db.tx() as c:
        have_ids = {r[0] for r in c.execute("SELECT video_id FROM trend_templates WHERE workspace_id = ?", (workspace_id,))}
        have_hash = {r[0] for r in c.execute("SELECT hash FROM trend_templates WHERE workspace_id = ?", (workspace_id,))}
        for r in rows[:40]:
            vid = r["url"].rsplit("/", 1)[-1]
            seen += 1
            if vid in have_ids:
                continue
            thumb = (r.get("meta") or {}).get("thumb")
            if not thumb:
                continue
            try:
                img = Image.open(io.BytesIO(_fetch(thumb)))
                st = analyse(img)
            except Exception as e:  # noqa: BLE001
                log.info("trend thumb %s skipped: %s", vid, e)
                continue
            h = layout_hash(st)
            if h in have_hash:
                skipped += 1
                continue
            st["views"] = (r.get("meta") or {}).get("views")
            st["views_per_day"] = (r.get("meta") or {}).get("views_per_day")
            st["thumb_url"] = thumb
            st["published"] = (r.get("meta") or {}).get("published")
            db.insert(c, "trend_templates", {"id": db.new_id(), "workspace_id": workspace_id, "source": "youtube", "source_url": r["url"],
                                             "video_id": vid, "title": r.get("title", "")[:200], "channel": (r.get("meta") or {}).get("channel"),
                                             "query": r.get("query") or (queries[0] if queries else ""), "fetched_at": now, "stats": st,
                                             "hash": h, "status": "draft", "note": None, "template_id": None, "licence": LICENCE})
            have_ids.add(vid)
            have_hash.add(h)
            added += 1
    return {"added": added, "seen": seen, "duplicates": skipped}


def report(workspace_id: str) -> dict:
    """What the winners have in common, over all non-rejected entries."""
    rows = db.rows(db.conn().execute("SELECT * FROM trend_templates WHERE workspace_id = ? AND status != 'rejected' ORDER BY fetched_at DESC",
                                     (workspace_id,)))
    if not rows:
        return {"count": 0}
    st = [r["stats"] for r in rows]
    n = len(st)
    side = {}
    band = {}
    for s in st:
        side[s.get("text_side")] = side.get(s.get("text_side"), 0) + 1
        band[s.get("text_band")] = band.get(s.get("text_band"), 0) + 1
    cols = {}
    for s in st:
        for c in (s.get("colors") or [])[:2]:
            cols[c] = cols.get(c, 0) + 1
    return {"count": n, "face_share": round(sum(1 for s in st if s.get("face")) / n, 2),
            "text_area_avg": round(sum(s.get("text_area", 0) for s in st) / n, 3),
            "contrast_avg": round(sum(s.get("contrast", 0) for s in st) / n, 3),
            "warm_share": round(sum(1 for s in st if s.get("warm")) / n, 2),
            "text_side": max(side, key=side.get), "text_band": max(band, key=band.get),
            "top_colors": [c for c, _ in sorted(cols.items(), key=lambda kv: -kv[1])[:6]],
            "latest": rows[0]["fetched_at"]}


def original_template(entry: dict, name: str | None = None) -> dict:
    """An original Vividora design in the measured style: same text side, warmth, contrast and badge habit —
    none of the source pixels or words."""
    st = entry.get("stats") or {}
    cols = st.get("colors") or ["#111111", "#FFD400"]
    dark = sorted(cols, key=lambda c: int(c[1:3], 16) + int(c[3:5], 16) + int(c[5:7], 16))
    bg1, bg2 = dark[0], dark[min(1, len(dark) - 1)]
    accent = "#FFD400" if st.get("warm") else "#00E5FF"
    face = bool(st.get("face"))
    tside = st.get("text_side") or "left"
    tpl = "face_left" if (face and tside == "right") else "face_right" if face else "headline" if st.get("text_band") == "top" else "spotlight"
    settings = {"template": tpl, "size": "yt", "accent": accent, "text": "आपका *headline* यहाँ", "style": "outline" if st.get("contrast", 0) > 0.35 else "box",
                "bg": {"type": "gradient", "color": bg1, "color2": bg2, "angle": 120}, "vignette": 0.3, "no_person": not face, "cutout": face,
                "stickers": [{"uid": "badge", "txt": "NEW", "x": 0.88, "y": 0.12, "size": 0.07, "bg": accent, "color": "#111111", "font": "Poppins"}]
                if st.get("text_area", 0) > 0.25 else [], "layout": {"yt": {}}}
    return {"name": name or f"Trend style · {entry.get('channel') or 'niche'}"[:60], "format": "yt", "industry": "creator",
            "tags": ["trend", st.get("text_side") or "", "face" if face else "no-face"], "settings": settings,
            "source": f"trend:{entry['id']}", "fields": [], "defaults": {}}


def due(channel_settings: dict | None, hour: int, today: str) -> bool:
    rs = (channel_settings or {}).get("trendtpl") or {}
    return bool(rs.get("auto")) and int(rs.get("hour", 9)) == hour and rs.get("last") != today
