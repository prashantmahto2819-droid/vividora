"""What the paid services cost — counted where the call is made, in whichever process makes it.

`check(service)` before a paid call (raises SpendCap when this month's limit is used up), `add(...)` after it. Where the
numbers go is set once per process with `configure()`: the API writes its database (spend.py), a worker reports to the
API with the job it is running. Prices are estimates (per unit, editable through the environment) — the provider's own
bill is the truth; this is here so a month can never run away unnoticed.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger("vividora.meter")

# service → (env with the price, default USD, unit, label)
PRICES: dict[str, tuple[str, float, str, str]] = {
    "fal_whisper": ("PRICE_FAL_WHISPER_MIN", 0.006, "audio-minute", "fal.ai Whisper (transcript)"),
    "runpod_whisper": ("PRICE_RUNPOD_SEC", 0.0004, "GPU-second", "RunPod serverless (transcript)"),
    "ai_video": ("AI_VIDEO_PRICE_PER_SEC", 0.03, "video-second", "AI video (fal.ai)"),
    "ai_image": ("PRICE_AI_IMAGE", 0.0, "image", "AI image"),
    "elevenlabs": ("PRICE_ELEVENLABS_1K", 0.2, "1000 chars", "ElevenLabs voice"),
    "fal_tts": ("PRICE_FAL_TTS_1K", 0.025, "1000 chars", "fal.ai voice"),
    "ai_music": ("PRICE_AI_MUSIC_MIN", 0.02, "minute", "AI music (fal.ai)"),
    "runpod_tts": ("PRICE_RUNPOD_TTS_1K", 0.05, "1000 chars", "RunPod voice (MiniMax)"),
    "runpod_tts_sec": ("PRICE_RUNPOD_TTS_SEC", 0.001, "audio-second", "RunPod voice (Chatterbox)"),
    "runpod_video": ("PRICE_RUNPOD_VIDEO_SEC", 0.02, "video-second", "AI video (RunPod)"),
}


class SpendCap(RuntimeError):
    """This month's spending limit is used up — the paid call was not made."""


_sink = None
_left = None
_local = 0.0          # added in this process since the last configure() (a worker's view of the budget between claims)


_track_local = True


def configure(sink=None, left=None, *, track_local: bool = True) -> None:
    """track_local=False when `left()` already sees everything this process adds (the API writes straight to its database)."""
    global _sink, _left, _local, _track_local
    _sink, _left, _local, _track_local = sink, left, 0.0, track_local


def price(service: str) -> float:
    env, default, _, _ = PRICES.get(service, ("", 0.0, "", ""))
    try:
        v = os.getenv(env) if env else None
        return max(0.0, float(v)) if v not in (None, "") else default
    except ValueError:
        return default


def left() -> float | None:
    """USD still allowed this month, None when there is no limit."""
    if _left is None:
        return None
    try:
        v = _left()
    except Exception:  # noqa: BLE001
        return None
    return None if v is None else float(v) - (_local if _track_local else 0.0)


def check(service: str) -> None:
    v = left()
    if v is not None and v <= 0 and price(service) > 0:
        raise SpendCap(f"इस महीने की खर्च-सीमा पूरी हो गई — {PRICES.get(service, ('', 0, '', service))[3]} नहीं चलाया। API & Keys → 💰 खर्च में सीमा बढ़ाएँ।")


def add(service: str, what: str, units: float, usd: float | None = None, **extra) -> float:
    """Record one paid call. Returns the USD counted. Never raises (the work is already done)."""
    global _local
    cost = round(float(usd if usd is not None else price(service) * float(units or 0)), 5)
    _local += cost
    entry = {"service": service, "what": str(what)[:160], "units": round(float(units or 0), 3), "unit": PRICES.get(service, ("", 0, "", ""))[2], "usd": cost, **extra}
    try:
        if _sink:
            _sink(entry)
    except Exception as e:  # noqa: BLE001
        log.warning("spend not recorded (%s): %s", service, e)
    return cost
