"""YouTube → Shorts/Reels converter: download a YouTube video with yt-dlp,
extract metadata, and find the best 30–60 s highlight segments for vertical
short-form content.

Only for the creator's own videos — the UI shows a copyright disclaimer.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from . import shorts as shorts_eng

log = logging.getLogger("vividora.ytshorts")

# yt-dlp format: best mp4 ≤ 1080p with audio, fallback to best available
_FMT = "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best"


def download_yt(url: str, out_dir: Path) -> dict:
    """Download a YouTube video to *out_dir*, return path + metadata dict.

    Raises ValueError for invalid / unreachable URLs.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_tpl = str(out_dir / "%(id)s.%(ext)s")

    # First: fetch metadata without downloading
    meta_cmd = ["yt-dlp", "--no-download", "--print-json", "--no-playlist", url]
    try:
        meta_raw = subprocess.run(meta_cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        raise ValueError("YouTube से जवाब नहीं आया — URL जाँचें और फिर कोशिश करें")
    if meta_raw.returncode != 0:
        err = (meta_raw.stderr or "").strip().split("\n")[-1][:200]
        raise ValueError(f"video नहीं मिला — URL जाँचें: {err}")

    info = json.loads(meta_raw.stdout)
    title = info.get("title") or "YouTube Video"
    duration = float(info.get("duration") or 0)
    video_id = info.get("id") or "unknown"

    if duration <= 0:
        raise ValueError("live या 0-length video — download नहीं हो सकता")
    if duration > 7200:
        raise ValueError("2 घंटे से लंबी video इस tool से नहीं — छोटी video चुनें")

    # Download
    dl_cmd = [
        "yt-dlp", "-f", _FMT, "--no-playlist", "--merge-output-format", "mp4",
        "-o", out_tpl, "--no-overwrites", url,
    ]
    try:
        dl = subprocess.run(dl_cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        raise ValueError("download बहुत देर लगा — internet connection जाँचें")
    if dl.returncode != 0:
        err = (dl.stderr or "").strip().split("\n")[-1][:200]
        raise ValueError(f"download असफल: {err}")

    # Find the downloaded file
    candidates = sorted(out_dir.glob(f"{video_id}.*"), key=lambda p: p.stat().st_size, reverse=True)
    if not candidates:
        # fallback: any mp4 in the directory
        candidates = sorted(out_dir.glob("*.mp4"), key=lambda p: p.stat().st_size, reverse=True)
    if not candidates:
        raise ValueError("download हुआ लेकिन file नहीं मिली")

    path = candidates[0]
    return {
        "path": path,
        "title": _clean_title(title),
        "duration": duration,
        "video_id": video_id,
        "channel": info.get("channel") or info.get("uploader") or "",
        "thumbnail": info.get("thumbnail") or "",
        "description": (info.get("description") or "")[:500],
    }


def find_highlights(transcript: dict, duration: float, edl: dict | None = None, *,
                    count: int = 5, min_len: float = 25.0, max_len: float = 58.0,
                    language: str = "hi") -> list[dict]:
    """Pick the best short-form segments from a transcript.

    Delegates to the existing shorts.plan engine (which already has hook-word
    scoring, LLM refinement, etc.) with parameters tuned for the converter.
    """
    return shorts_eng.plan(
        transcript, duration, edl,
        count=count, min_len=min_len, max_len=max_len, language=language,
    )


def _clean_title(title: str) -> str:
    """Strip common YouTube title noise."""
    t = re.sub(r"\s*[|\-–—]\s*(Full Video|Official|HD|4K|Lyrics|Audio).*$", "", title, flags=re.I)
    t = re.sub(r"\s*\(?(Official|Full|HD|4K|Lyric)\)?.*$", "", t, flags=re.I)
    return t.strip()[:80] or "YouTube Video"
