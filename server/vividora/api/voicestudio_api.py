"""VoiceStudio API — proxy to self-hosted OmniVoice TTS (41 models, 646 languages).

GET  /voicestudio/health          service health check
GET  /voicestudio/models          available TTS models
GET  /voicestudio/voices          available voices (optional ?model= filter)
POST /voicestudio/synthesise      text → audio file (WAV/MP3)
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from starlette.requests import Request
from starlette.responses import FileResponse
from starlette.routing import Route

from ..engine import voicestudio as vs
from .deps import ApiError, body, ok, require

log = logging.getLogger("vividora.api.voicestudio")


async def health_check(request: Request):
    """Public health — no auth."""
    return ok(vs.health())


@require("viewer")
async def list_models(request: Request, user: dict):
    return ok({"models": vs.models()})


@require("viewer")
async def list_voices(request: Request, user: dict):
    model = request.query_params.get("model")
    return ok({"voices": vs.voices(model)})


@require("editor")
async def synthesise(request: Request, user: dict):
    """POST JSON {text, model?, voice?, language?, speed?} → audio file download."""
    d = await body(request)
    text = str(d.get("text") or "").strip()
    if not text:
        raise ApiError(422, "text लिखें")
    if len(text) > 5000:
        raise ApiError(422, "text बहुत लंबा (max 5000 chars)")

    h = vs.health()
    if h.get("status") != "ok":
        raise ApiError(503, f"VoiceStudio उपलब्ध नहीं: {h.get('error', 'offline')}")

    model = d.get("model")
    voice = d.get("voice")
    language = str(d.get("language") or "hi")[:10]
    speed = float(d.get("speed") or 1.0)

    with tempfile.TemporaryDirectory(prefix="vs_tts_") as td:
        out = Path(td) / "output.wav"
        try:
            vs.synthesise(text, model=model, voice=voice, language=language, speed=speed, out=out)
        except RuntimeError as e:
            raise ApiError(502, f"TTS failed: {e}")

        if not out.exists() or out.stat().st_size < 100:
            raise ApiError(502, "VoiceStudio ने audio नहीं बनाया")

        # Return the audio file directly
        return FileResponse(out, media_type="audio/wav",
                            headers={"Content-Disposition": 'attachment; filename="voicestudio_output.wav"'})


routes = [
    Route("/voicestudio/health", health_check),
    Route("/voicestudio/models", list_models),
    Route("/voicestudio/voices", list_voices),
    Route("/voicestudio/synthesise", synthesise, methods=["POST"]),
]
