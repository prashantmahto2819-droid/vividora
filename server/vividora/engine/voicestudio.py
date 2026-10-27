"""VoiceStudio (OmniVoice) proxy — 41 TTS models, 646 languages, running on localhost:3900.

This module proxies TTS requests to the self-hosted VoiceStudio API.  It plugs into
Vividora's existing TTS pipeline as another backend alongside Parler / Kokoro / ElevenLabs.

VoiceStudio API endpoints (localhost:3900):
  GET  /api/health            → {"status":"ok","device":"cpu","version":"0.5.7"}
  GET  /api/models            → list of loaded TTS models
  GET  /api/voices?model=...  → voices for a model
  POST /api/tts               → synthesise (returns audio file)
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path

from ..config import settings

log = logging.getLogger("vividora.voicestudio")

_TIMEOUT = 120  # seconds — TTS on CPU can be slow


def _url(path: str) -> str:
    return f"{settings.voicestudio_url.rstrip('/')}{path}"


def health() -> dict:
    """Check if VoiceStudio is reachable."""
    try:
        with urllib.request.urlopen(_url("/api/health"), timeout=5) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"status": "error", "error": str(e)}


def models() -> list[dict]:
    """List available TTS models."""
    try:
        with urllib.request.urlopen(_url("/api/models"), timeout=10) as r:
            data = json.loads(r.read())
            return data if isinstance(data, list) else data.get("models", [])
    except Exception as e:
        log.warning("VoiceStudio models list failed: %s", e)
        return []


def voices(model: str | None = None) -> list[dict]:
    """List available voices, optionally filtered by model."""
    try:
        url = _url("/api/voices")
        if model:
            url += f"?model={urllib.request.quote(model)}"
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
            return data if isinstance(data, list) else data.get("voices", [])
    except Exception as e:
        log.warning("VoiceStudio voices list failed: %s", e)
        return []


def synthesise(text: str, model: str | None = None, voice: str | None = None,
               language: str = "hi", speed: float = 1.0, out: Path | None = None) -> Path:
    """Synthesise text → WAV file via VoiceStudio API.

    Args:
        text:     The text to speak.
        model:    TTS model name (e.g. "coqui/XTTS-v2").  None = server default.
        voice:    Voice / speaker name.  None = server default.
        language: BCP-47 or ISO-639 language code.
        speed:    Speech speed multiplier (0.5 – 2.0).
        out:      Output .wav path.  Required.

    Returns the path to the generated WAV file.
    """
    if out is None:
        raise ValueError("out path is required")

    payload: dict = {"text": text, "language": language}
    if model:
        payload["model"] = model
    if voice:
        payload["voice"] = voice
    if speed and abs(speed - 1.0) > 0.01:
        payload["speed"] = round(max(0.5, min(2.0, speed)), 2)

    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        _url("/api/tts"),
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            audio = r.read()
    except urllib.error.HTTPError as e:
        err = e.read().decode(errors="replace")[:500]
        raise RuntimeError(f"VoiceStudio TTS error ({e.code}): {err}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"VoiceStudio unreachable: {e.reason}") from e

    if not audio:
        raise RuntimeError("VoiceStudio returned empty audio")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(audio)
    return out


def is_available() -> bool:
    """Quick check: is the VoiceStudio service running?"""
    h = health()
    return h.get("status") == "ok"
