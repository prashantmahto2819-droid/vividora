"""Pre-flight: check a project's render settings against each platform's rules.

Rules come from the platforms' own help pages / API docs (2025-2026) and are
written so code can test them. Each finding: level (block | warn | tip),
platform, message (Hindi), and an optional one-click fix (render-settings patch).
"""

from __future__ import annotations

import re

# safe zones as fractions of the frame (areas covered by the app's buttons/captions)
SAFE = {
    "yt-short": {"top": .15, "bottom": .20, "right": .13, "left": .04},
    "ig-reel": {"top": .14, "bottom": .35, "right": .10, "left": .06},
    "fb-reel": {"top": .14, "bottom": .35, "right": .10, "left": .06},
    "yt-long": {"top": .0, "bottom": .12, "right": .0, "left": .0},   # bottom: progress bar / controls
}
RULES = {
    "yt-long": {"label": "YouTube video", "min": 60, "best": (480, 1200), "max": 12 * 3600, "hashtags": 3, "title": 100},
    "yt-short": {"label": "YouTube Short", "min": 5, "best": (20, 60), "max": 180, "hashtags": 3, "title": 100, "hook_s": 1.0},
    "ig-reel": {"label": "Instagram Reel", "min": 3, "best": (15, 90), "max": 180, "hashtags": 5, "caption": 2200, "hook_s": 1.5},
    "fb-reel": {"label": "Facebook Reel", "min": 3, "best": (15, 60), "max": 90, "hashtags": 5, "hook_s": 1.5},
}
WATERMARK_WORDS = ("tiktok", "capcut", "inshot", "kinemaster", "moj", "josh")


def _f(level, preset, msg, fix=None, item=None):
    return {"level": level, "preset": preset, "platform": RULES.get(preset, {}).get("label", preset), "msg": msg, "fix": fix, "item": item}


def _caption_margin(preset_id: str) -> float:
    """How high the preset puts bottom captions (fraction of the height) — the IG/FB presets already
    lift them above the 35 % caption/button area, so "bottom" there is safe."""
    try:
        from .presets import platform
        return float(platform(preset_id).get("caption_margin_v") or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def _text_y(t: dict) -> float:
    if t.get("pos") == "free":
        return float(t.get("y", .5))
    return {"top": .18, "center": .5, "bottom": .78}.get(t.get("pos") or "top", .18)


def check(project: dict, rs: dict, presets: list[str] | None = None, meta_text: dict | None = None) -> list[dict]:
    """meta_text: {"title": ..., "description": ..., "tags": [...]} per publish plan item (optional)."""
    fx = rs.get("effects") or {}
    m = project.get("meta") or {}
    dur = float(m.get("duration") or 0) - float(((project.get("edl") or {}).get("stats") or {}).get("removed_seconds") or 0)
    presets = presets or rs.get("presets") or ["yt-short"]
    out: list[dict] = []
    for p in presets:
        r = RULES.get(p)
        if not r:
            continue
        # duration
        if dur > r["max"]:
            out.append(_f("block", p, f"वीडियो {dur:.0f}s है — {r['label']} की सीमा {r['max']}s। इसे Shorts tab से छोटे हिस्सों में बाँटें।"))
        elif dur < r["min"]:
            out.append(_f("warn", p, f"वीडियो सिर्फ़ {dur:.0f}s — {r['label']} के लिए कम से कम {r['min']}s रखें।"))
        elif not (r["best"][0] <= dur <= r["best"][1]):
            out.append(_f("tip", p, f"{r['label']} के लिए {r['best'][0]}–{r['best'][1]}s सबसे अच्छा चलता है (अभी {dur:.0f}s)।"))
        # hook timing (short-form)
        if r.get("hook_s"):
            hk = (rs.get("hook") or {}).get("text")
            if not hk and not any(float(t.get("start", 9)) <= r["hook_s"] for t in fx.get("titles") or []):
                out.append(_f("warn", p, f"पहले {r['hook_s']:.0f} सेकंड में स्क्रीन पर hook text नहीं — {r['label']} पर लोग तुरंत scroll कर देते हैं।"))
        # safe zones for text items (vertical formats)
        z = SAFE.get(p)
        if z and p != "yt-long":
            for t in fx.get("titles") or []:
                y = _text_y(t)
                if y < z["top"] or y > 1 - z["bottom"]:
                    out.append(_f("warn", p, f"Text “{str(t.get('text', ''))[:24]}” {r['label']} के बटन/caption वाले हिस्से में है (ऊपर {int(z['top'] * 100)}%, नीचे {int(z['bottom'] * 100)}% खाली रखें)।",
                                  item=t.get("_id")))
            cap = (rs.get("captions") or {}).get("position") or ""
            if p in ("ig-reel", "fb-reel") and cap in ("", "bottom") and rs.get("burn_captions", True) \
                    and _caption_margin(p) < z["bottom"]:
                out.append(_f("tip", p, "Instagram/Facebook में नीचे का 35% हिस्सा caption/बटन से ढका रहता है — captions “बीच” पर रखें।",
                              fix={"captions": {**(rs.get("captions") or {}), "position": "center"}}))
            for b in fx.get("broll") or []:
                if b.get("fit") == "free" and float(b.get("x", .5)) > 1 - z["right"] and not b.get("platforms"):
                    out.append(_f("tip", p, f"Sticker दाएँ किनारे पर है — {r['label']} के like/comment बटन उसे ढक देंगे।", item=b.get("_id")))
        # metadata
        mt = (meta_text or {}).get(p) or {}
        title = mt.get("title") or ""
        if title and len(title) > r.get("title", 100):
            out.append(_f("warn", p, f"Title {len(title)} अक्षर — सीमा {r['title']}।"))
        tags_in_text = re.findall(r"#\w+", (mt.get("description") or "") + " " + title)
        if len(tags_in_text) > r["hashtags"]:
            out.append(_f("warn", p, f"{len(tags_in_text)} hashtags — {r['label']} पर {r['hashtags']} से ज़्यादा फ़ायदा नहीं (Instagram 5 की सीमा)।"))
    # originality / watermark (all platforms)
    for b in fx.get("broll") or []:
        nm = str(b.get("name") or b.get("id") or "").lower()
        if any(w in nm for w in WATERMARK_WORDS):
            out.append(_f("block", "all", "दूसरे app का watermark/logo दिख रहा है — Instagram/YouTube ऐसे reposts की reach घटाते हैं।", item=b.get("_id")))
    if not (rs.get("hook") or {}).get("text") and not fx.get("titles") and not fx.get("broll"):
        out.append(_f("tip", "all", "वीडियो में कोई text/sticker/B-roll नहीं — एक जैसे दिखने वाले वीडियो को platforms “unoriginal” मान सकते हैं; हर वीडियो में कुछ अलग जोड़ें।"))
    order = {"block": 0, "warn": 1, "tip": 2}
    out.sort(key=lambda x: order[x["level"]])
    return out
