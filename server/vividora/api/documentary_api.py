"""Auto Documentary API — topic or script → narrated documentary MP4 in the Library.

POST /documentary/plan   {topic, minutes?, language?}  or  {script}   → {title, scenes:[{narration, visual, on_screen}]}
POST /documentary/build  {scenes:[…], title?, voice?, lang?, orientation?, music_id?, stock?, callback_url?} → 202 {job_id}
GET  /documentary/{id}   → {status, progress, message, error, item, credits, warnings}
Same under /api/v1/documentary/… for other software. Heavy work runs in a background thread; poll the job."""

from __future__ import annotations

import logging
import tempfile
import threading
import time
import urllib.request
import uuid
from pathlib import Path

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.routing import Route

from .. import db, service, storage
from .deps import ApiError, body, ok, require

log = logging.getLogger("vividora.api.documentary")
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
MAX_CHARS = 9000
MAX_STOCK_BYTES = 80 * 1024 * 1024
# commercial-safe engines first — Voice Studio (OmniVoice) is personal/non-commercial only
_SAFE_ENGINES = ("kokoro", "parler")


def _voice_for(vid: str | None, lang: str) -> tuple[dict | None, list[str]]:
    from ..engine import tts
    warn: list[str] = []
    if vid:
        v = tts.voice_preset(vid)
    else:
        voices = tts.available_voices()
        v = (next((x for x in voices if x.get("engine") in _SAFE_ENGINES and x.get("lang") == lang), None)
             or next((x for x in voices if x.get("engine") in _SAFE_ENGINES), None)
             or next((x for x in voices if x.get("engine") == "voicestudio"), None) or (voices[0] if voices else None))
    if v and v.get("engine") == "voicestudio":
        warn.append("Voice Studio (OmniVoice) की आवाज़ सिर्फ़ निजी/non-commercial इस्तेमाल के लिए है — public YouTube के लिए Kokoro/Parler voice चुनें")
    return v, warn


def _library(ws: str) -> list[dict]:
    return db.rows(db.conn().execute(
        "SELECT * FROM library WHERE workspace_id = ? AND kind IN ('image','broll') ORDER BY created_at DESC LIMIT 600", (ws,)))


def _download(url: str, dest: Path) -> Path:
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    if urlparse(url).scheme != "https" or not host.endswith("pixabay.com"):
        raise RuntimeError("stock URL अनुमत नहीं")
    req = urllib.request.Request(url, headers={"User-Agent": "Vividora/1.0"})
    n = 0
    with urllib.request.urlopen(req, timeout=40) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            n += len(chunk)
            if n > MAX_STOCK_BYTES:
                raise RuntimeError("stock clip बहुत बड़ी")
            f.write(chunk)
    return dest


def _run(job_id: str, ws: str, user_id: str, p: dict):
    import os

    from ..engine import documentary as doc
    from ..engine import tts
    from .library import _add_file, _http_json, _view
    st = _JOBS[job_id]
    scenes, voice, lang = p["scenes"], p["voice"], p["lang"]
    size = doc.SIZES[p["orientation"]]
    try:
        with tempfile.TemporaryDirectory(prefix="doc_") as td:
            work = Path(td)
            backend = tts.backend_for(voice.get("engine") or "parler")
            wavs, narr, visuals = [], [], []
            library, used, credits = _library(ws), set(), []
            key = os.getenv("PIXABAY_API_KEY") if p["stock"] else None
            n = len(scenes)
            for i, sc in enumerate(scenes):
                st.update(progress=int(5 + 55 * i / n), message=f"scene {i + 1}/{n}: आवाज़ और तस्वीर")
                w = tts.synth_text(backend, sc["narration"], voice, lang, p["speed"], work, f"s{i}")
                wavs.append(w)
                narr.append(tts.wav_seconds(w))
                m = doc.pick_visual(sc, library, used)
                src, kind = None, "image"
                if m:
                    src, kind = storage.abs_path(m["path"]), ("image" if m["kind"] == "image" else "video")
                    used.add(m["id"])
                elif key and sc.get("visual"):
                    try:
                        for c in doc.stock_candidates(sc["visual"], key, _http_json):
                            src = _download(c["url"], work / f"stock{i}.mp4")
                            kind = "video"
                            credits.append(f'scene {i + 1}: {c["creator"] or "?"} (Pixabay) {c["page"] or ""}'.strip())
                            break
                    except Exception as e:  # noqa: BLE001 — stock is a bonus; a title card is the fallback
                        log.info("stock for scene %d failed: %s", i, e)
                if not src or not Path(src).exists():
                    src, kind = doc.title_card(sc.get("on_screen") or sc["narration"][:90], work / f"card{i}.png", size, i), "image"
                visuals.append((Path(src), kind))
            durs = doc.scene_durations(narr)
            clips = []
            for i, ((src, kind), d) in enumerate(zip(visuals, durs)):
                st.update(progress=int(60 + 25 * i / n), message=f"scene {i + 1}/{n}: वीडियो बन रहा है")
                clips.append(doc.render_scene(src, kind, d, work / f"c{i}.mp4", size, i))
            st.update(progress=88, message="आवाज़, effects और music जुड़ रहे हैं")
            track = doc.narration_track(wavs, durs, work / "narration.wav")
            sfx_path = None
            row = db.conn().execute("SELECT * FROM library WHERE workspace_id = ? AND kind = 'sfx' AND lower(name) IN ('whoosh soft','whoosh','swipe') "
                                    "ORDER BY CASE lower(name) WHEN 'whoosh soft' THEN 0 WHEN 'whoosh' THEN 1 ELSE 2 END LIMIT 1", (ws,)).fetchone()
            if row:
                sfx_path = storage.abs_path(db.row(row)["path"])
            music_path = None
            if p.get("music_id"):
                mrow = db.get("library", p["music_id"])
                if mrow and mrow["workspace_id"] == ws and mrow["kind"] == "music":
                    music_path = storage.abs_path(mrow["path"])
            ass = doc.build_captions([sc["narration"] for sc in scenes], narr, durs, size, work / "captions.ass") if p.get("captions") else None
            out = doc.assemble(clips, durs, track, work / "documentary.mp4", sfx=sfx_path, music=music_path, work=work, captions=ass)
            lic = "own narration; visuals: library + " + ("; ".join(credits) if credits else "title cards")
            item = _add_file(ws, user_id, "broll", out, name=(p["title"] or "Documentary")[:100], tags="documentary,auto", source="documentary",
                             license=lic[:900], analyse=False)
        with db.tx() as c:
            service.log(c, ws, "documentary.build", user_id=user_id, detail={"item_id": item["id"], "scenes": n})
        st.update(status="done", progress=100, message="तैयार", item=_view(item), credits=credits, finished=time.time())
    except Exception as e:  # noqa: BLE001 — shown to the user
        log.warning("documentary failed: %s", e)
        st.update(status="failed", error=(str(e) or e.__class__.__name__)[:300], finished=time.time())
    from .. import webhooks
    webhooks.notify(st, job_id, "documentary")


@require("editor")
async def plan(request: Request, user: dict):
    from ..engine import documentary as doc
    b = await body(request)
    if str(b.get("script") or "").strip():
        res = doc.scenes_from_script(str(b["script"])[:MAX_CHARS])
        source = "script"
    else:
        topic = str(b.get("topic") or "").strip()
        if len(topic) < 3:
            raise ApiError(422, "topic (या अपनी script) चाहिए")
        res = await run_in_threadpool(doc.plan, topic, minutes=float(b.get("minutes") or 3), language=str(b.get("language") or "hi"))
        source = "llm"
        if res is None:
            from ..engine import llm
            if not llm.available():
                raise ApiError(409, ".env में GEMINI_API_KEY या ANTHROPIC_API_KEY डालें — या अपनी script दें ({\"script\": \"…\"})")
            raise ApiError(502, "AI से scenes नहीं बन पाए — दोबारा कोशिश करें")
    if res is None:
        raise ApiError(422, "script से scenes नहीं बने")
    return ok({**res, "source": source, "has_stock": bool(__import__("os").getenv("PIXABAY_API_KEY"))})


@require("editor")
async def build(request: Request, user: dict):
    from ..engine import documentary as doc
    b = await body(request)
    res = doc.normalize({"title": b.get("title"), "scenes": b.get("scenes")})
    if not res:
        raise ApiError(422, "scenes चाहिए (हर scene में narration)")
    if len(res["scenes"]) > 24:
        raise ApiError(422, "एक बार में अधिकतम 24 scenes")
    if sum(len(s["narration"]) for s in res["scenes"]) > MAX_CHARS:
        raise ApiError(422, f"narration बहुत लंबी (max {MAX_CHARS} अक्षर)")
    lang = str(b.get("lang") or "hi")[:8]
    voice, warn = _voice_for(b.get("voice"), lang)
    if not voice:
        raise ApiError(422, "कोई TTS voice उपलब्ध नहीं" if not b.get("voice") else "voice नहीं मिली")
    orient = str(b.get("orientation") or "landscape")
    if orient not in doc.SIZES:
        raise ApiError(422, "orientation: landscape | portrait | square")
    try:
        speed = max(0.7, min(1.4, float(b.get("speed") or 1.0)))
    except (TypeError, ValueError):
        speed = 1.0
    cb = None
    if b.get("callback_url"):
        from .. import webhooks
        try:
            cb = webhooks.check_url(str(b["callback_url"]))
        except ValueError as e:
            raise ApiError(422, str(e))
    ws = user["workspace_id"]
    with _LOCK:
        for k in [k for k, j in _JOBS.items() if j.get("finished") and time.time() - j["finished"] > 3600]:
            _JOBS.pop(k, None)
        if any(j["status"] == "running" and j["ws"] == ws for j in _JOBS.values()):
            raise ApiError(429, "एक documentary अभी बन रही है — ख़त्म होने दें")
        job_id = uuid.uuid4().hex[:16]
        _JOBS[job_id] = {"status": "running", "ws": ws, "started": time.time(), "callback": cb, "progress": 1, "message": "शुरू", "warnings": warn}
    p = {"scenes": res["scenes"], "title": res["title"], "voice": voice, "lang": lang, "orientation": orient, "speed": speed,
         "music_id": b.get("music_id"), "stock": b.get("stock", True) is not False, "captions": b.get("captions", True) is not False}
    threading.Thread(target=_run, args=(job_id, ws, user["id"], p), daemon=True).start()
    return ok({"job_id": job_id, "warnings": warn}, 202)


@require("viewer")
async def status(request: Request, user: dict):
    st = _JOBS.get(request.path_params["job_id"])
    if not st or st["ws"] != user["workspace_id"]:
        raise ApiError(404, "job नहीं मिला (server restart हुआ हो तो Library देखें)")
    return ok({"status": st["status"], "progress": st.get("progress"), "message": st.get("message"), "error": st.get("error"),
               "item": st.get("item"), "credits": st.get("credits"), "warnings": st.get("warnings"),
               "seconds": int((st.get("finished") or time.time()) - st["started"])})


routes = [
    Route("/documentary/plan", plan, methods=["POST"]),
    Route("/documentary/build", build, methods=["POST"]),
    Route("/documentary/{job_id}", status),
]
