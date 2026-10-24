"""Music library tagging — bpm, loudness, energy, brightness → mood / genre tags.

Heuristics only (no model, no network): tempo and energy from the beat analysis
that the montage already does, brightness = spectral centroid, loudness via
ffmpeg ebur128. Words in the file name / user tags count too ("piano", "lofi").
Everything is labelled `guessed` in the UI; the user can correct the tags.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import numpy as np

from . import ffmpeg
from .montage import SR, _decode, onset_envelope, tempo

MOODS = ["motivational", "emotional", "romantic", "energetic", "cinematic", "calm", "happy", "devotional", "story", "news"]
GENRES = ["piano", "lofi", "electronic", "orchestral", "acoustic", "hiphop", "pop", "corporate", "ambient", "indian"]

_WORDS = {
    "motivational": ("motivat", "rise", "inspir", "epic", "hero", "power"),
    "emotional": ("emotion", "sad", "tear", "cry", "melanch", "heartbreak"),
    "romantic": ("romantic", "love", "pyar", "ishq", "wedding"),
    "energetic": ("energetic", "workout", "gym", "hype", "party", "dance", "edm"),
    "cinematic": ("cinematic", "tension", "trailer", "dark", "thriller", "suspense"),
    "calm": ("calm", "chill", "relax", "peace", "meditat", "sleep", "soft"),
    "happy": ("happy", "upbeat", "fun", "joy", "bright", "summer"),
    "devotional": ("devotion", "bhajan", "bhakti", "temple", "mantra", "aarti", "shiv", "krishna", "ram"),
    "story": ("story", "narrat", "documentary", "journey"),
    "news": ("news", "corporate", "business", "anchor", "report"),
    "piano": ("piano",), "lofi": ("lofi", "lo-fi"), "electronic": ("electro", "synth", "edm", "techno", "house"),
    "orchestral": ("orchestr", "strings", "cinematic", "epic"), "acoustic": ("acoustic", "guitar", "folk"),
    "hiphop": ("hiphop", "hip-hop", "trap", "rap", "beat"), "pop": ("pop",), "corporate": ("corporate", "business", "news"),
    "ambient": ("ambient", "drone", "pad", "atmos"), "indian": ("indian", "sitar", "tabla", "flute", "bansuri", "desi", "bollywood"),
}


def _loudness(path: Path) -> float | None:
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-t", "120", "-i", str(path), "-filter_complex", "ebur128=peak=none",
                            "-f", "null", "-"], capture_output=True, text=True, timeout=120)
        m = re.findall(r"I:\s+(-?\d+(?:\.\d+)?) LUFS", r.stderr or "")
        return round(float(m[-1]), 1) if m else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _brightness(y: np.ndarray) -> float:
    """Spectral centroid (Hz) averaged over 2048-sample frames → 0..1 (200 Hz dark … 4 kHz bright)."""
    n = 2048
    if len(y) < n * 4:
        return 0.5
    step = n * 4
    freqs = np.fft.rfftfreq(n, 1 / SR)
    cents = []
    for i in range(0, len(y) - n, step):
        spec = np.abs(np.fft.rfft(y[i:i + n] * np.hanning(n)))
        tot = float(spec.sum())
        if tot > 1e-6:
            cents.append(float((spec * freqs).sum() / tot))
    if not cents:
        return 0.5
    c = float(np.median(cents))
    return float(np.clip((np.log(max(c, 1)) - np.log(200)) / (np.log(4000) - np.log(200)), 0, 1))


def analyze(path: Path, name: str = "", tags: str = "") -> dict:
    """→ {bpm, duration, loudness, energy, brightness, dynamics, moods[], genres[], analysed: True}"""
    y = _decode(path, 150)
    dur = len(y) / SR
    if dur < 1.0:
        raise ValueError("music file में आवाज़ नहीं मिली")
    try:
        full = float(ffmpeg.probe(path).get("duration") or dur)
    except Exception:  # noqa: BLE001
        full = dur
    env = onset_envelope(y)
    bpm = float(tempo(env))
    # energy: RMS per second, normalised against a typical mastered level; dynamics = spread
    win = SR
    rms = np.array([float(np.sqrt(np.mean(y[i:i + win] ** 2))) for i in range(0, max(1, len(y) - win), win)]) if len(y) > win else np.array([0.0])
    energy = float(np.clip(np.mean(rms) / 0.25, 0, 1))
    dynamics = float(np.clip((np.percentile(rms, 90) - np.percentile(rms, 10)) / 0.25, 0, 1)) if len(rms) > 3 else 0.0
    bright = _brightness(y)
    loud = _loudness(path)
    text = f"{name} {tags}".lower()
    moods, genres = guess_tags(bpm, energy, bright, dynamics, text)
    return {"bpm": round(bpm, 1), "duration": round(full, 2), "loudness": loud, "energy": round(energy, 3),
            "brightness": round(bright, 3), "dynamics": round(dynamics, 3), "moods": moods, "genres": genres, "analysed": True}


def guess_tags(bpm: float, energy: float, bright: float, dynamics: float, text: str = "") -> tuple[list[str], list[str]]:
    score: dict[str, float] = {k: 0.0 for k in [*MOODS, *GENRES]}
    for tag, words in _WORDS.items():
        if any(w in text for w in words):
            score[tag] += 2.0
    slow, mid, fast = bpm < 85, 85 <= bpm < 115, bpm >= 115
    if slow and energy < 0.35:
        score["emotional"] += 1.2
        score["calm"] += 1.0
        score["piano" if bright < 0.45 else "ambient"] += 0.8
    if slow and bright >= 0.45 and energy < 0.5:
        score["romantic"] += 0.9
    if mid and 0.3 <= energy < 0.7:
        score["motivational"] += 1.0
        score["story"] += 0.7
    if mid and bright < 0.4:
        score["cinematic"] += 0.8
        score["orchestral"] += 0.5
    if fast and energy >= 0.5:
        score["energetic"] += 1.3
        score["electronic" if bright >= 0.5 else "hiphop"] += 0.8
    if fast and bright >= 0.55 and energy < 0.75:
        score["happy"] += 0.9
        score["pop"] += 0.6
    if dynamics >= 0.45 and bright < 0.5:
        score["cinematic"] += 0.6
    if slow and bright < 0.42 and 0.25 <= energy < 0.55:
        score["lofi"] += 1.0
    if mid and dynamics < 0.2:
        score["corporate"] += 0.8
        score["news"] += 0.5
    moods = [k for k, v in sorted(((k, score[k]) for k in MOODS), key=lambda kv: -kv[1]) if v >= 0.9][:3]
    genres = [k for k, v in sorted(((k, score[k]) for k in GENRES), key=lambda kv: -kv[1]) if v >= 0.8][:2]
    if not moods:
        moods = ["energetic" if fast else "calm" if slow else "story"]
    return moods, genres


def commercial_ok(license: str | None) -> bool | None:
    """From the licence text: True = commercial use fine, False = NC / unknown restriction, None = not stated."""
    s = (license or "").lower()
    if not s:
        return None
    if "nc" in s.replace("cc0", "") or "non-commercial" in s or "noncommercial" in s or "personal" in s:
        return False
    if any(w in s for w in ("cc0", "public domain", "commercial", "royalty", "cc by", "cc-by", "pixabay", "vividora", "own", "starter", "synthetic")):
        return True
    return None
