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

    from ..engine import aiimage, aivideo
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
                elif p.get("ai_images") and aiimage.provider() and (sc.get("visual") or sc.get("narration")):
                    try:
                        src, prov = aiimage.generate(aiimage.prompt_for(sc.get("visual"), sc["narration"]), work / f"ai{i}", size)
                        kind = "image"
                        credits.append(f"scene {i + 1}: AI-generated image ({prov}) — synthetic")
                    except Exception as e:  # noqa: BLE001 — falls through to stock / title card
                        log.info("ai image for scene %d failed: %s", i, e)
                        src = None
                if not src and key and sc.get("visual"):
                    try:
                        for c in doc.stock_candidates(sc["visual"], key, _http_json):
                            is_img = c["kind"] == "image"
                            src = _download(c["url"], work / (f"stock{i}.jpg" if is_img else f"stock{i}.mp4"))
                            kind = "image" if is_img else "video"
                            credits.append(f'scene {i + 1}: {c["creator"] or "?"} (Pixabay) {c["page"] or ""}'.strip())
                            break
                    except Exception as e:  # noqa: BLE001 — stock is a bonus; a title card is the fallback
                        log.info("stock for scene %d failed: %s", i, e)
                if (sc.get("motion") and p.get("ai_video") and aivideo.provider() and src and kind == "image" and Path(src).exists()
                        and sum(1 for c in credits if "AI video" in c) < aivideo.max_clips()):
                    try:
                        st.update(message=f"scene {i + 1}/{n}: AI video बन रही है (1–3 मिनट)")
                        src = aivideo.animate(Path(src), sc.get("visual") or sc["narration"][:120], work / f"mo{i}.mp4")
                        kind = "video"
                        credits.append(f"scene {i + 1}: AI video ({aivideo.provider()}) — synthetic")
                    except Exception as e:  # noqa: BLE001 — the still picture (Ken-Burns) is the fallback
                        log.info("ai video for scene %d failed: %s", i, e)
                        st["warnings"].append(f"scene {i + 1}: AI video नहीं बनी — तस्वीर इस्तेमाल हुई")
                if not src or not Path(src).exists():
                    src, kind = doc.title_card(sc.get("on_screen") or sc["narration"][:90], work / f"card{i}.png", size, i), "image"
                visuals.append((Path(src), kind))
            durs = doc.scene_durations(narr, [sc.get("hold", 0) for sc in scenes])
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
            music_path, mrow = None, None
            if p.get("music_id") == "auto":   # pick from the library by the script's mood — safe licences only
                lib = db.rows(db.conn().execute("SELECT * FROM library WHERE workspace_id = ? AND kind = 'music' LIMIT 400", (ws,)))
                mood = p.get("music_mood") or doc.detect_mood(p.get("title") or "", scenes)
                pick = doc.pick_music(lib, mood, seed=p.get("title") or mood)
                if pick:
                    music_path = storage.abs_path(pick["path"])
                    st.update(message=f"music: {pick['name']} ({mood})")
                    mrow = pick
            elif p.get("music_id"):
                mrow = db.get("library", p["music_id"])
                if mrow and mrow["workspace_id"] == ws and mrow["kind"] == "music":
                    music_path = storage.abs_path(mrow["path"])
            if music_path and (mrow.get("source") or "") not in ("starter", "upload"):   # CC music needs its credit in the description
                credits.append(f"Music: {mrow.get('license') or mrow['name']}"[:300])
                if doc.music_is_nc(mrow):
                    st.setdefault("warnings", []).append("⚠ यह music NON-COMMERCIAL licence का है — monetised channel पर upload न करें")
            ass = doc.build_captions([sc["narration"] for sc in scenes], narr, durs, size, work / "captions.ass") if p.get("captions") else None
            out = doc.assemble(clips, durs, track, work / "documentary.mp4", sfx=sfx_path, music=music_path, work=work, captions=ass, music_volume=p.get("music_volume", 0.14))
            chaps = doc.chapters(scenes, durs)
            desc = doc.description(p["title"] or "Documentary", chaps, credits, p.get("sources"), p.get("series"))
            lic = "own narration; visuals: library + " + ("; ".join(credits) if credits else "title cards")
            item = _add_file(ws, user_id, "broll", out, name=(p["title"] or "Documentary")[:100], tags="documentary,auto", source="documentary",
                             license=lic[:900], analyse=False)
            thumb = None
            try:
                tp = doc.make_thumbnail(out, p["title"] or "Documentary", work / "thumbnail.png", at=min(2.0, sum(durs) / 3))
                thumb = _view(_add_file(ws, user_id, "image", tp, name=((p["title"] or "Documentary") + " · thumbnail")[:100], tags="documentary,thumbnail",
                                        source="documentary", license="own", analyse=False))
            except Exception as e:  # noqa: BLE001 — the film is the product; the thumbnail is a bonus
                log.info("thumbnail failed: %s", e)
        with db.tx() as c:
            service.log(c, ws, "documentary.build", user_id=user_id, detail={"item_id": item["id"], "scenes": n})
        st.update(status="done", progress=100, message="तैयार", item=_view(item), credits=credits, description=desc, thumbnail=thumb, ai_used=any("AI-generated" in c for c in credits), finished=time.time())
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
        res = await run_in_threadpool(lambda: doc.plan(topic, minutes=float(b.get("minutes") or 3), language=str(b.get("language") or "hi"),
                                                       ground=b.get("ground", True) is not False))
        source = "llm"
        if res is None:
            from ..engine import llm
            if not llm.available():
                raise ApiError(409, ".env में GEMINI_API_KEY या ANTHROPIC_API_KEY डालें — या अपनी script दें ({\"script\": \"…\"})")
            raise ApiError(502, "AI से scenes नहीं बन पाए — दोबारा कोशिश करें")
    if res is None:
        raise ApiError(422, "script से scenes नहीं बने")
    return ok({**res, "source": source, "has_stock": bool(__import__("os").getenv("PIXABAY_API_KEY")),
                "ai_provider": __import__("vividora.engine.aiimage", fromlist=["x"]).provider(),
                "video_provider": __import__("vividora.engine.aivideo", fromlist=["x"]).provider()})


def _params(b: dict, user: dict) -> tuple[dict, list[str]]:
    """Validate a build request → (job params, warnings). Raises ApiError."""
    from ..engine import documentary as doc
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
    try:
        mv = max(0.02, min(0.6, float(b.get("music_volume") if b.get("music_volume") is not None else 0.14)))
    except (TypeError, ValueError):
        mv = 0.14
    ser = b.get("series") if isinstance(b.get("series"), dict) else None
    p = {"scenes": res["scenes"], "title": res["title"], "voice": voice, "lang": lang, "orientation": orient, "speed": speed,
         "music_id": b.get("music_id"), "music_mood": (str(b.get("music_mood") or "")[:20] or None), "music_volume": mv, "stock": b.get("stock", True) is not False,
         "captions": b.get("captions", True) is not False, "ai_images": b.get("ai_images", True) is not False, "ai_video": b.get("ai_video", True) is not False,
         "series": ({"name": str(ser.get("name", ""))[:100], "i": int(ser.get("i") or 1), "titles": [str(t)[:100] for t in (ser.get("titles") or [])[:12]]} if ser else None),
         "sources": [{"title": str(x.get("title", ""))[:120], "url": str(x.get("url", ""))[:300]} for x in (b.get("sources") or [])[:6] if isinstance(x, dict)]}
    return p, warn


def _callback(b: dict):
    if not b.get("callback_url"):
        return None
    from .. import webhooks
    try:
        return webhooks.check_url(str(b["callback_url"]))
    except ValueError as e:
        raise ApiError(422, str(e))


def _reserve(ws: str, extra: dict) -> str:
    with _LOCK:
        for k in [k for k, j in _JOBS.items() if j.get("finished") and time.time() - j["finished"] > 3600]:
            _JOBS.pop(k, None)
        if any(j["status"] == "running" and j["ws"] == ws and not j.get("child") for j in _JOBS.values()):
            raise ApiError(429, "एक documentary अभी बन रही है — ख़त्म होने दें")
        job_id = uuid.uuid4().hex[:16]
        _JOBS[job_id] = {"status": "running", "ws": ws, "started": time.time(), "progress": 1, "message": "शुरू", **extra}
    return job_id


@require("editor")
async def build(request: Request, user: dict):
    b = await body(request)
    p, warn = _params(b, user)
    cb = _callback(b)
    job_id = _reserve(user["workspace_id"], {"callback": cb, "warnings": warn})
    threading.Thread(target=_run, args=(job_id, user["workspace_id"], user["id"], p), daemon=True).start()
    return ok({"job_id": job_id, "warnings": warn}, 202)


MAX_BATCH = 12


def _batch_run(batch_id: str, ws: str, user_id: str, items: list[dict], common: dict, user: dict):
    """Build items one after another (each = one documentary job). An item is either ready scenes or {topic} to plan first."""
    from ..engine import documentary as doc
    st = _JOBS[batch_id]
    n = len(items)
    for k, it in enumerate(items):
        row = st["items"][k]
        try:
            row["status"] = "running"
            st.update(progress=int(100 * k / n), message=f"{k + 1}/{n}: {it.get('title') or it.get('topic') or ''}"[:120])
            if not it.get("scenes"):
                st.update(message=f"{k + 1}/{n}: scenes लिखे जा रहे हैं")
                res = doc.plan(it["topic"], minutes=float(it.get("minutes") or common.get("minutes") or 3), language=str(common.get("language") or "hi"),
                               ground=common.get("ground", True) is not False)
                if not res:
                    raise RuntimeError("AI से scenes नहीं बन पाए")
                it = {**it, "scenes": res["scenes"], "sources": res.get("sources"), "title": it.get("title") or res["title"]}
                row["title"] = it["title"]
            p, _ = _params({**common, **it}, user)
            cid = uuid.uuid4().hex[:16]
            with _LOCK:
                _JOBS[cid] = {"status": "running", "ws": ws, "started": time.time(), "progress": 1, "message": "शुरू", "child": True, "warnings": []}
            _run(cid, ws, user_id, p)
            ch = _JOBS[cid]
            row.update(status=ch["status"], error=ch.get("error"), item=ch.get("item"), thumbnail=ch.get("thumbnail"), description=ch.get("description"),
                       ai_used=ch.get("ai_used"), job_id=cid, scenes=len(p["scenes"]))
        except Exception as e:  # noqa: BLE001 — one failed item must not stop the rest
            log.warning("batch item %d failed: %s", k, e)
            row.update(status="failed", error=(str(e) or e.__class__.__name__)[:300])
    done = sum(1 for r in st["items"] if r["status"] == "done")
    st.update(status="done" if done else "failed", progress=100, message=f"{done}/{n} तैयार", finished=time.time(),
              error=None if done else "कोई भी नहीं बन पाई")


def _start_batch(user: dict, items: list[dict], common: dict, label: str) -> str:
    ws = user["workspace_id"]
    rows = [{"title": str(it.get("title") or it.get("topic") or f"#{k + 1}")[:120], "status": "waiting"} for k, it in enumerate(items)]
    bid = _reserve(ws, {"batch": True, "label": label, "items": rows, "warnings": []})
    threading.Thread(target=_batch_run, args=(bid, ws, user["id"], items, common, user), daemon=True).start()
    return bid


_COMMON_KEYS = ("voice", "lang", "language", "speed", "orientation", "music_id", "music_mood", "music_volume", "stock", "captions", "ai_images", "ai_video", "minutes", "ground")


def _common(b: dict) -> dict:
    return {k: b[k] for k in _COMMON_KEYS if k in b}


@require("editor")
async def shorts(request: Request, user: dict):
    """Pick the best 20–58 s runs of scenes for Shorts/Reels. build=true renders them (portrait) one after another."""
    from ..engine import documentary as doc
    b = await body(request)
    res = doc.normalize({"title": b.get("title"), "scenes": b.get("scenes")})
    if not res:
        raise ApiError(422, "scenes चाहिए")
    plan_ = doc.shorts_plan(res["scenes"], count=int(b.get("count") or 3))
    if not plan_:
        raise ApiError(422, "इन scenes से 20 सेकंड का Short नहीं बनता — और scenes जोड़ें")
    if not b.get("build"):
        return ok({"shorts": plan_})
    chosen = b.get("pick")
    if isinstance(chosen, list):
        plan_ = [plan_[i] for i in chosen if isinstance(i, int) and 0 <= i < len(plan_)] or plan_
    items = [{"title": (c["title"] + " #Shorts")[:100], "scenes": [res["scenes"][i] for i in c["indices"]]} for c in plan_]
    common = {**_common(b), "orientation": "portrait"}
    _params({**common, **items[0]}, user)  # fail fast on a bad voice etc.
    return ok({"job_id": _start_batch(user, items, common, "shorts"), "shorts": plan_}, 202)


@require("editor")
async def series(request: Request, user: dict):
    """Series: without build → episode outline (LLM). With build + episodes → plan and render every episode in order."""
    from ..engine import documentary as doc
    from ..engine import llm
    b = await body(request)
    if not b.get("build"):
        topic = str(b.get("topic") or "").strip()
        if len(topic) < 3:
            raise ApiError(422, "series का topic चाहिए")
        if not llm.available():
            raise ApiError(409, ".env में GEMINI_API_KEY (या ANTHROPIC_API_KEY / Ollama) डालें — series के episodes AI से बनते हैं")
        res = await run_in_threadpool(lambda: doc.series_plan(topic, int(b.get("episodes") or 4), str(b.get("language") or "hi")))
        if not res:
            raise ApiError(502, "AI से episodes नहीं बन पाए — दोबारा कोशिश करें")
        return ok(res)
    eps = [e for e in (b.get("episodes") or []) if isinstance(e, dict) and str(e.get("title") or "").strip()][:10]
    name = str(b.get("series") or b.get("topic") or "Series")[:100]
    if len(eps) < 2:
        raise ApiError(422, "कम से कम 2 episodes चाहिए")
    if not llm.available():
        raise ApiError(409, "AI key चाहिए — हर episode की scenes AI लिखता है")
    titles = [e["title"] for e in eps]
    items = [{"topic": f"{name} — Episode {k + 1}: {e['title']}. {e.get('summary', '')} (Other episodes in this series: {'; '.join(t for t in titles if t != e['title'])}. "
                       f"Do NOT repeat their content.)",
              "title": f"{name} — Ep {k + 1}: {e['title']}"[:100], "series": {"name": name, "i": k + 1, "titles": titles}} for k, e in enumerate(eps)]
    common = _common(b)
    _params({**common, "scenes": [{"narration": "test narration"}]}, user)
    return ok({"job_id": _start_batch(user, items, common, "series")}, 202)


@require("viewer")
async def drafts_list(request: Request, user: dict):
    cur = db.conn().execute("SELECT id, name, updated_at, meta FROM doc_drafts WHERE workspace_id = ? ORDER BY updated_at DESC LIMIT 100", (user["workspace_id"],))
    out = []
    for x in db.rows(cur):
        m = x.get("meta") or {}
        out.append({"id": x["id"], "name": x["name"], "updated_at": x["updated_at"], "scenes": len(m.get("scenes") or [])})
    return ok({"drafts": out})


@require("editor")
async def draft_save(request: Request, user: dict):
    """Save the editor state (title, scenes with hold/library_id, voice/music/… options) so you can come back later."""
    import json

    from ..engine import documentary as doc
    b = await body(request)
    res = doc.normalize({"title": b.get("title"), "scenes": b.get("scenes")})
    if not res:
        raise ApiError(422, "सेव करने के लिए scenes चाहिए")
    opts = {k: b[k] for k in ("voice", "lang", "speed", "orientation", "music_id", "music_volume", "stock", "captions", "ai_images", "sources") if k in b}
    meta = {"title": res["title"], "scenes": res["scenes"], "options": opts}
    if len(json.dumps(meta, ensure_ascii=False)) > 200_000:
        raise ApiError(413, "draft बहुत बड़ा")
    name = str(b.get("name") or res["title"])[:100]
    ws, did = user["workspace_id"], str(b.get("id") or "")
    with db.tx() as c:
        cur = db.get("doc_drafts", did) if did else None
        if cur and cur["workspace_id"] == ws:
            db.update(c, "doc_drafts", did, {"name": name, "meta": meta, "updated_at": db.now()})
        else:
            did = db.new_id()
            db.insert(c, "doc_drafts", {"id": did, "workspace_id": ws, "name": name, "meta": meta, "created_by": user["id"], "created_at": db.now(), "updated_at": db.now()})
    return ok({"id": did, "name": name})


@require("viewer")
async def draft_get(request: Request, user: dict):
    d = db.get("doc_drafts", request.path_params["draft_id"])
    if not d or d["workspace_id"] != user["workspace_id"]:
        raise ApiError(404, "draft नहीं मिला")
    return ok({"id": d["id"], "name": d["name"], **d["meta"]})


@require("editor")
async def draft_delete(request: Request, user: dict):
    d = db.get("doc_drafts", request.path_params["draft_id"])
    if not d or d["workspace_id"] != user["workspace_id"]:
        raise ApiError(404, "draft नहीं मिला")
    with db.tx() as c:
        c.execute("DELETE FROM doc_drafts WHERE id = ?", (d["id"],))
    return ok({"deleted": True})


def _upload_run(uid: str, ws: str, conn_id: str, path: Path, thumb: Path | None, meta: dict):
    from ..config import settings
    from ..publish import youtube
    st = _JOBS[uid]
    try:
        if settings.publish_dry_run:
            st.update(status="done", progress=100, message="dry-run: upload नहीं हुआ", url="(dry-run)", finished=time.time())
            return
        conn = db.get("connections", conn_id)
        token, sec = youtube.access_token(conn["secrets"])
        if sec != conn["secrets"]:
            with db.tx() as c:
                db.update(c, "connections", conn_id, {"secrets": sec, "updated_at": db.now()})
        st.update(progress=5, message="YouTube पर upload हो रहा है…")
        res = youtube.upload_video(token, path, title=meta["title"], description=meta["description"], tags=meta["tags"], privacy=meta["privacy"],
                                   category="27" if meta.get("education") else "22", language=meta.get("language"), synthetic=meta["synthetic"],
                                   on_progress=lambda f: st.update(progress=int(5 + 90 * max(0.0, min(1.0, float(f or 0))))))
        if thumb:
            try:
                youtube.set_thumbnail(token, res["remote_id"], thumb)
            except Exception as e:  # noqa: BLE001 — channel may not be verified for custom thumbnails
                st["warnings"].append(f"thumbnail नहीं लगा: {str(e)[:120]}")
        st.update(status="done", progress=100, message="private draft तैयार", url=res["url"], remote_id=res["remote_id"], finished=time.time())
    except Exception as e:  # noqa: BLE001 — shown to the user
        log.warning("youtube upload failed: %s", e)
        st.update(status="failed", error=(str(e) or e.__class__.__name__)[:300], finished=time.time())


@require("editor")
async def youtube_upload(request: Request, user: dict):
    """Upload a finished documentary (Library item) to YOUR connected YouTube channel as a PRIVATE video (never public)
    with the title/description/thumbnail from the build and the "synthetic content" flag when AI pictures were used.
    You review and publish it in YouTube Studio yourself."""
    from PIL import Image
    b = await body(request)
    ws = user["workspace_id"]
    item = db.get("library", str(b.get("library_id") or ""))
    if not item or item["workspace_id"] != ws or item["kind"] not in ("broll", "video"):
        raise ApiError(404, "वीडियो Library में नहीं मिला")
    conn = db.get("connections", str(b.get("connection_id") or ""))
    if not conn or conn["workspace_id"] != ws or conn["platform"] != "youtube":
        raise ApiError(404, "YouTube channel connect नहीं है — Dashboard → Connections")
    title = str(b.get("title") or item["name"]).strip()[:100]
    if not title:
        raise ApiError(422, "title चाहिए")
    privacy = "unlisted" if b.get("privacy") == "unlisted" else "private"
    thumb = None
    if b.get("thumbnail_id"):
        t = db.get("library", str(b["thumbnail_id"]))
        if t and t["workspace_id"] == ws and t["kind"] == "image":
            tmpd = Path(tempfile.mkdtemp(prefix="docyt_"))
            thumb = tmpd / "thumb.jpg"
            Image.open(storage.abs_path(t["path"])).convert("RGB").save(thumb, quality=90)
    meta = {"title": title, "description": str(b.get("description") or "")[:5000], "privacy": privacy,
            "tags": [str(t)[:40] for t in (b.get("tags") or [])][:30], "synthetic": bool(b.get("synthetic")),
            "language": b.get("language") if b.get("language") in ("hi", "en") else None, "education": True}
    uid = _reserve_upload(ws)
    threading.Thread(target=_upload_run, args=(uid, ws, conn["id"], storage.abs_path(item["path"]), thumb, meta), daemon=True).start()
    return ok({"job_id": uid, "privacy": privacy}, 202)


def _reserve_upload(ws: str) -> str:
    with _LOCK:
        if any(j["status"] == "running" and j["ws"] == ws and j.get("upload") for j in _JOBS.values()):
            raise ApiError(429, "एक upload अभी चल रहा है")
        uid = uuid.uuid4().hex[:16]
        _JOBS[uid] = {"status": "running", "ws": ws, "started": time.time(), "progress": 1, "message": "शुरू", "upload": True, "warnings": [], "child": True}
    return uid


def _ig_run(uid: str, conn_id: str, item_id: str, caption: str):
    from ..config import settings
    from ..publish import meta
    from ..security import make_token
    st = _JOBS[uid]
    try:
        if settings.publish_dry_run:
            st.update(status="done", progress=100, message="dry-run: Instagram पर कुछ नहीं गया", url="(dry-run)", finished=time.time())
            return
        conn = db.get("connections", conn_id)
        sec = conn["secrets"]
        url = f"{settings.public_url.rstrip('/')}/publib/{make_token(item_id, kind='publib', hours=48)}"
        st.update(progress=10, message="Instagram वीडियो उठा रहा है और process कर रहा है (कुछ मिनट)…")
        res = meta.ig_publish_reel(sec["ig_id"], sec["page_token"], url, caption, on_progress=lambda f: st.update(progress=int(10 + 85 * max(0.0, min(1.0, float(f or 0))))))
        st.update(status="done", progress=100, message="Instagram पर live हो गया", url=res["url"], remote_id=res["remote_id"], finished=time.time())
    except Exception as e:  # noqa: BLE001 — shown to the user
        log.warning("instagram publish failed: %s", e)
        st.update(status="failed", error=(str(e) or e.__class__.__name__)[:300], finished=time.time())


def _ig_conn(user: dict, cid) -> dict:
    conn = db.get("connections", str(cid or ""))
    if not conn or conn["workspace_id"] != user["workspace_id"] or conn["platform"] != "instagram" or not (conn["secrets"] or {}).get("ig_id"):
        raise ApiError(404, "Instagram account connect नहीं है — Dashboard → Connections (Meta)")
    return conn


@require("editor")
async def instagram_publish(request: Request, user: dict):
    """Post a finished documentary / Short (Library video) as an Instagram Reel on YOUR connected account.
    Instagram has no private-draft mode: this goes LIVE immediately, so the request must carry confirm:true."""
    from ..config import settings
    b = await body(request)
    if b.get("confirm") is not True:
        raise ApiError(422, "Instagram पर यह तुरंत live होगा — confirm:true भेजें (UI में टिक करें)")
    if not settings.public_url and not settings.publish_dry_run:
        raise ApiError(409, "PUBLIC_URL सेट नहीं है — Instagram को वीडियो का public link चाहिए (.env में PUBLIC_URL=https://studio…)")
    item = db.get("library", str(b.get("library_id") or ""))
    if not item or item["workspace_id"] != user["workspace_id"] or item["kind"] not in ("broll", "video"):
        raise ApiError(404, "वीडियो Library में नहीं मिला")
    conn = _ig_conn(user, b.get("connection_id"))
    caption = str(b.get("caption") or item["name"]).strip()[:2200]
    if not caption:
        raise ApiError(422, "caption चाहिए")
    m = item.get("meta") or {}
    warn = []
    if m.get("width") and m.get("height") and m["width"] >= m["height"]:
        warn.append("यह वीडियो landscape है — Reels के लिए 9:16 (Portrait/Shorts) सबसे अच्छा रहता है")
    uid = _reserve_upload(user["workspace_id"])
    _JOBS[uid]["warnings"] = warn
    threading.Thread(target=_ig_run, args=(uid, conn["id"], item["id"], caption), daemon=True).start()
    return ok({"job_id": uid, "warnings": warn}, 202)


@require("viewer")
async def instagram_insights(request: Request, user: dict):
    """Latest reels of the connected Instagram account with views / reach / saves / shares / avg watch time + simple takeaways."""
    from ..engine import analytics
    cid = request.query_params.get("connection_id")
    conn = _ig_conn(user, cid)
    sec = conn["secrets"]
    try:
        rows = await run_in_threadpool(lambda: analytics.ig_recent(sec["ig_id"], sec["page_token"], 12))
    except Exception as e:  # noqa: BLE001
        raise ApiError(502, f"Instagram से data नहीं आया: {str(e)[:200]}")
    reels = [r for r in rows if r.get("views") or r.get("reach")]
    tips = []
    if reels:
        best = max(reels, key=lambda r: r["views"] or 0)
        tips.append(f"सबसे ज़्यादा views: «{best['caption'][:50] or best['id']}» ({best['views']})")
        sv = [r for r in reels if r["save_rate"] is not None]
        if sv:
            bs = max(sv, key=lambda r: r["save_rate"])
            tips.append(f"सबसे ज़्यादा saves/reach: «{bs['caption'][:50] or bs['id']}» ({bs['save_rate'] * 100:.1f}%) — ऐसे ही content और बनाएँ")
        w = [r["avg_watch_s"] for r in reels if r["avg_watch_s"]]
        if w:
            tips.append(f"औसत watch time {sum(w) / len(w):.1f} सेकंड — शुरुआती 3 सेकंड में hook रखें")
    return ok({"reels": rows, "tips": tips})


@require("editor")
async def preview(request: Request, user: dict):
    """Which Library picture each scene would get (no rendering): [{index, library_id, name}|null]."""
    from ..engine import documentary as doc
    b = await body(request)
    res = doc.normalize({"scenes": b.get("scenes")})
    if not res:
        raise ApiError(422, "scenes चाहिए")
    lib, used, out = _library(user["workspace_id"]), set(), []
    for i, sc in enumerate(res["scenes"]):
        m = doc.pick_visual(sc, lib, used)
        if m:
            used.add(m["id"])
        out.append({"index": i, "library_id": m["id"] if m else None, "name": m["name"] if m else None})
    from ..engine import aivideo
    n_motion = min(sum(1 for sc in res["scenes"] if sc.get("motion")), aivideo.max_clips()) if aivideo.provider() else 0
    return ok({"matches": out, "video_clips": n_motion, "video_estimate_usd": aivideo.estimate_usd(n_motion),
               "has_stock": bool(__import__("os").getenv("PIXABAY_API_KEY")),
                "ai_provider": __import__("vividora.engine.aiimage", fromlist=["x"]).provider(),
                "video_provider": __import__("vividora.engine.aivideo", fromlist=["x"]).provider()})


@require("viewer")
async def status(request: Request, user: dict):
    st = _JOBS.get(request.path_params["job_id"])
    if not st or st["ws"] != user["workspace_id"]:
        raise ApiError(404, "job नहीं मिला (server restart हुआ हो तो Library देखें)")
    return ok({"status": st["status"], "progress": st.get("progress"), "message": st.get("message"), "error": st.get("error"),
               "item": st.get("item"), "credits": st.get("credits"), "description": st.get("description"), "thumbnail": st.get("thumbnail"), "warnings": st.get("warnings"), "ai_used": st.get("ai_used"), "items": st.get("items"), "url": st.get("url"),
               "seconds": int((st.get("finished") or time.time()) - st["started"])})


routes = [
    Route("/documentary/plan", plan, methods=["POST"]),
    Route("/documentary/build", build, methods=["POST"]),
    Route("/documentary/preview", preview, methods=["POST"]),
    Route("/documentary/shorts", shorts, methods=["POST"]),
    Route("/documentary/series", series, methods=["POST"]),
    Route("/documentary/youtube", youtube_upload, methods=["POST"]),
    Route("/documentary/instagram", instagram_publish, methods=["POST"]),
    Route("/documentary/instagram/insights", instagram_insights),
    Route("/documentary/drafts", drafts_list),
    Route("/documentary/drafts", draft_save, methods=["POST"]),
    Route("/documentary/drafts/{draft_id}", draft_get),
    Route("/documentary/drafts/{draft_id}", draft_delete, methods=["DELETE"]),
    Route("/documentary/{job_id}", status),
]
