"""Voice-over API — text → speech (any TTS preset) saved to the library as kind "voice", for the editor's
"3D & Voice" tab. Synthesis on CPU can take minutes (Cloudflare cuts requests at 100 s) → background thread + polling.

POST /voiceover        {text, voice?, lang?, speed?, name?} → 202 {job_id}
GET  /voiceover/{id}   → {status: running|done|failed, error, item, seconds}
"""

from __future__ import annotations

import logging
import tempfile
import threading
import time
import uuid
from pathlib import Path

from starlette.requests import Request
from starlette.routing import Route

from .. import db, service
from .deps import ApiError, body, ok, require

log = logging.getLogger("vividora.api.voiceover")

MAX_TEXT = 4000
_JOBS: dict[str, dict] = {}  # in-memory state of runs; the browser polls
_LOCK = threading.Lock()


def _default_voice() -> dict | None:
    """Prefer the self-hosted VoiceStudio voice (works on the CPU server), else the first usable preset."""
    from ..engine import tts
    voices = tts.available_voices()
    return next((v for v in voices if v.get("engine") == "voicestudio"), None) or (voices[0] if voices else None)


def _run(job_id: str, ws: str, user_id: str, text: str, voice: dict, lang: str, speed: float, name: str):
    from ..engine import tts
    from .library import _add_file, _view
    st = _JOBS[job_id]
    try:
        with tempfile.TemporaryDirectory(prefix="vo_") as td:
            work = Path(td)
            backend = tts.backend_for(voice.get("engine") or "parler")
            wav = tts.synth_text(backend, text, voice, lang, speed, work, "vo")
            data, _ = tts.read_pcm(wav)
            if len(data) < 2 * tts.SR // 20:
                raise RuntimeError("आवाज़ खाली बनी — text या voice बदलकर देखें")
            out = tts.write_wav(work / "voiceover.wav", data, tts.SR)
            item = _add_file(ws, user_id, "voice", out, name=name, tags="voiceover,tts", source="tts", license="own",
                             analyse=False)
        with db.tx() as c:
            service.log(c, ws, "voiceover.create", user_id=user_id, detail={"item_id": item["id"], "voice": voice.get("id")})
        st.update(status="done", item=_view(item), finished=time.time())
    except Exception as e:  # noqa: BLE001 — shown to the user
        log.warning("voice-over failed: %s", e)
        st.update(status="failed", error=(str(e) or e.__class__.__name__)[:300], finished=time.time())


@require("editor")
async def create(request: Request, user: dict):
    from ..engine import tts
    b = await body(request)
    text = str(b.get("text") or "").strip()
    if not text:
        raise ApiError(422, "पहले text लिखें")
    if len(text) > MAX_TEXT:
        raise ApiError(422, f"text बहुत लंबा है (max {MAX_TEXT} अक्षर)")
    vid = b.get("voice")
    voice = tts.voice_preset(vid) if vid else _default_voice()
    if not voice:
        raise ApiError(422, "voice नहीं मिली" if vid else "कोई TTS voice उपलब्ध नहीं (VoiceStudio चालू करें)")
    try:
        speed = max(0.5, min(2.0, float(b.get("speed") or 1.0)))
    except (TypeError, ValueError):
        speed = 1.0
    lang = str(b.get("lang") or voice.get("lang") or "hi")[:8]
    name = (str(b.get("name") or "").strip() or "Voice-over · " + text[:30])[:120]
    ws = user["workspace_id"]
    with _LOCK:
        for k in [k for k, j in _JOBS.items() if j.get("finished") and time.time() - j["finished"] > 3600]:
            _JOBS.pop(k, None)
        if any(j["status"] == "running" and j["ws"] == ws for j in _JOBS.values()):
            raise ApiError(429, "एक आवाज़ अभी बन रही है — ख़त्म होने दें")
        job_id = uuid.uuid4().hex[:16]
        _JOBS[job_id] = {"status": "running", "ws": ws, "started": time.time()}
    threading.Thread(target=_run, args=(job_id, ws, user["id"], text, voice, lang, speed, name), daemon=True).start()
    return ok({"job_id": job_id}, 202)


@require("viewer")
async def status(request: Request, user: dict):
    st = _JOBS.get(request.path_params["job_id"])
    if not st or st["ws"] != user["workspace_id"]:
        raise ApiError(404, "job नहीं मिला (server restart हुआ हो तो Library → Voice-over देखें)")
    return ok({"status": st["status"], "error": st.get("error"), "item": st.get("item"),
               "seconds": int((st.get("finished") or time.time()) - st["started"])})


routes = [
    Route("/voiceover", create, methods=["POST"]),
    Route("/voiceover/{job_id}", status),
]
