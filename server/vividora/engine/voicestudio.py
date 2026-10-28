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


def _get(path: str, timeout: int = 10):
    with urllib.request.urlopen(_url(path), timeout=timeout) as r:
        return json.loads(r.read())


def health() -> dict:
    """Check if VoiceStudio is reachable and its models are loaded."""
    try:
        h = _get("/health", 5)
    except urllib.error.HTTPError as e:  # 503 while the ML runtime is still loading
        try:
            d = json.loads(e.read())
        except Exception:  # noqa: BLE001
            d = {}
        return {"status": "error", "error": str(d.get("detail") or f"HTTP {e.code}")[:200]}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error": str(e)}
    return h if isinstance(h, dict) and h.get("status") else {"status": "ok", **(h if isinstance(h, dict) else {})}


def models() -> list[dict]:
    """TTS models (OpenAI-style /v1/models)."""
    try:
        data = _get("/v1/models")
        items = data.get("data", data) if isinstance(data, dict) else data
        return [{"id": m.get("id"), "name": m.get("id")} if isinstance(m, dict) else {"id": m, "name": m} for m in items]
    except Exception as e:  # noqa: BLE001
        log.warning("VoiceStudio models list failed: %s", e)
        return []


def voices(model: str | None = None) -> list[dict]:
    """Voice profiles (OpenAI-style /v1/audio/voices)."""
    try:
        data = _get("/v1/audio/voices")
        items = data.get("voices", data.get("data", data)) if isinstance(data, dict) else data
        out = []
        for v in items:
            if isinstance(v, dict):
                vid = v.get("id") or v.get("name")
                out.append({"id": vid, "name": v.get("name") or vid})
            else:
                out.append({"id": v, "name": v})
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("VoiceStudio voices list failed: %s", e)
        return []


def synthesise(text: str, model: str | None = None, voice: str | None = None,
               language: str = "hi", speed: float = 1.0, out: Path | None = None) -> Path:
    """Text → WAV via VoiceStudio's OpenAI-compatible POST /v1/audio/speech."""
    if out is None:
        raise ValueError("out path is required")
    payload: dict = {"model": model or "omnivoice", "input": text, "voice": voice or "default",
                     "response_format": "wav"}
    if speed and abs(speed - 1.0) > 0.01:
        payload["speed"] = round(max(0.25, min(4.0, speed)), 2)

    def _post(pl: dict) -> bytes:
        req = urllib.request.Request(_url("/v1/audio/speech"), data=json.dumps(pl).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            return r.read()

    try:
        try:
            audio = _post({**payload, "language": language})
        except urllib.error.HTTPError as e:
            if e.code not in (400, 422):  # this build rejects the extra "language" field
                raise
            audio = _post(payload)  # this build rejects the extra "language" field
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
