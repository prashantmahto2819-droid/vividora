"""Autopilot: upload → finished videos + Shorts + titles, with no clicks in
between. Every decision is a plain rule (or the workspace's learned
defaults), written into the project's settings so the editor shows exactly
what was chosen and the creator can change anything before approving.
"""

from __future__ import annotations

import random
import re

from . import analyze, metadata, shorts
from .catalog import GRADE_PRESETS

HOOK_MAX_WORDS = 8


def _first_hook(project: dict) -> str:
    """A short on-screen line from the strongest early sentence."""
    tr = project.get("transcript") or {}
    sents = shorts._sentences(tr)
    if not sents:
        return ""
    head = sents[:6]
    best = max(head, key=shorts._score)
    words = best["text"].split()
    line = " ".join(words[:HOOK_MAX_WORDS]).strip(" ।.,!?")
    return line if len(line) >= 8 else ""


def _grade_with_correction(preset: dict, analysis: dict) -> dict:
    """Brand look + the measured correction for this recording (dark room, cold light…)."""
    g = {k: v for k, v in (preset or {}).items() if k != "label" and not k.startswith("_")}
    for k, v in analyze.auto_grade(analysis).items():
        g[k] = round(max(-1.0, min(1.0, float(g.get(k, 0)) + float(v))), 3)
    return g


def plan(project: dict, workspace_settings: dict, library: list[dict]) -> dict:
    """Render settings for this recording. Pure function: no I/O."""
    learned = (workspace_settings or {}).get("render_defaults", {}) or {}
    rec = (workspace_settings or {}).get("recommend", {}) or {}
    brand = (workspace_settings or {}).get("brand", {}) or {}
    duration = float(project.get("meta", {}).get("duration") or 0)
    analysis = (project.get("meta") or {}).get("analysis") or {}
    is_short_source = duration <= 75
    lang = project.get("language") or "hi"

    caption_style = learned.get("caption_style") or brand.get("caption_style") or ("hormozi" if is_short_source else "karaoke")
    hook = _first_hook(project)
    music = ""
    niche = " ".join([str(workspace_settings.get("niche") or ""), str(brand.get("music_mood") or "")]).lower()
    mood = next((m for m in ("motivational", "emotional", "news", "lofi", "upbeat", "cinematic", "story", "energetic") if m in niche), None)
    if not mood:
        mood = "news" if "news" in niche else "motivational"
    musics = [m for m in library if m.get("kind") == "music"]
    bg = [m for m in musics if mood in (m.get("tags") or "") or mood in (m.get("name") or "").lower()] or musics
    if bg and brand.get("music", True):
        music = random.Random(project["id"]).choice(bg)["id"]
    stickers = [m for m in library if m.get("kind") == "sticker"]
    sfx = {(m.get("name") or "").lower(): m["id"] for m in library if m.get("kind") == "sfx"}

    def find(names: list[str]) -> str:
        for n in names:
            for m in stickers:
                if n in (m.get("name") or "").lower():
                    return m["id"]
        return ""
    logo = brand.get("logo_id") or next((l["id"] for l in library if l.get("kind") == "logo"), "")
    grade_preset = brand.get("grade_preset") or "natural_skin"
    effects = {
        "zoom": {"enabled": rec.get("zoom", "on") != "off", "strength": 0.9},
        "look": learned.get("effects", {}).get("look", "none") if isinstance(learned.get("effects"), dict) else "none",
        "transition": "punch" if is_short_source else "none",
        "extras": [],
        "grade": _grade_with_correction(GRADE_PRESETS.get(grade_preset, {}), analysis),
        "grade_preset": grade_preset,
        "stack": [],
        "music": {"id": music, "volume": 0.12, "duck": True, "duck_amount": 0.6, "fade": 1.5},
        "voice": analyze.auto_voice(analysis, brand.get("voice_preset") or "studio"),
        "broll": [], "titles": [], "sfx": [],
        "watermark": {"id": logo, "opacity": 0.7, "size": 0.12, "pos": "tr"},
    }
    # CTA popup + SFX (output timeline ≈ source minus cuts; place relative to the end)
    out_dur = duration - float(((project.get("edl") or {}).get("stats") or {}).get("removed_seconds") or 0)
    # Call-to-action popups — English text on every platform, and the right ask per platform:
    # Subscribe on YouTube, Follow on Instagram / Facebook (each item only renders on its platform).
    ctas = [("youtube", ["subscribe red", "subscribe"]), ("instagram", ["follow insta", "follow"]),
            ("facebook", ["follow facebook", "follow insta", "follow"])]
    if out_dur > 8 and brand.get("cta_popup", True):
        at = max(2.0, out_dur * (0.72 if not is_short_source else 0.82))
        added = False
        for fam, names in ctas:
            sid = find(names)
            if not sid:
                continue
            effects["broll"].append({"_id": f"ap_cta_{fam}", "id": sid, "start": round(at, 2), "end": round(min(out_dur, at + 2.8), 2),
                                     "fit": "free", "x": 0.5, "y": 0.6, "scale": 0.6, "opacity": 1, "rotate": 0, "anim": "pop",
                                     "platforms": [fam]})
            added = True
        if added and sfx.get("pop"):
            effects["sfx"].append({"_id": "ap_pop", "id": sfx["pop"], "at": round(at, 2), "volume": 0.7})
    if hook and sfx.get("whoosh"):
        effects["sfx"].append({"_id": "ap_whoosh", "id": sfx["whoosh"], "at": 0.0, "volume": 0.6})
    if not is_short_source and out_dur > 40 and brand.get("cta_popup", True):
        bell = find(["like sub bell"])
        if bell:
            effects["broll"].append({"_id": "ap_bell", "id": bell, "start": 6.0, "end": 9.0, "fit": "free", "x": 0.5, "y": 0.62,
                                     "scale": 0.7, "opacity": 1, "rotate": 0, "anim": "slide_up", "platforms": ["youtube"]})
    pc = analyze.pace(project)
    fast = pc["wpm"] >= 150
    effects["zoom"]["mode"] = "punch" if is_short_source else ("emphasis" if fast else "push")
    if is_short_source:
        effects["transition"] = "punch" if not fast else "whip"
    if not is_short_source and out_dur > 90:
        effects["extras"] = ["soft_glow"] if (analysis.get("video") or {}).get("contrast", 0.2) < 0.15 else []
    presets = ["yt-short", "ig-reel", "fb-reel"] if is_short_source else ["yt-long", "yt-short"]
    return {
        "presets": presets,
        "caption_style": caption_style,
        "captions": {"size_scale": 1.0, "position": "", "primary": brand.get("primary", ""), "highlight": brand.get("highlight", ""),
                     "font": brand.get("font", ""), "italic": "", "uppercase": "", "letter_spacing": "", "outline_scale": "",
                     "shadow_scale": "", "outline_color": ""},
        "burn_captions": True,
        "focus_x": 0.5, "focus_y": 0.5,
        "hook": {"text": hook, "seconds": 3},
        "effects": effects,
        "face_track": "auto",
        "shorts_preset": "yt-short",
        "autopilot": {"shorts": 0 if is_short_source else 3, "language": lang},
    }


def publish_plan(project: dict, outputs: list[dict], connections: list[dict]) -> list[dict]:
    """Which output goes where, with drafted metadata. Only platforms that are connected."""
    by_platform = {c["platform"]: c for c in connections}
    route = {"yt-long": "youtube", "yt-short": "youtube", "ig-reel": "instagram", "fb-reel": "facebook"}
    plan = []
    for a in outputs:
        label = a.get("label") or ""
        platform = "youtube" if label.startswith("short-") else route.get(label)
        if not platform or platform not in by_platform:
            continue
        md = metadata.suggest(project, platform=platform, label=label)
        title = md["title"]
        if label.startswith("short-") or label == "yt-short":
            title = re.sub(r"\s*#shorts\s*$", "", title)[:90] + " #Shorts"
        plan.append({"asset_id": a["id"], "label": label, "platform": platform, "connection_id": by_platform[platform]["id"],
                     "title": title, "description": md["description"], "tags": md["tags"],
                     "privacy": "public" if platform == "youtube" else None, "selected": True})
    return plan
