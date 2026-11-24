"""Background music from a description, on fal.ai (FAL_KEY) — paid per minute of music, nothing runs in between.

Default model: cassetteai/music-generator ({prompt, duration 10–180 s} → {audio_file: {url}}), $0.02 per output minute
(PRICE_AI_MUSIC_MIN). Another fal music model with the same two inputs can be named in FAL_MUSIC_MODEL.
"""

from __future__ import annotations

import os
import subprocess
import urllib.request
from pathlib import Path

from . import cloudasr, meter

MOODS = {
    "calm": ("शांत / soft", "calm soft ambient background music, warm pads, gentle piano, slow tempo 70 BPM"),
    "motivational": ("Motivational / जोश", "uplifting motivational cinematic background music, building strings, steady drums, hopeful, 110 BPM"),
    "corporate": ("Corporate / साफ़-सुथरा", "clean modern corporate background music, light guitar plucks, soft claps, positive, 105 BPM"),
    "lofi": ("Lo-fi / chill", "chill lo-fi hip-hop beat, mellow electric piano, vinyl crackle, relaxed drums, 85 BPM"),
    "emotional": ("भावुक / emotional", "emotional cinematic piano and strings, slow, touching, 65 BPM"),
    "energetic": ("तेज़ / energetic", "energetic upbeat electronic pop background music, punchy drums, bright synths, 125 BPM"),
    "suspense": ("Suspense / रहस्य", "dark suspenseful underscore, low drones, ticking percussion, tension, 90 BPM"),
    "indian": ("भारतीय / Indian", "Indian fusion background music, sitar and bansuri flute melody, tabla groove, modern soft beat, 95 BPM"),
    "devotional": ("भक्ति / peaceful", "peaceful Indian devotional instrumental, bansuri flute, tanpura drone, soft bells, slow"),
    "podcast": ("Podcast के नीचे", "very subtle minimal background bed for a talking podcast, soft warm pads, no melody on top, unobtrusive, 80 BPM"),
}


def ready() -> bool:
    return bool(os.getenv("FAL_KEY"))


def model() -> str:
    return (os.getenv("FAL_MUSIC_MODEL") or "cassetteai/music-generator").strip("/")


def build_prompt(mood: str | None, text: str | None) -> str:
    base = MOODS.get(mood or "", ("", ""))[1]
    text = " ".join(str(text or "").split())[:300]
    p = ", ".join(x for x in (text, base) if x) or MOODS["calm"][1]
    return p + ". Instrumental only, no vocals, no singing."


def estimate_usd(seconds: float) -> float:
    return round(meter.price("ai_music") * max(10.0, float(seconds)) / 60.0, 4)


def generate(prompt: str, seconds: float, out: Path) -> Path:
    """→ an MP3 at `out`. Raises meter.SpendCap when the month's limit is used up."""
    if not ready():
        raise ValueError("fal.ai की key नहीं है — Settings → API & Keys में FAL_KEY डालें")
    secs = int(max(10, min(180, round(float(seconds)))))
    meter.check("ai_music")
    res = cloudasr.fal_run(model(), {"prompt": prompt[:600], "duration": secs}, max_wait=900)
    f = res.get("audio_file") or res.get("audio") or {}
    url = f.get("url") if isinstance(f, dict) else None
    if not url:
        raise RuntimeError("fal.ai ने music नहीं लौटाया: " + str(res)[:160])
    meter.add("ai_music", prompt[:60], secs / 60.0)
    raw = out.with_suffix(".bin")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Vividora/1.0"}), timeout=300) as r:
        raw.write_bytes(r.read())
    try:
        p = subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-i", str(raw), "-vn", "-ac", "2", "-ar", "44100",
                            "-c:a", "libmp3lame", "-b:a", "192k", str(out)], capture_output=True, text=True)
        if p.returncode != 0 or not out.exists():
            raise RuntimeError("music फ़ाइल नहीं खुली: " + (p.stderr or "")[-200:])
    finally:
        raw.unlink(missing_ok=True)
    return out
