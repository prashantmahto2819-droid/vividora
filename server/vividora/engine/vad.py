"""Where is somebody speaking? — Silero VAD (the small model that ships inside faster-whisper, CPU, no download).

The loudness rule (ffmpeg silencedetect) calls a fan, traffic or music "sound" and a soft word "silence". A voice model
does not: silence cuts stay right in a noisy room. Switched on in API & Keys → "चुप्पी कैसे पहचानें" (SILENCE_ENGINE=silero);
whenever the model is missing or fails, the loudness rule is used as before.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

log = logging.getLogger("vividora.vad")
SR = 16000


def engine_setting() -> str:
    v = (os.getenv("SILENCE_ENGINE") or "loudness").strip().lower()
    return v if v in ("loudness", "silero") else "loudness"


def _load(path: Path):
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                         capture_output=True, timeout=1800).stdout
    return np.frombuffer(raw[:len(raw) // 2 * 2], dtype=np.int16).astype(np.float32) / 32768.0


def speech(path: Path, *, min_silence: float = 0.45, pad: float = 0.06, threshold: float = 0.5, detect=None) -> list[tuple[float, float]] | None:
    """Spoken stretches [(start, end)] in seconds, or None when the voice model cannot be used here.
    `detect(audio, min_silence_ms, pad_ms, threshold) → [{"start": sample, "end": sample}]` can be given (tests)."""
    try:
        audio = _load(Path(path))
        if not len(audio):
            return None
        if detect is None:
            from faster_whisper.vad import VadOptions, get_speech_timestamps

            def detect(a, ms, pad_ms, th):
                return get_speech_timestamps(a, VadOptions(threshold=th, min_silence_duration_ms=ms, speech_pad_ms=pad_ms,
                                                           min_speech_duration_ms=120))
        got = detect(audio, int(min_silence * 1000), int(pad * 1000), threshold)
        out = sorted((max(0.0, float(c["start"]) / SR), float(c["end"]) / SR) for c in got if c["end"] > c["start"])
        return out
    except Exception as e:  # noqa: BLE001 — never fail the cut over this; the caller falls back
        log.warning("voice detection not available (%s) — using the loudness rule", str(e)[:160])
        return None


def gaps(regions: list[tuple[float, float]], duration: float, min_dur: float = 0.45) -> list[tuple[float, float]]:
    """The stretches between the spoken ones (the same shape ffmpeg.silences returns)."""
    out, pos = [], 0.0
    for a, b in sorted(regions):
        if a - pos >= min_dur:
            out.append((round(pos, 3), round(a, 3)))
        pos = max(pos, b)
    if duration - pos >= min_dur:
        out.append((round(pos, 3), round(duration, 3)))
    return out


def silences(path: Path, duration: float, min_dur: float = 0.45, detect=None) -> list[tuple[float, float]] | None:
    """Silent stretches by the voice model; None → use ffmpeg.silences. A recording where the model hears no voice at all
    also returns None (music-only clips must not be cut away as one long silence)."""
    reg = speech(path, min_silence=min_dur, detect=detect)
    if not reg:
        return None
    return gaps(reg, duration, min_dur)
