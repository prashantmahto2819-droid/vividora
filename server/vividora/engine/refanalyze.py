"""Theme Analyzer — a reference video → the *parameters* of its style, as an editable theme.

Only numbers are taken (cut rate, colour, motion, music tempo/energy); nothing of the
reference itself is copied. Every value is marked `measured` (computed from the file) or
`guessed` (a mapping from those numbers to a preset). Captions/text styles are not read
(no OCR here) — the UI says so.
"""

from __future__ import annotations

import math
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from . import ffmpeg, musictag, scenes
from .analyze import _video_stats, auto_grade
from .catalog import GRADE_PRESETS

_GRADE_KEYS = ("exposure", "contrast", "saturation", "vibrance", "temperature", "tint", "highlights", "shadows")


def _motion(path: Path, duration: float) -> float:
    """Mean absolute frame difference at 4 fps, 160 px wide → 0..1 (talking head ≈ 0.03, action ≈ 0.25+)."""
    n_max = 240
    w, h = 160, 90
    cmd = ["ffmpeg", "-v", "error", "-t", f"{min(duration, 60):.2f}", "-i", str(path), "-vf", f"fps=4,scale={w}:{h}",
           "-pix_fmt", "gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    n = min(n_max, len(raw) // (w * h))
    if n < 3:
        return 0.0
    f = np.frombuffer(raw[: n * w * h], dtype=np.uint8).reshape(n, h, w).astype(np.float32) / 255.0
    d = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
    return float(np.clip(np.median(d) * 6, 0, 1))


def closest_grade(stats: dict) -> tuple[str, float]:
    """The look preset whose warmth/saturation/contrast direction is nearest to the reference's picture."""
    sat, warm, con, luma = stats.get("saturation", 0.3), stats.get("warmth", 0.05), stats.get("contrast", 0.2), stats.get("luma", 0.45)
    # the reference relative to a neutral recording → the direction a preset would push
    want = {"saturation": (sat - 0.32) * 2.2, "temperature": (warm - 0.06) * 3.0, "contrast": (con - 0.2) * 2.5,
            "exposure": (luma - 0.45) * 1.5}
    best, bd = "", 9e9
    for gid, g in GRADE_PRESETS.items():
        d = 0.0
        for k, v in want.items():
            d += (float(g.get(k, 0)) - v) ** 2
        d += 0.15 * sum(float(g.get(k, 0)) ** 2 for k in ("tint", "highlights", "shadows"))  # prefer simple looks
        if d < bd:
            best, bd = gid, d
    return best, round(math.sqrt(bd), 3)


def analyze(path: Path) -> dict:
    info = ffmpeg.probe(path)
    dur = float(info.get("duration") or 0)
    if dur < 2:
        raise ValueError("reference video 2 s से छोटी है या पढ़ी नहीं गई")
    span = min(dur, 180.0)
    cuts = scenes.detect(path, threshold=0.28, start=0.0, end=span, min_gap=0.25)
    n_cuts = len(cuts)
    shots = []
    last = 0.0
    for c in cuts:
        shots.append(c["t"] - last)
        last = c["t"]
    shots.append(span - last)
    shots = [s for s in shots if s > 0.05] or [span]
    avg_shot = float(np.mean(shots))
    stats = _video_stats(path, dur) or {}
    motion = _motion(path, dur)
    music = None
    if info.get("has_audio"):
        try:
            music = musictag.analyze(path, "", "")
        except Exception:  # noqa: BLE001
            music = None
    grade_id, dist = closest_grade(stats) if stats else ("", 0.0)
    cpm = n_cuts / (span / 60.0)
    pace = "fast" if avg_shot < 1.2 else "medium" if avg_shot < 3.5 else "slow"
    measured = {"duration": round(dur, 2), "analysed_seconds": round(span, 1), "cuts": n_cuts, "cuts_per_minute": round(cpm, 1),
                "avg_shot": round(avg_shot, 2), "shortest_shot": round(min(shots), 2), "longest_shot": round(max(shots), 2),
                "motion": round(motion, 3), "picture": {k: stats.get(k) for k in ("luma", "contrast", "saturation", "warmth", "tint") if k in stats},
                "music": {k: music.get(k) for k in ("bpm", "energy", "brightness", "loudness") if music and music.get(k) is not None} if music else None,
                "width": info.get("width"), "height": info.get("height")}
    guessed = {"pace": pace, "grade_preset": grade_id, "grade_distance": dist,
               "music_mood": (music or {}).get("moods", [None])[0] if music else None,
               "music_genres": (music or {}).get("genres", []) if music else [],
               "effects_level": "strong" if motion > 0.35 or avg_shot < 0.9 else "subtle" if motion < 0.08 and avg_shot > 3 else "medium",
               "transition": "x_dissolve" if pace == "slow" else "flash" if pace == "fast" else "dip",
               "zoom": motion < 0.12 and avg_shot > 2.5,
               "captions": "unknown — OCR नहीं है, text style नहीं पढ़ी गई"}
    return {"measured": measured, "guessed": guessed, "theme": build_theme(measured, guessed)}


def build_theme(m: dict, g: dict) -> dict:
    pace = g["pace"]
    mood = g.get("music_mood") or ("energetic" if pace == "fast" else "cinematic" if pace == "slow" else "motivational")
    strong = g["effects_level"] == "strong"
    min_cut = max(0.3, round(m["shortest_shot"], 2)) if pace == "fast" else 0.6 if pace == "medium" else 0.9
    max_cut = min(4.0, max(min_cut + 0.4, round(m["avg_shot"] * 1.4, 2)))
    return {"label": "इस video जैसा", "emoji": "🔍", "hint": f"reference से: {m['cuts_per_minute']} cuts/min, {g['grade_preset'] or 'neutral'} look, {mood} music",
            "swatch": ["#4E7CFF", "#1B1F2A"],
            "caption_style": "karaoke" if pace != "slow" else "minimal", "text_style": "bold_white",
            "look": "none", "grade_preset": g["grade_preset"] or "",
            "transition": g["transition"], "transition_duration": 0.25 if pace == "fast" else 0.45,
            "stack": [{"id": "tr_shake", "params": {}}] if strong else [],
            "extras": ["grain"] if pace == "slow" else [],
            "zoom": {"enabled": bool(g["zoom"]), "strength": 0.9},
            "music": {"mood": mood, "volume": 0.18 if pace == "fast" else 0.15, "duck_amount": 0.6},
            "voice": "studio", "slowmo": pace != "fast", "speed_ramp": strong,
            "montage": {"pace": pace, "effects_level": g["effects_level"], "min_cut": min_cut, "max_cut": max_cut,
                        "look": f"grade:{g['grade_preset']}" if g["grade_preset"] else "auto",
                        "fx_strong": ["glitch", "flash", "punch"] if strong else ["zoom_in", "flash"],
                        "fx_soft": ["zoom_in", "zoom_out"] if pace != "slow" else ["zoom_in", "black_fade"],
                        "intro": pace != "fast", "outro": True},
            "reference": {"measured": m, "guessed": {k: v for k, v in g.items() if k != "captions"}}}
