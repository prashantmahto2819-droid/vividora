"""Output QA: checks every finished render before anyone is asked to approve it.

check()  — black frames at the very start, integrated loudness vs the platform target,
           a silent / missing audio track, captions that should be there but are empty.
fix_black_start() — cuts leading black frames off (re-encode, a few seconds of work).

Cheap: only the first seconds are decoded for the black check; loudness reads the
audio stream only.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


def _ff(args: list[str], timeout: float = 600) -> str:
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *args], capture_output=True, text=True, timeout=timeout)
        return r.stderr
    except (OSError, subprocess.TimeoutExpired):
        return ""


def leading_black(path: Path, window: float = 6.0) -> float:
    """Seconds of black picture at the start (0 if the video starts with an image)."""
    err = _ff(["-t", f"{window}", "-i", str(path), "-vf", "blackdetect=d=0.05:pix_th=0.10", "-an", "-f", "null", "-"], 120)
    for m in re.finditer(r"black_start:\s*([\d.]+)\s+black_end:\s*([\d.]+)", err):
        if float(m.group(1)) <= 0.05:
            return round(float(m.group(2)), 3)
    return 0.0


def loudness(path: Path) -> float | None:
    """Integrated loudness (LUFS) of the audio track; None without audio."""
    err = _ff(["-i", str(path), "-vn", "-af", "ebur128=framelog=quiet", "-f", "null", "-"])
    m = re.findall(r"I:\s*(-?[\d.]+|-inf)\s*LUFS", err)
    if not m or m[-1] == "-inf":
        return None
    return float(m[-1])


def has_audio(path: Path) -> bool:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
                           capture_output=True, text=True, timeout=60)
        return bool(r.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        return False


def fix_black_start(path: Path, cut: float, encoder_preset: str | None = None) -> bool:
    """Drop the first `cut` seconds (picture and sound together) in place."""
    tmp = path.with_name(path.stem + "_qa.mp4")
    try:
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{cut:.3f}", "-i", str(path), "-map", "0",
                            "-c:v", "libx264", "-preset", encoder_preset or "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "192k",
                            "-movflags", "+faststart", str(tmp)], capture_output=True, text=True, timeout=3600)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if r.returncode != 0 or not tmp.exists() or tmp.stat().st_size < 1000:
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(path)
    return True


def check(path: Path, *, target_lufs: float | None = -14.0, expect_audio: bool = True, expect_captions: bool = False,
          caption_words: int = 0, duration: float = 0.0, fix: bool = True, encoder_preset: str | None = None) -> dict:
    """→ {"black_start", "lufs", "fixed": [...], "warnings": [...]} (warnings in Hindi, for the owner)."""
    out: dict = {"fixed": [], "warnings": []}
    black = leading_black(path)
    out["black_start"] = black
    if black >= 0.3:
        if fix and black < max(1.0, duration - 2.0) and fix_black_start(path, black, encoder_preset):
            out["fixed"].append(f"शुरू के {black:.1f}s काले frames हटाए")
            out["black_start"] = 0.0
        else:
            out["warnings"].append(f"शुरू में {black:.1f}s काली स्क्रीन")
    if expect_audio:
        if not has_audio(path):
            out["warnings"].append("वीडियो में आवाज़ नहीं")
            out["lufs"] = None
        else:
            lufs = loudness(path)
            out["lufs"] = lufs
            if lufs is None or lufs < -40:
                out["warnings"].append("आवाज़ लगभग चुप है")
            elif target_lufs is not None and abs(lufs - target_lufs) > 3:
                out["warnings"].append(f"loudness {lufs:.0f} LUFS (platform {target_lufs:.0f})")
    if expect_captions and caption_words == 0:
        out["warnings"].append("captions चालू हैं पर बोले शब्द नहीं मिले — captions खाली")
    return out
