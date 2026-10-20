"""Voice notes from WhatsApp → text (small Whisper model on CPU; a 10-second note takes a few seconds)."""

from __future__ import annotations

import base64
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path

_MODEL = None


def _model():
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel
        _MODEL = WhisperModel(os.getenv("VOICE_CMD_MODEL", "small"), device="cpu", compute_type="int8",
                              download_root=os.getenv("WHISPER_CACHE") or None)
    return _MODEL


def transcribe_any(src: str) -> str:
    """src: http(s) URL or base64 (optionally a data: URI) of an audio file (ogg/opus from WhatsApp)."""
    with tempfile.TemporaryDirectory(prefix="vcmd_") as td:
        raw = Path(td) / "in.bin"
        try:
            if str(src).startswith(("http://", "https://")):
                with urllib.request.urlopen(src, timeout=60) as r:
                    raw.write_bytes(r.read(25 * 1024 * 1024))
            else:
                b = str(src).split(",", 1)[-1] if str(src).startswith("data:") else str(src)
                raw.write_bytes(base64.b64decode(b))
            wav = Path(td) / "a.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-ac", "1", "-ar", "16000", "-t", "120", str(wav)], check=True)
            segs, _ = _model().transcribe(str(wav), language="hi", beam_size=3, vad_filter=True,
                                          initial_prompt="Vividora, इस वीडियो के शॉर्ट्स बना दो, render करो, music लगाओ।")
            return " ".join(s.text.strip() for s in segs).strip()
        except Exception:  # noqa: BLE001
            return ""
