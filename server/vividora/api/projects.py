from __future__ import annotations

from pathlib import Path

from starlette.requests import Request
from starlette.responses import FileResponse
from starlette.routing import Route

from .. import db, service, storage
from ..engine import autocut
from ..engine import catalog, encode, procatalog, textfx
from ..engine import autopilot as autopilot_eng
from ..engine.effects import BODY_ANIMS, BODY_BG, EXTRAS, LOOKS, STICKER_ANIMS, TEXT_ANIMS, TRANSITIONS, VOICE_PARAMS, VOICE_PRESETS, ZOOM_MODES, BLENDS
from ..engine.presets import caption_styles, platforms
from ..security import media_token, read_token
from .channels import channel_settings, get_channel
from .deps import ApiError, body, need, ok, own_project, require

STATUSES = ("uploading", "preparing", "transcribing", "cutting", "review_cuts", "rendering",
            "review_output", "approved", "failed")


@require("viewer")
async def list_projects(request: Request, user: dict):
    q = "SELECT * FROM projects WHERE workspace_id = ? AND kind != 'tools'"
    args: list = [user["workspace_id"]]
    status = request.query_params.get("status")
    if status in STATUSES:
        q += " AND status = ?"
        args.append(status)
    ch = request.query_params.get("channel")
    if ch:
        q += " AND channel_id = ?"
        args.append(ch)
    q += " ORDER BY updated_at DESC LIMIT 200"
    projects = db.rows(db.conn().execute(q, args))
    pids = [p["id"] for p in projects]
    if pids:
        marks = ", ".join("?" for _ in pids)
        thumbs = {a["project_id"]: a["id"] for a in db.rows(db.conn().execute(
            f"SELECT id, project_id FROM assets WHERE kind = 'thumb' AND project_id IN ({marks})", pids))}
    else:
        thumbs = {}
    out = []
    for p in projects:
        p.pop("transcript", None)
        p.pop("edl", None)
        sel = (p.get("meta") or {}).get("thumbnail") or {}
        tid = (sel.get("yt") or sel.get("vertical") or next(iter(sel.values()), None)) if isinstance(sel, dict) and sel else None
        tid = tid or thumbs.get(p["id"])
        p["thumb_url"] = f"/api/media/{tid}?t={media_token(tid)}" if tid else None
        out.append(p)
    return ok(out)


@require("editor")
async def create_project(request: Request, user: dict):
    data = await body(request)
    need(data, "title")
    p = new_project_row(user, data)
    with db.tx() as c:
        db.insert(c, "projects", p)
        service.log(c, user["workspace_id"], "project.create", user_id=user["id"], project_id=p["id"],
                    detail={"title": p["title"]})
    return ok(service.project_view(p), 201)


def new_project_row(user: dict, data: dict) -> dict:
    """A project row with the channel's brand kit / render defaults applied (not yet inserted)."""
    channel = get_channel(user["workspace_id"], data.get("channel_id"))
    ws_settings = channel_settings(user["workspace_id"], channel["id"] if channel else None)
    brand = ws_settings.get("brand", {}) or {}
    brand_render = {}
    if brand.get("caption_style"):
        brand_render["caption_style"] = brand["caption_style"]
    if any(brand.get(k) for k in ("primary", "highlight", "font")):
        brand_render["captions"] = {**service.DEFAULT_RENDER["captions"], "primary": brand.get("primary", ""), "highlight": brand.get("highlight", ""), "font": brand.get("font", "")}
    if brand.get("logo_id") or brand.get("grade_preset"):
        from ..engine.catalog import GRADE_PRESETS
        eff = {**service.DEFAULT_EFFECTS}
        if brand.get("logo_id"):
            eff["watermark"] = {"id": brand["logo_id"], "opacity": 0.75, "size": 0.12, "pos": brand.get("watermark_pos", "tr")}
        if brand.get("grade_preset") in GRADE_PRESETS:
            eff["grade"] = {k: v for k, v in GRADE_PRESETS[brand["grade_preset"]].items() if k != "label"}
            eff["grade_preset"] = brand["grade_preset"]
        brand_render["effects"] = eff
    p = {"id": db.new_id(), "workspace_id": user["workspace_id"], "created_by": user["id"], "channel_id": channel["id"] if channel else None,
         "title": data["title"].strip()[:200], "kind": data.get("kind", "talking_head"),
         "language": data.get("language") or (channel or {}).get("language") or "auto",
         "status": "review_cuts" if data.get("kind") == "montage" else "uploading",
         "status_note": "clips, music और text चुनकर montage बनाएँ" if data.get("kind") == "montage" else "upload का इंतज़ार",
         "meta": {}, "transcript": None, "edl": None,
         "settings": {"render": {**brand_render, **(ws_settings.get("render_defaults", {}) or {}), **data.get("render", {})},
                      "autocut": data.get("autocut", {}),
                      "autopilot": bool(data.get("autopilot", False)) and data.get("kind") != "montage",
                      # "Transcript छोड़ें": no speech-to-text; cuts come from silence + scenes, captions/AI text later on request
                      "skip_transcript": bool(data.get("skip_transcript", False)) and data.get("kind") != "montage",
                      # one-click theme (presets/themes or a saved one) — autopilot applies it at the plan stage
                      "theme_id": str(data.get("theme_id") or "")[:40]},
         "approved_by": None, "approved_at": None, "created_at": db.now(), "updated_at": db.now()}
    return p


def _with_urls(view: dict) -> dict:
    for a in view["assets"]:
        a["url"] = f"/api/media/{a['id']}?t={media_token(a['id'])}"
    return view


@require("viewer")
async def get_project(request: Request, user: dict):
    p = own_project(request, user)
    return ok(_with_urls(service.project_view(p)))


@require("editor")
async def update_project(request: Request, user: dict):
    p = own_project(request, user)
    data = await body(request)
    changes: dict = {}
    if data.get("title"):
        changes["title"] = data["title"].strip()[:200]
    if data.get("channel_id") and get_channel(user["workspace_id"], data["channel_id"]):
        changes["channel_id"] = data["channel_id"]
    if "settings" in data and isinstance(data["settings"], dict):
        changes["settings"] = {**p["settings"], **data["settings"]}
    if "edl" in data and isinstance(data["edl"], dict):
        # the dashboard toggles / trims cuts; keep stats honest
        edl = {**(p["edl"] or {}), **data["edl"]}
        cuts = [c for c in edl.get("cuts", []) if float(c["end"]) > float(c["start"])]
        removed = sum(float(c["end"]) - float(c["start"]) for c in cuts if c.get("enabled", True))
        edl["cuts"] = cuts
        edl["stats"] = {**edl.get("stats", {}), "cuts": sum(1 for c in cuts if c.get("enabled", True)),
                        "removed_seconds": round(removed, 2),
                        "final_seconds": round(float(edl["duration"]) - removed, 2)}
        changes["edl"] = edl
    if "transcript" in data and isinstance(data["transcript"], dict):
        # the editor may still hold the transcript from before a re-transcribe: lines re-heard since
        # are merged in; after a whole re-transcribe the old words are not written back
        fresh = service.transcript_for_save(p.get("transcript"), data["transcript"])
        if fresh is None:
            data.pop("transcript")
        else:
            fresh["text"] = " ".join((s.get("text") or "").strip() for s in fresh.get("segments") or []).strip()
            data["transcript"] = fresh
    if "transcript" in data and isinstance(data["transcript"], dict):
        changes["transcript"] = data["transcript"]
        # remember the creator's word corrections for this channel → future transcripts get them automatically
        from ..engine import vocab
        learned = vocab.learn(p.get("transcript"), data["transcript"])
        if learned:
            ch = service.project_channel(p)
            if ch.get("id"):
                st = ch.get("settings") or {}
                st["vocab_fixes"] = vocab.merge_fixes(st.get("vocab_fixes"), learned)
                with db.tx() as c2:
                    db.update(c2, "channels", ch["id"], {"settings": st, "updated_at": db.now()})
    if isinstance(data.get("meta"), dict) and isinstance(data["meta"].get("shorts"), list):
        changes["meta"] = {**p["meta"], "shorts": data["meta"]["shorts"][:40]}
    if changes:
        changes["updated_at"] = db.now()
        with db.tx() as c:
            if "settings" in changes or "edl" in changes:
                # version history: keep the state BEFORE this change (last 40 per project, 1 per ~30 s)
                last = db.row(c.execute("SELECT created_at FROM history WHERE project_id = ? ORDER BY id DESC LIMIT 1", (p["id"],)).fetchone())
                recent = last and (db.now()[:16] == last["created_at"][:16])
                if not recent:
                    db.insert(c, "history", {"project_id": p["id"], "user_id": user["id"], "note": data.get("note") or ", ".join(changes.keys() - {"updated_at"}),
                                             "settings": p["settings"], "edl": p.get("edl"), "meta": {"shorts": (p.get("meta") or {}).get("shorts")},
                                             "created_at": db.now()})
                    c.execute("DELETE FROM history WHERE project_id = ? AND id NOT IN (SELECT id FROM history WHERE project_id = ? ORDER BY id DESC LIMIT 40)", (p["id"], p["id"]))
            db.update(c, "projects", p["id"], changes)
            service.log(c, user["workspace_id"], "project.update", user_id=user["id"],
                        project_id=p["id"], detail={"fields": list(changes)})
    return ok(_with_urls(service.project_view(db.get("projects", p["id"]))))


def _analysis(p: dict) -> dict:
    """Cached picture/sound measurements; measured on demand for older projects."""
    a = (p.get("meta") or {}).get("analysis")
    if a:
        return a
    from ..engine import analyze
    proxy = service.asset_of(p["id"], "proxy") or service.asset_of(p["id"], "raw")
    asr = service.asset_of(p["id"], "audio_asr")
    if not proxy:
        return {}
    a = analyze.measure(storage.abs_path(proxy["path"]), float(p["meta"].get("duration") or 0),
                        storage.abs_path(asr["path"]) if asr else None)
    with db.tx() as c:
        cur = db.get("projects", p["id"])
        db.update(c, "projects", p["id"], {"meta": {**(cur.get("meta") or {}), "analysis": a}})
    return a


@require("viewer")
async def suggestions(request: Request, user: dict):
    """“क्या कमी है” — measured problems + one-click fixes for the editor."""
    from starlette.concurrency import run_in_threadpool
    from ..engine import analyze
    p = own_project(request, user)
    a = await run_in_threadpool(_analysis, p)
    rs = {**service.DEFAULT_RENDER, **p.get("settings", {}).get("render", {})}
    lib = db.rows(db.conn().execute("SELECT id, kind, name, tags FROM library WHERE workspace_id = ? AND kind = 'music' ORDER BY created_at",
                                    (user["workspace_id"],)))
    return ok({"analysis": a, "pace": analyze.pace(p), "items": analyze.suggest(p, rs, a, library=lib),
               "auto_grade": analyze.auto_grade(a)})


@require("viewer")
async def audio_preview(request: Request, user: dict):
    """~12 s of the finished sound (voice enhancement + music) from time t, as MP3 — to hear settings before rendering."""
    import subprocess
    import tempfile
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import Response
    from ..engine import effects as fxm
    p = own_project(request, user)
    data = await body(request)
    t = max(0.0, float(data.get("t") or 0))
    dur = min(20.0, max(3.0, float(data.get("seconds") or 12)))
    opts = {**service.DEFAULT_RENDER, **p.get("settings", {}).get("render", {}), **(data.get("render") or {})}
    eff = service.resolve_effects_local(p, opts.get("effects") or {}, audio=True)
    raw = bool(data.get("raw"))  # A/B: the untouched voice — no enhancement, no music
    voice = {"preset": "off"} if raw else (eff.get("voice") or {})
    src = None if voice.get("denoise") in ("light", "off") else service.asset_of(p["id"], "audio_clean")
    src = src or service.asset_of(p["id"], "raw")
    if str(data.get("src") or "").startswith("dub:"):
        # A/B of an AI voice line: the dub track itself (its timing is the output timeline)
        a = db.get("assets", str(data["src"])[4:])
        if not a or a["project_id"] != p["id"] or a["kind"] != "dub":
            raise ApiError(404, "voice track नहीं मिला")
        src = a
    if not src:
        raise ApiError(400, "आवाज़ नहीं मिली")

    def work() -> bytes:
        with tempfile.TemporaryDirectory(prefix="vap_") as td:
            out = Path(td) / "p.mp3"
            args = ["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-t", f"{dur:.2f}", "-i", str(storage.abs_path(src["path"]))]
            vchain = "" if raw else fxm.voice_chain(voice, dur)
            fc = f"[0:a]aformat=sample_rates=48000:channel_layouts=mono{',' + vchain if vchain else ''}[voice]"
            cur = "[voice]"
            music = {} if raw else (eff.get("music") or {})
            if music.get("path"):
                args += ["-stream_loop", "-1", "-i", music["path"]]
                chain, cur = fxm.music_chain(cur, 1, volume=float(music.get("volume", 0.18)), duck=bool(music.get("duck", True)),
                                             duration=dur, fade=min(1.0, float(music.get("fade", 1.5))),
                                             duck_amount=float(music.get("duck_amount", 0.6)))
                fc += ";" + chain
            target = fxm.voice_settings(voice).get("loudness", -14)
            tail = "" if raw else fxm.voice_tail(voice)
            fc += f";{cur}loudnorm=I={target}:TP=-1.5:LRA=11,aresample=48000{',' + tail if tail else ''}[a]"
            subprocess.run([*args, "-filter_complex", fc, "-map", "[a]", "-t", f"{dur:.2f}", "-c:a", "libmp3lame", "-b:a", "128k", str(out)],
                           check=True, capture_output=True)
            return out.read_bytes()
    try:
        mp3 = await run_in_threadpool(work)
    except subprocess.CalledProcessError as e:
        raise ApiError(500, "audio preview नहीं बना: " + (e.stderr or b"").decode(errors="ignore")[-300:]) from None
    return Response(mp3, media_type="audio/mpeg")


@require("viewer")
async def ai_prompts(request: Request, user: dict):
    """Prompt Studio: prompts for hook video, B-roll, cut-out background and thumbnail (Grok / ChatGPT / Veo)."""
    from starlette.concurrency import run_in_threadpool
    from ..engine import prompts
    p = own_project(request, user)
    dur = float((p.get("meta") or {}).get("duration") or 0)
    plat = request.query_params.get("platform") or ("short" if dur <= 75 else "long")
    n = max(1, min(10, int(request.query_params.get("broll") or 4)))
    items = await run_in_threadpool(prompts.suggest, p, plat, n)
    return ok({"platform": plat, "items": items, "batch": prompts.batch(items)})


@require("viewer")
async def ai_pack(request: Request, user: dict):
    """The one-call AI pack (hooks, metadata for every platform, thumbnail texts, pinned comment, prompts)
    + how many AI calls the cache has saved."""
    from starlette.concurrency import run_in_threadpool
    from ..engine import aipack, llm
    p = own_project(request, user)
    pack = await run_in_threadpool(aipack.get, p) if p.get("transcript") else None
    return ok({"pack": pack, "llm": llm.stats()})


@require("viewer")
async def preflight(request: Request, user: dict):
    """Platform rule check (duration, hook, safe zones, hashtags, originality) for the chosen presets."""
    from ..engine import platform_rules
    p = own_project(request, user)
    rs = {**service.DEFAULT_RENDER, **p.get("settings", {}).get("render", {})}
    q = request.query_params.get("presets")
    presets = q.split(",") if q else (rs.get("presets") or ["yt-short", "ig-reel", "fb-reel"])
    plan = (p.get("meta") or {}).get("publish_plan") or []
    mt = {}
    for it in plan:
        key = {"youtube": "yt-long" if it.get("label") == "yt-long" else "yt-short", "instagram": "ig-reel", "facebook": "fb-reel"}.get(it.get("platform"))
        if key:
            mt[key] = {"title": it.get("title"), "description": it.get("description"), "tags": it.get("tags")}
    return ok({"presets": presets, "items": platform_rules.check(p, rs, presets, mt)})


@require("viewer")
async def hook_studio(request: Request, user: dict):
    """Hook score for the opening + three hook options."""
    from starlette.concurrency import run_in_threadpool
    from ..engine import hooks
    p = own_project(request, user)
    rs = {**service.DEFAULT_RENDER, **p.get("settings", {}).get("render", {})}
    dur = float((p.get("meta") or {}).get("duration") or 0)
    plat = request.query_params.get("platform") or ("short" if dur <= 75 else "long")
    sc = hooks.score(p, rs, plat)
    opts = await run_in_threadpool(hooks.options, p)
    return ok({**sc, "options": opts, "platform": plat})


@require("editor")
async def autopilot_apply(request: Request, user: dict):
    """Run autopilot's choices on this project now (without rendering). mode=items: only stickers/text/sfx/CTA;
    mode=all: every setting autopilot decides. Items the creator added by hand stay."""
    p = own_project(request, user)
    if not p.get("transcript"):
        raise ApiError(400, "पहले transcript बनने दें")
    data = await body(request)
    mode = data.get("mode") or "items"
    plan = service.autopilot_plan(p)
    plan.pop("autopilot", None)
    cur = {**service.DEFAULT_RENDER, **p.get("settings", {}).get("render", {})}
    eff = dict(cur.get("effects") or {})
    pe = plan["effects"]
    for key in ("broll", "titles", "sfx"):
        mine = [x for x in (eff.get(key) or []) if not str(x.get("_id", "")).startswith("ap_")]
        eff[key] = mine + pe.get(key, [])
    if mode == "all":
        for k, v in pe.items():
            if k not in ("broll", "titles", "sfx"):
                eff[k] = v
        cur.update({k: v for k, v in plan.items() if k != "effects"})
    cur["effects"] = eff
    with db.tx() as c:
        db.update(c, "projects", p["id"], {"settings": {**p["settings"], "render": cur}, "updated_at": db.now()})
        service.log(c, user["workspace_id"], "project.autopilot_apply", user_id=user["id"], project_id=p["id"], detail={"mode": mode})
    return ok(_with_urls(service.project_view(db.get("projects", p["id"]))))


@require("editor")
async def autopilot_resume(request: Request, user: dict):
    """“Autopilot फिर चलाएँ”: continue the autopilot sequence from the step that failed or stalled
    (or run it again on a finished project). Nothing is published — approval stays manual."""
    from .. import autopilot_flow
    p = own_project(request, user)
    if p.get("kind") == "montage":
        raise ApiError(400, "montage project पर autopilot नहीं चलता")
    if p["status"] == "uploading":
        raise ApiError(400, "पहले recording upload करें")
    with db.tx() as c:
        step = autopilot_flow.resume(c, db.get("projects", p["id"]))
        service.log(c, user["workspace_id"], "project.autopilot_resume", user_id=user["id"], project_id=p["id"], detail={"step": step})
    return ok({"step": step, **_with_urls(service.project_view(db.get("projects", p["id"])))})


@require("viewer")
async def autopilot_status(request: Request, user: dict):
    """The autopilot sequence for the progress UI: every step with done / current / todo / failed."""
    from .. import autopilot_flow
    from ..engine import autopilot as ap_eng
    p = own_project(request, user)
    st = autopilot_flow.state(p)
    cur = st.get("stage")
    n = ap_eng.step_no(cur) if cur in ap_eng.STEP_KEYS else (len(ap_eng.STEPS) + 1 if cur == ap_eng.READY else 0)
    steps = [{"key": k, "label": lbl, "n": i + 1,
              "state": "failed" if st.get("failed") == k else "done" if i + 1 < n else "current" if i + 1 == n else "todo"}
             for i, (k, lbl) in enumerate(ap_eng.STEPS)]
    job = db.row(db.conn().execute("SELECT kind, status, progress, message FROM jobs WHERE project_id = ? AND status = 'running' "
                                   "ORDER BY started_at DESC LIMIT 1", (p["id"],)).fetchone())
    return ok({"on": bool((p.get("settings") or {}).get("autopilot")), "stage": cur, "steps": steps, "job": job,
               "note": p.get("status_note"), "status": p["status"], "percent": st.get("percent", 0),
               "warnings": st.get("warnings") or [], "preflight": st.get("preflight") or [], "hook_score": st.get("hook_score")})


@require("editor")
async def retranscribe(request: Request, user: dict):
    """Run speech-to-text again.

    Empty body → the whole recording (new model / new vocabulary); the cut list is rebuilt
    afterwards, keeping the creator's manual cuts and switched-off cuts.
    {"start": s, "end": e} (source seconds) or {"segments": [i, ...]} → only that part:
    the project stays in its editing state and only words inside the part are replaced.
    Optional: "alternatives" (0–3, default 2 for a part), "model" (e.g. "medium")."""
    p = own_project(request, user)
    if not any(a["kind"] == "audio_asr" for a in service.project_view(p).get("assets", [])):
        raise ApiError(400, "इस project में आवाज़ नहीं है")
    data = await body(request)
    from .. import queue
    try:
        payload = service.transcribe_payload(p, part=data)
    except ValueError as e:
        raise ApiError(400, str(e)) from None
    with db.tx() as c:
        busy = db.rows(c.execute("SELECT id, status, payload FROM jobs WHERE project_id = ? AND kind = 'transcribe' "
                                 "AND status IN ('queued','running')", (p["id"],)))
        if payload.get("range"):
            if any(not (j.get("payload") or {}).get("range") for j in busy) or p["status"] == "transcribing":
                raise ApiError(409, "पूरा transcript अभी बन रहा है — उसके बाद line दोबारा बनाएँ")
            if not p.get("transcript"):
                raise ApiError(400, "पहले transcript बनने दें")
            job = queue.enqueue(c, p["id"], "transcribe", payload)
            db.update(c, "projects", p["id"], {"status_note": "line दोबारा सुन रहे हैं…", "updated_at": db.now()})
            service.log(c, user["workspace_id"], "project.retranscribe_part", user_id=user["id"], project_id=p["id"],
                        detail={"range": payload["range"]})
            return ok({"job": job})
        # whole recording: an older transcribe (whole or one line) must not land on top of the new one
        for j in busy:
            db.update(c, "jobs", j["id"], {"status": "cancelled", "finished_at": db.now(),
                                           "message": "नया transcript माँगा गया"})
        if data.get("later") or (p.get("transcript") or {}).get("skipped"):
            # "Transcript बाद में बनाएँ": an independent job — the project keeps its status, cuts, overlays and music;
            # only the words are filled in (no autocut / autopilot afterwards)
            payload.update(later=True, retranscribe=False)
            job = queue.enqueue(c, p["id"], "transcribe", payload)
            db.update(c, "projects", p["id"], {"status_note": "transcript पीछे बन रहा है — editing जारी रखें", "updated_at": db.now()})
            service.log(c, user["workspace_id"], "project.transcribe_later", user_id=user["id"], project_id=p["id"])
            return ok({"job": job, "later": True})
        service.set_status(c, p["id"], "transcribing", "transcript दोबारा बन रहा है")
        job = queue.enqueue(c, p["id"], "transcribe", payload)
        service.log(c, user["workspace_id"], "project.retranscribe", user_id=user["id"], project_id=p["id"])
    return ok({"job": job})


@require("editor")
async def delete_project(request: Request, user: dict):
    p = own_project(request, user)
    if p["status"] == "approved" and user["role"] != "admin":
        raise ApiError(403, "approved project सिर्फ़ admin हटा सकता है")
    also_archive = request.query_params.get("archive") in ("1", "true", "yes")
    with db.tx() as c:
        service.delete_project(c, p)
        service.log(c, user["workspace_id"], "project.delete", user_id=user["id"], project_id=p["id"],
                    detail={"title": p["title"], "archive_copy_deleted": also_archive})
    if also_archive:
        from starlette.concurrency import run_in_threadpool
        from .. import cleanup
        await run_in_threadpool(cleanup.delete_archive_copy, p["workspace_id"], p["id"])
    return ok()


@require("editor")
async def recut(request: Request, user: dict):
    """Rebuild the cut list with new sensitivity (after the transcript exists)."""
    p = own_project(request, user)
    if not p.get("transcript"):
        raise ApiError(400, "transcript अभी नहीं बना")
    data = await body(request)
    opts = {**p["settings"].get("autocut", {}), **(data.get("options") or {})}
    with db.tx() as c:
        db.update(c, "projects", p["id"], {"settings": {**p["settings"], "autocut": opts}})
        service.set_status(c, p["id"], "cutting", "कट दोबारा ढूँढे जा रहे हैं")
        job = service.queue.enqueue(c, p["id"], "autocut", {"options": opts})
    return ok({"job": job})


@require("viewer")
async def encoders(request: Request, user: dict):
    """Which codecs/containers this server's ffmpeg can write (the export modal hides the rest)."""
    return ok(encode.available())


@require("viewer")
async def export_estimate(request: Request, user: dict):
    """Rough output size per chosen preset for the export overrides in the body ("लगभग")."""
    p = own_project(request, user)
    data = await body(request)
    exp = encode.normalize(data.get("export"))
    dur = float(data.get("duration") or p.get("meta", {}).get("duration") or 0)
    out = {}
    for pid in data.get("presets") or []:
        pr = platforms().get(pid)
        if pr:
            pl = encode.plan(exp, pr, p.get("meta") or {}, float((p.get("meta") or {}).get("fps") or 30))
            out[pid] = {"bytes": encode.estimate_bytes(exp, pr, p.get("meta") or {}, dur), "width": pl["width"],
                        "height": pl["height"], "fps": pl["fps"], "codec": pl["codec"], "container": pl["container"]}
    return ok({"estimate": out, "export": exp})


@require("viewer")
async def multiformat_analyze(request: Request, user: dict):
    """Smart reframing analysis — returns per-preset optimal focus + crop info."""
    p = own_project(request, user)
    from ..engine import multiformat
    meta = p.get("meta") or {}
    data = await body(request)
    presets = data.get("presets") or [pr for pr in platforms()]
    analysis = multiformat.analyze(meta, presets)
    suggestions = multiformat.suggested_presets(meta)
    # Add crop preview rectangles for the frontend overlay
    previews = {}
    for pid in presets:
        previews[pid] = multiformat.preview_crop(meta, pid, frame_w=640)
    return ok({"analysis": analysis, "suggestions": suggestions, "previews": previews})


@require("editor")
async def render(request: Request, user: dict):
    p = own_project(request, user)
    if p["status"] in ("uploading", "preparing", "transcribing", "cutting"):
        raise ApiError(400, "पहले transcript और कट पूरे होने दें")
    data = await body(request)
    try:
        with db.tx() as c:
            jobs = service.request_render(c, p, data)
            service.log(c, user["workspace_id"], "project.render", user_id=user["id"],
                        project_id=p["id"], detail={"presets": [j.get("payload", {}).get("preset", "deferred") for j in jobs]})
    except ValueError as e:
        raise ApiError(422, str(e))
    return ok({"jobs": jobs})


@require("viewer")
async def history_list(request: Request, user: dict):
    p = own_project(request, user)
    rows = db.rows(db.conn().execute("SELECT h.id, h.note, h.created_at, u.name AS user_name FROM history h LEFT JOIN users u ON u.id = h.user_id "
                                     "WHERE h.project_id = ? ORDER BY h.id DESC LIMIT 40", (p["id"],)))
    return ok(rows)


@require("editor")
async def history_restore(request: Request, user: dict):
    p = own_project(request, user)
    h = db.get("history", int(request.path_params["hid"]))
    if not h or h["project_id"] != p["id"]:
        raise ApiError(404, "version not found")
    with db.tx() as c:
        db.insert(c, "history", {"project_id": p["id"], "user_id": user["id"], "note": "restore से पहले", "settings": p["settings"],
                                 "edl": p.get("edl"), "meta": {"shorts": (p.get("meta") or {}).get("shorts")}, "created_at": db.now()})
        meta = {**(p.get("meta") or {})}
        if (h.get("meta") or {}).get("shorts") is not None:
            meta["shorts"] = h["meta"]["shorts"]
        db.update(c, "projects", p["id"], {"settings": h["settings"], "edl": h["edl"], "meta": meta, "updated_at": db.now()})
        service.log(c, user["workspace_id"], "project.restore", user_id=user["id"], project_id=p["id"], detail={"history_id": h["id"]})
    return ok(_with_urls(service.project_view(db.get("projects", p["id"]))))


@require("editor")
async def archive_now(request: Request, user: dict):
    from .. import archive
    p = own_project(request, user)
    if p["status"] != "approved":
        raise ApiError(400, "सिर्फ़ मंज़ूर projects archive होते हैं")
    from starlette.concurrency import run_in_threadpool
    r = await run_in_threadpool(archive.archive_project, p["id"])
    if r.get("error"):
        raise ApiError(400, r["error"])
    with db.tx() as c:
        service.log(c, user["workspace_id"], "project.archive", user_id=user["id"], project_id=p["id"], detail=r)
    return ok(r)


@require("editor")
async def restore_now(request: Request, user: dict):
    from .. import archive
    p = own_project(request, user)
    from starlette.concurrency import run_in_threadpool
    r = await run_in_threadpool(archive.restore_project, p["id"])
    if r.get("error"):
        raise ApiError(400, r["error"])
    return ok(r)


@require("viewer")
async def preview_frame(request: Request, user: dict):
    """One rendered frame (JPEG) at source time t with the current/sent settings — for effects that CSS can't fake."""
    import tempfile
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import Response
    from ..engine import render as render_engine
    from ..engine.presets import caption_style, platform
    p = own_project(request, user)
    data = await body(request)
    t = max(0.0, float(data.get("t") or request.query_params.get("t") or 0))
    opts = {**service.DEFAULT_RENDER, **p.get("settings", {}).get("render", {}), **(data.get("render") or {})}
    raw = service.asset_of(p["id"], "raw")
    if not raw:
        raise ApiError(400, "recording नहीं मिली")
    eff = service.resolve_effects_local(p, opts.get("effects") or {})
    preset = platform(data.get("preset") or (opts.get("presets") or ["yt-short"])[0])
    style = caption_style(opts.get("caption_style", "karaoke"))
    fps = float(p["meta"].get("fps") or 30)

    # start a little earlier so text fade-ins have finished on the frame we grab
    t0 = max(0.0, t - 0.4)

    # the real cut list, so text / overlays / effect clips (timed after cuts) land where the editor shows them;
    # a playhead inside a removed part falls back to the uncut recording
    from ..engine.autocut import keep_segments
    edl_now = {"duration": p["meta"]["duration"], "cuts": [], **(p.get("edl") or {})}
    if not any(a <= t < b for a, b in keep_segments(edl_now)):
        edl_now = {"duration": p["meta"]["duration"], "cuts": []}

    def work() -> bytes:
        with tempfile.TemporaryDirectory(prefix="vfr_") as td:
            out = render_engine.render(video=storage.abs_path(raw["path"]), audio=None, meta={**p["meta"], "has_audio": False},
                                       edl=edl_now, transcript=p.get("transcript"),
                                       preset=preset, style=style, out_dir=Path(td), name="frame", hook=opts.get("hook"),
                                       focus_x=float(opts.get("focus_x", 0.5)), focus_y=float(opts.get("focus_y", 0.5)),
                                       burn_captions=opts.get("burn_captions"), caption_overrides=opts.get("captions"),
                                       effects=eff, clip={"start": t0, "end": t + 2.5 / fps}, face_track="off",
                                       encoder_preset="ultrafast", on_progress=None)
            jpg = Path(td) / "frame.jpg"
            import subprocess
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, t - t0 - 0.5 / fps):.3f}", "-i", str(out["files"][0]["path"]), "-frames:v", "1", "-q:v", "4", str(jpg)], check=True)
            return jpg.read_bytes()

    try:
        img = await run_in_threadpool(work)
    except Exception as e:  # noqa: BLE001
        raise ApiError(500, f"frame नहीं बना: {str(e)[-300:]}")
    return Response(img, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@require("editor")
async def matte_now(request: Request, user: dict):
    """Build (or rebuild) the person cutout for this project."""
    p = own_project(request, user)
    if not service.asset_of(p["id"], "proxy"):
        raise ApiError(400, "पहले preview बनने दें")
    data = await body(request)
    q = data.get("quality") if data.get("quality") in ("fast", "balanced", "hair") else "balanced"
    with db.tx() as c:
        running = c.execute("SELECT COUNT(*) FROM jobs WHERE project_id = ? AND kind = 'matte' AND status IN ('queued','running')", (p["id"],)).fetchone()[0]
        if running:
            return ok({"job": None, "running": True})
        job = service.queue.enqueue(c, p["id"], "matte", {"quality": q})
        service.log(c, user["workspace_id"], "matte.start", user_id=user["id"], project_id=p["id"])
    return ok({"job": job})


@require("editor")
async def matte_lib_now(request: Request, user: dict):
    """Person cutout of one library video (for a "सिर्फ़ इंसान" overlay) — cached on the library item."""
    from .. import cutout
    p = own_project(request, user)
    data = await body(request)
    lid = str(data.get("library_id") or "")
    item = db.get("library", lid)
    if not item or item["workspace_id"] != user["workspace_id"]:
        raise ApiError(404, "library item नहीं मिला")
    with db.tx() as c:
        try:
            job = cutout.queue_lib(c, p["id"], lid, str(data.get("quality") or "balanced"), force=bool(data.get("force")))
        except ValueError as e:
            raise ApiError(400, str(e))
        if job:
            service.log(c, user["workspace_id"], "matte_lib.start", user_id=user["id"], project_id=p["id"], detail={"library_id": lid})
    return ok({"job": job, "cached": job is None and cutout.lib_alpha(item) is not None})


@require("editor")
async def montage_render(request: Request, user: dict):
    p = own_project(request, user)
    # montage render चलने दें — पुराना cancel हो जाता है (queue.enqueue already handles this)
    data = await body(request)
    try:
        with db.tx() as c:
            job = service.request_montage(c, p, data)
            service.log(c, user["workspace_id"], "montage.render", user_id=user["id"], project_id=p["id"])
    except ValueError as e:
        raise ApiError(422, str(e))
    return ok({"job": job})


@require("editor")
async def shorts_plan(request: Request, user: dict):
    p = own_project(request, user)
    data = await body(request)
    try:
        with db.tx() as c:
            job = service.request_shorts_plan(c, p, data.get("options"))
            service.log(c, user["workspace_id"], "shorts.plan", user_id=user["id"], project_id=p["id"])
    except ValueError as e:
        raise ApiError(422, str(e))
    return ok({"job": job})


@require("editor")
async def shorts_render(request: Request, user: dict):
    p = own_project(request, user)
    if p["status"] in ("uploading", "preparing", "transcribing", "cutting"):
        raise ApiError(400, "पहले transcript और कट पूरे होने दें")
    data = await body(request)
    clips = data.get("clips") or []
    if not isinstance(clips, list):
        raise ApiError(422, "clips list चाहिए")
    try:
        with db.tx() as c:
            jobs = service.request_shorts_render(c, p, clips, data.get("render") or {})
            service.log(c, user["workspace_id"], "shorts.render", user_id=user["id"], project_id=p["id"],
                        detail={"count": len(jobs)})
    except ValueError as e:
        raise ApiError(422, str(e))
    return ok({"jobs": jobs})


@require("editor")
async def job_cancel(request: Request, user: dict):
    """Stop one job (queued: gone now; running: the worker stops ffmpeg on its next heartbeat)."""
    p = own_project(request, user)
    job = db.get("jobs", request.path_params["job_id"])
    if not job or job["project_id"] != p["id"]:
        raise ApiError(404, "job नहीं मिला")
    if job["status"] not in ("queued", "running"):
        raise ApiError(409, f"job पहले ही {job['status']} है")
    with db.tx() as c:
        job = service.cancel_job(c, job, by=user.get("name"))
        service.log(c, user["workspace_id"], "job.cancel", user_id=user["id"], project_id=p["id"],
                    detail={"job_id": job["id"], "kind": job["kind"]})
    return ok({"job": job, "project": _with_urls(service.project_view(db.get("projects", p["id"])))})


@require("editor")
async def job_pause(request: Request, user: dict):
    """Pause a render: stops it now (finished pieces stay in the worker's cache); the next render of the
    same settings picks those pieces up instead of starting over."""
    p = own_project(request, user)
    job = db.get("jobs", request.path_params["job_id"])
    if not job or job["project_id"] != p["id"]:
        raise ApiError(404, "job नहीं मिला")
    if job["status"] not in ("queued", "running"):
        raise ApiError(409, f"job पहले ही {job['status']} है")
    with db.tx() as c:
        job = service.cancel_job(c, job, by=user.get("name"), note="रोका — दोबारा render पर बने हुए टुकड़े वहीं से उठेंगे")
        service.log(c, user["workspace_id"], "job.pause", user_id=user["id"], project_id=p["id"],
                    detail={"job_id": job["id"], "kind": job["kind"]})
    return ok({"job": job, "project": _with_urls(service.project_view(db.get("projects", p["id"])))})


@require("admin")
async def approve(request: Request, user: dict):
    p = own_project(request, user)
    if p["status"] != "review_output":
        raise ApiError(400, "पहले render पूरा होने दें")
    with db.tx() as c:
        db.update(c, "projects", p["id"], {"status": "approved", "status_note": "मंज़ूर",
                                           "approved_by": user["id"], "approved_at": db.now(),
                                           "updated_at": db.now()})
        service.log(c, user["workspace_id"], "project.approve", user_id=user["id"], project_id=p["id"])
    return ok(_with_urls(service.project_view(db.get("projects", p["id"]))))


@require("editor")
async def reopen(request: Request, user: dict):
    p = own_project(request, user)
    if not p.get("edl"):
        raise ApiError(400, "अभी कट नहीं बने")
    with db.tx() as c:
        service.set_status(c, p["id"], "review_cuts", "दोबारा review")
    return ok()


@require("editor")
async def restart_prepare(request: Request, user: dict):
    """A project stuck on "जाँच हो रही है" (worker restarted / job lost): drop its open jobs and run the
    file check again from the uploaded recording."""
    p = own_project(request, user)
    if p["status"] != "preparing":
        raise ApiError(409, "यह project अभी 'जाँच' में नहीं है")
    with db.tx() as c:
        c.execute("UPDATE jobs SET status='cancelled', finished_at=? WHERE project_id=? AND kind='prepare' "
                  "AND status IN ('queued','running')", (db.now(), p["id"]))
        job = service.start_pipeline(c, db.get("projects", p["id"]) or p)
        service.log(c, user["workspace_id"], "project.restart_prepare", user_id=user["id"], project_id=p["id"], detail={})
    return ok({"job": job})


@require("viewer")
async def preview_keep(request: Request, user: dict):
    """The kept segments after cuts — the dashboard uses this for a scrub preview."""
    p = own_project(request, user)
    if not p.get("edl"):
        return ok({"keep": []})
    return ok({"keep": autocut.keep_segments(p["edl"])})


async def media(request: Request):
    """Serve a file. Auth is the short-lived token in ?t= (works in <video src>)."""
    aid = request.path_params["asset_id"]
    tok = request.query_params.get("t")
    data = read_token(tok, kind="media") if tok else None
    if not data or data.get("sub") != aid:
        raise ApiError(401, "media link expired")
    a = db.get("assets", aid)
    if not a or a["archived"]:
        raise ApiError(404, "file not found")
    path = storage.abs_path(a["path"])
    if not path.exists():
        raise ApiError(404, "file missing on disk")
    download = request.query_params.get("download")
    name = Path(a["path"]).name
    return FileResponse(path, media_type=a["mime"] or "application/octet-stream",
                        filename=name if download else None)


@require("viewer")
async def presets(request: Request, user: dict):
    from ..engine import dub as dub_eng
    fonts = ["Noto Sans Devanagari", "Poppins", "Baloo 2", "Mukta", "Hind", "Lora", "FreeSerif"]
    return ok({"platforms": list(platforms().values()), "caption_styles": list(caption_styles().values()),
               "fonts": fonts, "looks": [{"id": k, "label": v["label"]} for k, v in LOOKS.items()],
               "extras": [{"id": k, "label": v["label"]} for k, v in EXTRAS.items()],
               "transitions": [{"id": k, "label": v} for k, v in TRANSITIONS.items()],
               "text_anims": [{"id": k, "label": v} for k, v in TEXT_ANIMS.items()],
               "zoom_modes": [{"id": k, "label": v} for k, v in ZOOM_MODES.items()],
               "sticker_anims": [{"id": k, "label": v} for k, v in STICKER_ANIMS.items()],
               "body_bg": [{"id": k, "label": v} for k, v in BODY_BG.items()],
               "body_anims": [{"id": k, "label": v} for k, v in BODY_ANIMS.items()],
               "voice_params": VOICE_PARAMS, "voice_presets": VOICE_PRESETS, "textfx": textfx.presets_json(), "blends": BLENDS, "autopilot": {"defaults": autopilot_eng.AUTOPILOT_DEFAULTS, "labels": autopilot_eng.AUTOPILOT_LABELS},
               "catalog": catalog.catalog_json(),
               "dub": dub_eng.presets_json(),  # AI voice-over: voices / languages / modes
               "pro": procatalog.pro_json(),  # trending / masks / blend modes / keyframes / pro tools — docs/editor-schema.md
               "render_defaults": service.DEFAULT_RENDER, "autocut_defaults": autocut.DEFAULTS})


@require("editor")
async def duplicate(request: Request, user: dict):
    """Copy a project: settings, cuts, transcript, meta and every file (real copies on disk)."""
    import shutil
    from starlette.concurrency import run_in_threadpool
    p = own_project(request, user)
    if p["status"] in ("uploading", "preparing"):
        raise ApiError(400, "upload / जाँच पूरी होने दें, फिर copy करें")
    data = await body(request)
    nid = db.new_id()
    old_dir, new_dir = str(storage.project_dir(p["workspace_id"], p["id"])), str(storage.project_dir(p["workspace_id"], nid))
    assets = db.rows(db.conn().execute("SELECT * FROM assets WHERE project_id = ? AND archived = 0", (p["id"],)))

    def copy_files() -> list[tuple[dict, str]]:
        done = []
        for a in assets:
            src = storage.abs_path(a["path"])
            if not src.exists():
                continue
            rel = a["path"].replace(old_dir, new_dir, 1) if a["path"].startswith(old_dir) else f"{new_dir}/work/{Path(a['path']).name}"
            dst = storage.ensure_parent(rel)
            shutil.copy2(src, dst)
            done.append((a, rel))
        return done

    copied = await run_in_threadpool(copy_files)
    has_out = any(a["kind"] == "render" for a, _ in copied)
    status = p["status"]
    if status in ("transcribing", "cutting", "rendering", "approved", "review_output", "failed"):
        status = "review_output" if has_out and status in ("approved", "review_output") else "review_cuts" if p.get("edl") else "failed"
    idmap: dict[str, str] = {}
    meta = {k: v for k, v in (p.get("meta") or {}).items() if k not in ("archived_at", "publish_plan", "render_after_matte")}
    np_ = {"id": nid, "workspace_id": p["workspace_id"], "created_by": user["id"], "channel_id": p.get("channel_id"),
           "title": (str(data.get("title") or "").strip() or f"{p['title']} (copy)")[:200], "kind": p["kind"], "language": p["language"],
           "status": status, "status_note": "copy — जाँचें और render करें", "meta": meta, "transcript": p.get("transcript"),
           "edl": p.get("edl"), "settings": p.get("settings") or {}, "approved_by": None, "approved_at": None,
           "created_at": db.now(), "updated_at": db.now()}
    with db.tx() as c:
        db.insert(c, "projects", np_)
        for a, rel in copied:
            na = service.add_asset(c, nid, a["kind"], rel, label=a.get("label"), mime=a.get("mime"), meta=a.get("meta"))
            idmap[a["id"]] = na["id"]
        sel = (meta.get("thumbnail") or {})
        if sel:
            db.update(c, "projects", nid, {"meta": {**meta, "thumbnail": {k: idmap.get(v) for k, v in sel.items() if idmap.get(v)}}})
        service.log(c, user["workspace_id"], "project.duplicate", user_id=user["id"], project_id=nid,
                    detail={"title": np_["title"], "from": p["id"], "files": len(copied)})
    return ok(_with_urls(service.project_view(db.get("projects", nid))), 201)


routes = [
    Route("/projects/{project_id}/duplicate", duplicate, methods=["POST"]),
    Route("/projects", list_projects),
    Route("/projects", create_project, methods=["POST"]),
    Route("/projects/{project_id}", get_project),
    Route("/projects/{project_id}", update_project, methods=["PATCH"]),
    Route("/projects/{project_id}", delete_project, methods=["DELETE"]),
    Route("/projects/{project_id}/recut", recut, methods=["POST"]),
    Route("/projects/{project_id}/retranscribe", retranscribe, methods=["POST"]),
    Route("/projects/{project_id}/autopilot/apply", autopilot_apply, methods=["POST"]),
    Route("/projects/{project_id}/autopilot/resume", autopilot_resume, methods=["POST"]),
    Route("/projects/{project_id}/autopilot", autopilot_status),
    Route("/projects/{project_id}/hooks", hook_studio),
    Route("/projects/{project_id}/preflight", preflight),
    Route("/projects/{project_id}/prompts", ai_prompts),
    Route("/projects/{project_id}/aipack", ai_pack),
    Route("/projects/{project_id}/suggest", suggestions),
    Route("/projects/{project_id}/audio-preview", audio_preview, methods=["POST"]),
    Route("/projects/{project_id}/render", render, methods=["POST"]),
    Route("/projects/{project_id}/export-estimate", export_estimate, methods=["POST"]),
    Route("/projects/{project_id}/multiformat", multiformat_analyze, methods=["POST"]),
    Route("/system/encoders", encoders),
    Route("/projects/{project_id}/approve", approve, methods=["POST"]),
    Route("/projects/{project_id}/jobs/{job_id}/cancel", job_cancel, methods=["POST"]),
    Route("/projects/{project_id}/jobs/{job_id}/pause", job_pause, methods=["POST"]),
    Route("/projects/{project_id}/shorts/plan", shorts_plan, methods=["POST"]),
    Route("/projects/{project_id}/montage", montage_render, methods=["POST"]),
    Route("/projects/{project_id}/matte", matte_now, methods=["POST"]),
    Route("/projects/{project_id}/matte_lib", matte_lib_now, methods=["POST"]),
    Route("/projects/{project_id}/frame", preview_frame, methods=["POST"]),
    Route("/projects/{project_id}/archive", archive_now, methods=["POST"]),
    Route("/projects/{project_id}/history", history_list),
    Route("/projects/{project_id}/history/{hid}/restore", history_restore, methods=["POST"]),
    Route("/projects/{project_id}/restore", restore_now, methods=["POST"]),
    Route("/projects/{project_id}/shorts/render", shorts_render, methods=["POST"]),
    Route("/projects/{project_id}/reopen", reopen, methods=["POST"]),
    Route("/projects/{project_id}/restart", restart_prepare, methods=["POST"]),
    Route("/projects/{project_id}/keep", preview_keep),
    Route("/media/{asset_id}", media),
    Route("/presets", presets),
]
