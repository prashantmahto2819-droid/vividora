"""Visuals from the voice (Smart B-roll) for the editor.

POST /api/projects/{id}/visuals/plan   {max_items?}                → {items: [...], providers: {...}}
    Which spoken lines deserve a picture + a stock query, an AI-image prompt and an AI-video prompt for each
    (engine/visualplan.py). Nothing is fetched; the user edits the prompts and chooses a source per line.
POST /api/projects/{id}/visuals/fetch  {source, query?, prompt?, video_prompt?, text?, vertical?}  → {job}
    source: library | stock_video | stock_photo | ai_image | ai_video. Runs in the background (AI video takes minutes).
GET  /api/visuals/jobs/{job}                                       → {status: running|done|error, item?, error?, message}
    `item` is the library item to put on the timeline (stock / AI results are saved to the library with their credit).
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from pathlib import Path

from starlette.requests import Request
from starlette.routing import Route

from .. import db, storage
from .deps import ApiError, body, ok, own_project, rate_limit, require

log = logging.getLogger("vividora.visuals")
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
SOURCES = ("library", "stock_video", "stock_photo", "ai_image", "ai_video")
MAX_RUNNING = 3                 # per workspace, so one click on "apply all" cannot fire 20 paid generations at once


def providers() -> dict:
    from ..engine import aiimage, aivideo, llm
    return {"stock": bool(os.getenv("PIXABAY_API_KEY")), "ai_image": aiimage.provider(), "ai_video": aivideo.provider(),
            "ai_video_usd": aivideo.estimate_usd(1), "ai_video_max": aivideo.max_clips(), "llm": llm.available()}


@require("editor")
async def plan(request: Request, user: dict):
    from starlette.concurrency import run_in_threadpool

    from ..engine import visualplan
    p = own_project(request, user)
    d = await body(request)
    rate_limit(request, "visuals_plan", 10)
    segs = ((p.get("transcript") or {}).get("segments")) or []
    if not segs:
        raise ApiError(409, "इस वीडियो का transcript नहीं है — पहले Captions tab से transcript बनाएँ")
    edl = p.get("edl") or {}
    dur = float((p.get("meta") or {}).get("duration") or edl.get("duration") or 0) or None
    ch = db.get("channels", p["channel_id"]) if p.get("channel_id") else None
    niche = str(((ch or {}).get("settings") or {}).get("niche") or "")[:80]
    n = max(1, min(20, int(d.get("max_items") or 8)))
    items = await run_in_threadpool(lambda: visualplan.plan(segs, niche=niche, max_items=n, cuts=edl.get("cuts") or [], duration=dur))
    return ok({"items": items, "providers": providers(), "effects": visualplan.EFFECTS, "layouts": visualplan.LAYOUTS})


def _fetch(job_id: str, ws: str, user_id: str, d: dict) -> None:
    from ..engine import aiimage, aivideo
    from ..engine import documentary as doc
    from .documentary_api import _download
    from .library import _add_file, _http_json, _view
    st = _JOBS[job_id]
    src_kind, query, text = d["source"], d.get("query") or "", d.get("text") or ""
    prompt = d.get("prompt") or query or text
    vertical = bool(d.get("vertical"))
    try:
        if src_kind == "library":
            lib = db.rows(db.conn().execute("SELECT * FROM library WHERE workspace_id = ? AND kind IN ('image','broll')", (ws,)))
            lib = [m for m in lib if (m.get("source") or "") != "starter"]          # starter "broll" are abstract backgrounds
            m = doc.pick_visual({"visual": f"{query} {text}"}, lib, set())
            if not m:
                raise RuntimeError("Library में इस line से मिलता कोई clip / photo नहीं — stock या AI चुनें, या clip के नाम/tags में ये शब्द डालें")
            st.update(status="done", item=_view(m), message="Library से मिला")
            return
        with tempfile.TemporaryDirectory(prefix="vis_") as td:
            work = Path(td)
            name = (query or text or "visual")[:60]
            if src_kind in ("stock_video", "stock_photo"):
                key = os.getenv("PIXABAY_API_KEY")
                if not key:
                    raise RuntimeError("API & Keys page (या .env) में PIXABAY_API_KEY नहीं है")
                if not query:
                    raise RuntimeError("stock खोज के लिए शब्द (English) लिखें")
                want = "video" if src_kind == "stock_video" else "photo"
                cands = doc.stock_candidates(query, key, _http_json, want=want, orientation="vertical" if vertical else "horizontal")
                if not cands:
                    raise RuntimeError(f"“{query}” के लिए stock {'video' if want == 'video' else 'photo'} नहीं मिला — शब्द बदलकर देखें (English में)")
                c = cands[0]
                is_img = c["kind"] == "image"
                f = _download(c["url"], work / ("stock.jpg" if is_img else "stock.mp4"))
                row = _add_file(ws, user_id, "image" if is_img else "broll", f, name=name, tags=f"stock,visuals,{query}"[:200], source="pixabay",
                                license=f'Pixabay Content License — {c.get("creator") or "?"} {c.get("page") or ""}'.strip(), move=True)
            else:
                if not aiimage.provider():
                    raise RuntimeError("AI image provider set नहीं है (.env: CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN या HF_TOKEN)")
                st.update(message="AI तस्वीर बन रही है…")
                img, prov = aiimage.generate(aiimage.prompt_for(prompt, text), work / "ai", (720, 1280) if vertical else (1280, 720))
                if src_kind == "ai_image":
                    row = _add_file(ws, user_id, "image", img, name=name, tags="ai,visuals", source="ai",
                                    license=f"AI-generated image ({prov}) — synthetic", move=True)
                else:
                    if not aivideo.provider():
                        raise RuntimeError("AI video provider set नहीं है (API & Keys page में FAL_KEY)")
                    st.update(message="AI video बन रही है (1–3 मिनट)…")
                    vid = aivideo.animate(img, d.get("video_prompt") or prompt[:160], work / "ai.mp4")
                    row = _add_file(ws, user_id, "broll", vid, name=name, tags="ai,visuals,ai-video", source="ai",
                                    license=f"AI video ({aivideo.provider()}) from an AI image ({prov}) — synthetic", move=True)
            st.update(status="done", item=_view(row), message="तैयार")
    except Exception as e:  # noqa: BLE001 — the job reports it; the editor shows the reason next to the line
        log.info("visual fetch (%s) failed: %s", src_kind, e)
        st.update(status="error", error=str(e)[:300], message="नहीं हो पाया")
    finally:
        st["ended"] = time.time()


@require("editor")
async def fetch(request: Request, user: dict):
    own_project(request, user)
    d = await body(request)
    rate_limit(request, "visuals_fetch", 40)
    if d.get("source") not in SOURCES:
        raise ApiError(422, "source: " + " | ".join(SOURCES))
    clean = {"source": d["source"], "query": str(d.get("query") or "")[:100], "prompt": str(d.get("prompt") or "")[:500],
             "video_prompt": str(d.get("video_prompt") or "")[:250], "text": str(d.get("text") or "")[:400], "vertical": bool(d.get("vertical"))}
    ws = user["workspace_id"]
    with _LOCK:
        now = time.time()
        for k in [k for k, j in _JOBS.items() if j.get("ended") and now - j["ended"] > 3600]:
            _JOBS.pop(k, None)
        if sum(1 for j in _JOBS.values() if j["ws"] == ws and j["status"] == "running") >= MAX_RUNNING:
            raise ApiError(429, "एक साथ 3 visuals बन रहे हैं — एक पूरा होने दें")
        job_id = db.new_id()
        _JOBS[job_id] = {"ws": ws, "status": "running", "message": "शुरू…", "source": clean["source"], "started": now}
    threading.Thread(target=_fetch, args=(job_id, ws, user["id"], clean), daemon=True).start()
    return ok({"job": job_id}, status=202)


@require("viewer")
async def job(request: Request, user: dict):
    j = _JOBS.get(request.path_params["job_id"])
    if not j or j["ws"] != user["workspace_id"]:
        raise ApiError(404, "job नहीं मिला (server restart हुआ हो तो दोबारा चलाएँ)")
    return ok({k: v for k, v in j.items() if k != "ws"})


@require("editor")
async def support_match(request: Request, user: dict):
    """Supporting clips / photos of a talk → where each belongs (engine/supportmatch.py). Nothing is changed here: the
    editor shows the suggestion and puts the clips on the timeline when the creator agrees.
    Body: {clips: [{id, note?}], spread?: true, image_seconds?: 4, video_seconds?: 6, use_ai?: true}"""
    from starlette.concurrency import run_in_threadpool

    from ..engine import llm, supportmatch
    p = own_project(request, user)
    d = await body(request)
    rate_limit(request, "support_match", 20)
    segs = ((p.get("transcript") or {}).get("segments")) or []
    if not segs:
        raise ApiError(409, "इस वीडियो का transcript नहीं है — बोले गए शब्दों के बिना जगह नहीं ढूँढी जा सकती। Captions tab से transcript बनाएँ।")
    raw = d.get("clips") if isinstance(d.get("clips"), list) else []
    clips = []
    for c in raw[:60]:
        if not isinstance(c, dict):
            continue
        it = db.get("library", str(c.get("id") or ""))
        if not it or it["workspace_id"] != user["workspace_id"]:
            continue
        meta = it.get("meta") or {}
        is_img = it["kind"] in ("image", "sticker", "logo") or str(it.get("mime") or "").startswith("image/")
        clips.append({"id": it["id"], "name": it["name"], "tags": [str(t) for t in (meta.get("tags") or [])][:12], "note": str(c.get("note") or "")[:200],
                      "kind": "image" if is_img else "video", "duration": float(meta.get("duration") or 0)})
    if not clips:
        raise ApiError(422, "पहले supporting clips / photos चुनें या upload करें")
    # look inside the clips once (kept in the Library item): a camera file name says nothing, the picture does
    seen_new = 0
    if d.get("use_ai", True) and llm.available() in ("gemini", "claude"):
        rows = {c["id"]: db.get("library", c["id"]) for c in clips}
        need = [c for c in clips if not (rows[c["id"]].get("meta") or {}).get("ai_seen")]

        def look() -> dict:
            todo = [{"id": c["id"], "frames": supportmatch.frames_of(storage.abs_path(rows[c["id"]]["path"]), c["kind"], c["duration"])} for c in need[:30]]
            return supportmatch.describe(todo, llm.ask_json_images)
        if need:
            found = await run_in_threadpool(look)
            with db.tx() as cx:
                for cid, text in found.items():
                    db.update(cx, "library", cid, {"meta": {**(rows[cid].get("meta") or {}), "ai_seen": text}})
                    rows[cid]["meta"] = {**(rows[cid].get("meta") or {}), "ai_seen": text}
            seen_new = len(found)
        for c in clips:
            c["seen"] = str((rows[c["id"]].get("meta") or {}).get("ai_seen") or "")
    # optional: CLIP on this server looks at the clips too (places what words and the LLM could not)
    look = None
    from ..engine import clipsee
    if clipsee.wanted() and clipsee.available():
        def see() -> dict:
            import numpy as np
            rows_ = {c["id"]: db.get("library", c["id"]) for c in clips}
            vecs, tag = {}, clipsee.model_name()
            for c in clips:
                m = rows_[c["id"]].get("meta") or {}
                if (m.get("clip_vec") or {}).get("model") == tag:
                    vecs[c["id"]] = clipsee.unpack(m["clip_vec"]["v"])
                    continue
                fr = supportmatch.frames_of(storage.abs_path(rows_[c["id"]]["path"]), c["kind"], c["duration"], max_side=336)
                if not fr:
                    continue
                v = clipsee.embed_images(fr).mean(axis=0)
                v = v / (float(np.linalg.norm(v)) or 1.0)
                vecs[c["id"]] = v
                with db.tx() as cx:
                    db.update(cx, "library", c["id"], {"meta": {**m, "clip_vec": {"model": tag, "v": clipsee.pack(v)}}})
            idx = [i for i, s_ in enumerate(segs) if (s_.get("text") or "").strip()]
            return clipsee.rank(vecs, clipsee.embed_texts([segs[i]["text"] for i in idx])) if vecs and idx else {}, idx
        try:
            ranked, idx = await run_in_threadpool(see)
            look = {cid: [(idx[i], sc) for i, sc in lst] for cid, lst in ranked.items()}
        except Exception as e:  # noqa: BLE001 — optional: words / AI still place the clips
            log.warning("CLIP matching skipped: %s", str(e)[:200])
    edl = p.get("edl") or {}
    dur = float((p.get("meta") or {}).get("duration") or edl.get("duration") or 0) or None
    ask = llm.ask_json if (d.get("use_ai", True) and llm.available()) else None
    num = lambda k, dv, lo, hi: max(lo, min(hi, float(d.get(k) or dv)))  # noqa: E731
    res = await run_in_threadpool(lambda: supportmatch.match(
        segs, clips, cuts=edl.get("cuts") or [], duration=dur, spread=bool(d.get("spread", True)),
        image_seconds=num("image_seconds", 4, 1.5, 15), video_seconds=num("video_seconds", 6, 1.5, 30), ask=ask, look=look))
    names = {c["id"]: c for c in clips}
    return ok({"placements": [{**r, "name": names[r["id"]]["name"], "kind": names[r["id"]]["kind"], "seen": names[r["id"]].get("seen", "")} for r in res],
               "seen_new": seen_new,
               "ai": any(r["how"] == "ai" for r in res), "ai_on": bool(ask), "clip_on": look is not None, "placed": sum(1 for r in res if r["start"] is not None), "total": len(res)})


@require("editor")
async def still(request: Request, user: dict):
    """One frame of the main video → a photo in the Library (to hold it on screen, or for a thumbnail).
    Body: {t: source seconds} → the library item."""
    from starlette.concurrency import run_in_threadpool

    from .. import thumbs
    from .library import _probe_meta, _view
    p = own_project(request, user)
    d = await body(request)
    rate_limit(request, "still", 30)
    try:
        t = max(0.0, float(d.get("t") or 0))
    except (TypeError, ValueError):
        raise ApiError(422, "t संख्या होनी चाहिए")
    item_id = db.new_id()
    name = f"{storage.safe_name(p.get('title') or 'video', 'video')[:40]} @ {int(t // 60)}m{t % 60:04.1f}s.jpg"
    rel = str(Path(f"ws_{user['workspace_id']}") / "library" / "image" / f"{item_id[:8]}_frame.jpg")
    dst = storage.ensure_parent(rel)

    def grab() -> None:
        img = thumbs.frame_image(p, t, max_w=1920)
        img.convert("RGB").save(dst, "JPEG", quality=93)
    try:
        await run_in_threadpool(grab)
    except Exception as e:  # noqa: BLE001
        raise ApiError(500, f"frame नहीं निकला: {str(e)[-200:]}")
    item = {"id": item_id, "workspace_id": user["workspace_id"], "kind": "image", "name": name, "path": rel, "size": dst.stat().st_size,
            "mime": "image/jpeg", "meta": {**_probe_meta(dst, "image"), "project_id": p["id"], "frame_at": round(t, 2)}, "created_by": user["id"],
            "created_at": db.now(), "tags": "frame", "source": "frame", "license": "own", "channel_id": p.get("channel_id")}
    with db.tx() as c:
        db.insert(c, "library", item)
    return ok(_view(db.get("library", item_id)), status=201)


def _music(job_id: str, ws: str, user_id: str, opts: dict) -> None:
    st = _JOBS[job_id]
    try:
        from ..engine import aimusic
        from .library import _add_file, _view
        with tempfile.TemporaryDirectory(prefix="vividora-aimusic-") as d:
            st["message"] = "fal.ai पर music बन रहा है… (आधे से एक मिनट)"
            out = aimusic.generate(opts["prompt"], opts["seconds"], Path(d) / "ai_music.mp3")
            st["message"] = "Library में रख रहा हूँ…"
            item = _add_file(ws, user_id, "music", out, name=opts["name"], tags=",".join(x for x in ("ai", opts.get("mood") or "") if x),
                             source="ai", license="AI-generated (fal.ai) — अपने video में इस्तेमाल के लिए", channel_id=opts.get("channel_id"), move=True)
        with db.tx() as c:
            db.update(c, "library", item["id"], {"meta": {**(item.get("meta") or {}), "ai_prompt": opts["prompt"][:400]}})
        st.update(status="done", message="तैयार", item=_view(db.get("library", item["id"])))
    except Exception as e:  # noqa: BLE001 — the job reports it
        log.info("ai music failed: %s", e)
        st.update(status="error", error=str(e)[:300], message="नहीं हो पाया")
    finally:
        st["ended"] = time.time()


@require("editor")
async def music_generate(request: Request, user: dict):
    """Background music from a description (engine/aimusic.py, fal.ai). Body: {mood?, text?, seconds?: 10–180, name?,
    project_id?} → 202 {job, usd}; GET /visuals/jobs/{job} → `item` = the new Library music."""
    from ..engine import aimusic
    d = await body(request)
    rate_limit(request, "music_generate", 10)
    if not aimusic.ready():
        raise ApiError(409, "fal.ai की key नहीं है — Settings → API & Keys में FAL_KEY डालें (music का दाम: लगभग $0.02 प्रति मिनट)")
    mood = d.get("mood") if d.get("mood") in aimusic.MOODS else None
    try:
        seconds = max(10.0, min(180.0, float(d.get("seconds") or 60)))
    except (TypeError, ValueError):
        raise ApiError(422, "seconds संख्या होनी चाहिए")
    text = str(d.get("text") or "")[:300]
    if not mood and not text.strip():
        raise ApiError(422, "mood चुनें या लिखें कि कैसा music चाहिए")
    channel = None
    if d.get("project_id"):
        p = db.get("projects", str(d["project_id"]))
        channel = p.get("channel_id") if p and p["workspace_id"] == user["workspace_id"] else None
    label = aimusic.MOODS[mood][0].split(" / ")[0] if mood else text[:30]
    opts = {"prompt": aimusic.build_prompt(mood, text), "seconds": seconds, "mood": mood, "channel_id": channel,
            "name": (str(d.get("name") or "").strip() or f"AI music · {label} · {int(seconds)}s")[:100]}
    ws = user["workspace_id"]
    with _LOCK:
        if any(j["ws"] == ws and j["status"] == "running" and j.get("source") == "ai_music" for j in _JOBS.values()):
            raise ApiError(429, "एक music अभी बन रहा है — उसे पूरा होने दें")
        job_id = db.new_id()
        _JOBS[job_id] = {"ws": ws, "status": "running", "message": "शुरू…", "source": "ai_music", "started": time.time()}
    threading.Thread(target=_music, args=(job_id, ws, user["id"], opts), daemon=True).start()
    return ok({"job": job_id, "usd": aimusic.estimate_usd(seconds)}, status=202)


@require("viewer")
async def music_moods(request: Request, user: dict):
    from ..engine import aimusic
    return ok({"ready": aimusic.ready(), "usd_per_min": aimusic.estimate_usd(60), "moods": [{"id": k, "label": v[0]} for k, v in aimusic.MOODS.items()]})


_SCANS: dict[tuple, dict] = {}      # (file, mtime) → speakers.scan result; a second plan with another style is instant


def _scan_cached(path: Path, duration: float, width: int, height: int, progress) -> dict:
    from ..engine import speakers
    key = (str(path), path.stat().st_mtime_ns)
    got = _SCANS.get(key)
    if got is None:
        got = speakers.scan(path, duration, width, height, progress=progress)
        with _LOCK:
            while len(_SCANS) >= 6:
                _SCANS.pop(next(iter(_SCANS)))
            _SCANS[key] = got
    return got


def _speakers(job_id: str, project: dict, opts: dict) -> None:
    st = _JOBS[job_id]
    try:
        from .. import thumbs
        from ..engine import speakers
        from .library import _probe_meta
        src = thumbs.source_video(project, quality=False)
        if src is None:
            raise ValueError("वीडियो फ़ाइल नहीं मिली")
        meta = project.get("meta") or {}
        dur = float(meta.get("duration") or 0)
        pm = _probe_meta(src, "broll")
        w, h = int(pm.get("width") or meta.get("width") or 0), int(pm.get("height") or meta.get("height") or 0)
        st["message"] = "चेहरे और होंठ देख रहा हूँ… 0%"
        main = _scan_cached(src, dur, w, h, lambda f: st.update(message=f"चेहरे और होंठ देख रहा हूँ… {int(f * 100)}%"))
        words = []
        for sg in ((project.get("transcript") or {}).get("segments")) or []:
            ws = [x for x in (sg.get("words") or []) if isinstance(x, dict) and "start" in x and "end" in x]
            words += ws or [{"start": sg.get("start", 0), "end": sg.get("end", 0)}]
        faces, cams, cam_out, norm = main["faces"], {}, None, False
        scores = main["scores"]
        who = [{"cam": 1, "face": j} for j in range(len(faces))]
        if opts.get("cam"):
            it = opts["cam"]
            cpath = storage.abs_path(it["path"])
            cm = {**_probe_meta(cpath, "broll"), **{k: v for k, v in (it.get("meta") or {}).items() if k in ("duration", "width", "height") and v}}
            cdur, cw, ch = float(cm.get("duration") or 0), int(cm.get("width") or 0), int(cm.get("height") or 0)
            if opts.get("cam_offset") is not None:
                off, conf = float(opts["cam_offset"]), None
            else:
                st["message"] = "दूसरे कैमरे को आवाज़ से मिला रहा हूँ…"
                raw = thumbs.source_video(project) or src
                off, conf = speakers.sync_offset(raw, cpath)
                if conf < 7.5:
                    raise ValueError(f"दूसरे कैमरे की आवाज़ इस वीडियो से नहीं मिली (भरोसा {conf}) — क्या दोनों एक ही समय की recording हैं और दूसरे कैमरे में आवाज़ है? "
                                     "नहीं तो नीचे “कितने सेकंड आगे/पीछे” हाथ से भरें।")
            st["message"] = "दूसरा कैमरा देख रहा हूँ… 0%"
            cam = _scan_cached(cpath, cdur, cw, ch, lambda f: st.update(message=f"दूसरा कैमरा देख रहा हूँ… {int(f * 100)}%"))
            if not cam["faces"]:
                raise ValueError("दूसरे कैमरे में चेहरा नहीं मिला — सामने से दिखता चेहरा चाहिए")
            scores, who, faces = speakers.with_camera(main, cam, off, words)
            cams = {len(who) - 1: True}
            norm = True
            cf = max(cam["faces"], key=lambda f: f["seen"] * f["h"])
            cam_out = {"id": it["id"], "name": it["name"], "offset": off, "confidence": conf, "duration": cdur, "focus_x": cf["x"], "focus_y": cf["y"]}
        if not main["faces"] and not cam_out:
            raise ValueError("चेहरा नहीं मिला — speaker switch के लिए चेहरे सामने से (या थोड़ा तिरछे) दिखने चाहिए")
        if len(who) < 2:
            raise ValueError("एक ही चेहरा मिला — बदलने के लिए दो लोग एक frame में हों, या दूसरे कैमरे की फ़ाइल जोड़ें")
        tl = speakers.turns(scores, main["fps"], words, min_turn=opts["min_turn"], norm=norm, duration=dur or None)
        sh = speakers.shots(tl, faces, dur or (tl[-1]["end"] if tl else 0), style=opts["style"], zoom=opts["zoom"], cams=cams,
                            main_close=len(main["faces"]) >= 2)
        if cam_out:      # shots of camera 2 outside its recording fall back to the main picture
            for s_ in sh:
                if s_["shot"] == "cam" and (s_["start"] + cam_out["offset"] < 0 or s_["end"] + cam_out["offset"] > cam_out["duration"] + 0.2):
                    s_["shot"] = "wide"
        talk = [0.0] * len(who)
        for t in tl:
            talk[t["who"]] += t["end"] - t["start"]
        people = []
        for j, wdef in enumerate(who):
            row = {"who": j, "cam": wdef["cam"], "talk": round(talk[j], 1)}
            if wdef["cam"] == 1 and j < len(faces):
                row.update({"x": faces[j]["x"], "y": faces[j]["y"], "h": faces[j]["h"]})
            people.append(row)
        st.update(status="done", message="तैयार", result={"shots": sh, "people": people, "faces": faces, "turns": len(tl), "cam": cam_out,
                                                         "style": opts["style"], "zoom": opts["zoom"], "main_close": len(main["faces"]) >= 2})
    except Exception as e:  # noqa: BLE001 — the job reports it
        log.info("speaker plan failed: %s", e)
        st.update(status="error", error=str(e)[:400], message="नहीं हो पाया")
    finally:
        st["ended"] = time.time()


@require("editor")
async def speakers_plan(request: Request, user: dict):
    """Who is speaking → camera plan (engine/speakers.py). Runs in the background: poll GET /visuals/jobs/{job}.
    Body: {style?: mix | close | wide_long, zoom?: 0.6–1.6, min_turn?: 1–6 s, cam?: library video id (second camera),
    cam_offset?: seconds (skip the sound match)} → {job}; the job's `result` = {shots, people, faces, turns, cam}."""
    p = own_project(request, user)
    d = await body(request)
    rate_limit(request, "speakers_plan", 12)
    opts = {"style": d.get("style") if d.get("style") in ("mix", "close", "wide_long") else "mix", "cam": None, "cam_offset": None}
    try:
        opts["zoom"] = max(0.6, min(1.6, float(d.get("zoom") or 1)))
        opts["min_turn"] = max(1.0, min(6.0, float(d.get("min_turn") or 1.8)))
        if d.get("cam_offset") not in (None, ""):
            opts["cam_offset"] = max(-7200.0, min(7200.0, float(d["cam_offset"])))
    except (TypeError, ValueError):
        raise ApiError(422, "zoom / min_turn / cam_offset संख्या होनी चाहिए")
    if d.get("cam"):
        it = db.get("library", str(d["cam"]))
        if not it or it["workspace_id"] != user["workspace_id"] or it["kind"] != "broll" or str(it.get("mime") or "").startswith("image/"):
            raise ApiError(404, "दूसरे कैमरे की वीडियो Library में नहीं मिली")
        opts["cam"] = it
    ws = user["workspace_id"]
    with _LOCK:
        if any(j["ws"] == ws and j["status"] == "running" and j.get("source") == "speakers" for j in _JOBS.values()):
            raise ApiError(429, "एक speaker जाँच चल रही है — उसे पूरा होने दें")
        job_id = db.new_id()
        _JOBS[job_id] = {"ws": ws, "status": "running", "message": "शुरू…", "source": "speakers", "started": time.time()}
    threading.Thread(target=_speakers, args=(job_id, p, opts), daemon=True).start()
    return ok({"job": job_id}, status=202)


routes = [Route("/projects/{project_id}/visuals/plan", plan, methods=["POST"]),
          Route("/projects/{project_id}/speakers/plan", speakers_plan, methods=["POST"]),
          Route("/music/generate", music_generate, methods=["POST"]),
          Route("/music/moods", music_moods),
          Route("/projects/{project_id}/still", still, methods=["POST"]),
          Route("/projects/{project_id}/support/match", support_match, methods=["POST"]),
          Route("/projects/{project_id}/visuals/fetch", fetch, methods=["POST"]),
          Route("/visuals/jobs/{job_id}", job)]
