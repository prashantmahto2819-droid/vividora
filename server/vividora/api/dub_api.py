"""AI voice-over / dubbing: start a `dub` job, remove a dub track.

The plan (lines + timing, and the one-call translation for Dub mode) is made here;
the GPU worker (or the CPU worker with TTS_LOCAL=1) synthesises the voice.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.routing import Route

from .. import db, queue, service, storage
from ..engine import dub
from .deps import ApiError, body, ok, own_project, require


@require("editor")
async def create_dub(request: Request, user: dict):
    from starlette.concurrency import run_in_threadpool
    p = own_project(request, user)
    data = await body(request)
    mode = data.get("mode") or "revoice"
    if p.get("kind") == "montage" and mode != "script":
        raise ApiError(422, "montage में सिर्फ़ “Script से voice-over” चलता है")
    if p["status"] in ("uploading", "preparing", "transcribing", "cutting") and mode != "script":
        raise ApiError(400, "पहले transcript और कट पूरे होने दें")
    try:
        speed = max(0.7, min(1.4, float(data.get("speed") or 1.0)))
    except (TypeError, ValueError):
        speed = 1.0
    busy = db.conn().execute("SELECT COUNT(*) FROM jobs WHERE project_id = ? AND kind = 'dub' AND status IN ('queued','running')",
                             (p["id"],)).fetchone()[0]
    if busy:
        raise ApiError(409, "एक AI voice-over पहले से बन रहा है — उसके पूरा होने दें")
    rs = (p.get("settings") or {}).get("render") or {}
    effects = rs.get("effects") or {}
    try:
        pitch = max(-12.0, min(12.0, float(data.get("pitch") or 0)))
    except (TypeError, ValueError):
        pitch = 0.0
    try:
        pl = await run_in_threadpool(dub.plan, p, mode=mode, language=data.get("language"),
                                     script=str(data.get("script") or ""), effects=effects)
        voice = dub.resolve_voice(data.get("voice"), data.get("description"), pl["language"])
        # ElevenLabs: allow frontend to override voice settings (stability, similarity_boost, style, use_speaker_boost)
        el_overrides = data.get("elevenlabs_settings")
        if el_overrides and isinstance(el_overrides, dict) and voice.get("engine") == "elevenlabs":
            merged = dict(voice.get("elevenlabs_settings") or {})
            for k in ("stability", "similarity_boost", "style"):
                if k in el_overrides:
                    try:
                        merged[k] = max(0.0, min(1.0, float(el_overrides[k])))
                    except (TypeError, ValueError):
                        pass
            if "use_speaker_boost" in el_overrides:
                merged["use_speaker_boost"] = bool(el_overrides["use_speaker_boost"])
            voice["elevenlabs_settings"] = merged
        # dialogue scripts: `Name: …` lines get the voice from the project's cast (settings.render.voice_cast)
        cast = dub.cast_payload(data.get("cast") if data.get("cast") is not None else rs.get("voice_cast"), pl["language"])
    except ValueError as e:
        raise ApiError(422, str(e))
    fixes = dub.fixes_map(data.get("fixes") if data.get("fixes") is not None else rs.get("tts_fixes"))
    found = pl.pop("speakers_found", []) or []
    missing_cast = [n for n in found if n not in cast]
    from .. import saas
    from ..engine import tts as _tts
    saas.check_voice(p["workspace_id"], _tts.is_premium(voice))
    payload = {**pl, "voice": voice, "speed": speed, "pitch": pitch, "fixes": fixes, "speakers": cast}
    with db.tx() as c:
        job = queue.enqueue(c, p["id"], "dub", payload)
        db.update(c, "projects", p["id"], {"status_note": f"AI voice-over बन रहा है ({len(pl['segments'])} lines, {voice.get('label', '')})",
                                           "updated_at": db.now()})
        service.log(c, user["workspace_id"], "dub.start", user_id=user["id"], project_id=p["id"],
                    detail={"mode": mode, "language": pl["language"], "voice": voice.get("id"), "lines": len(pl["segments"])})
    return ok({"job": {k: v for k, v in job.items() if k != "payload"}, "lines": len(pl["segments"]),
               "language": pl["language"], "translated": [s.get("text") for s in pl["segments"][:3]] if mode == "dub" else None,
               "speakers": found, "missing_cast": missing_cast})


@require("editor")
async def redo_lines(request: Request, user: dict):
    """Per-line edits of a finished voice track: {edits:[{i, text?, voice?, description?, pitch?, pause?, redo?}], redo_all?}
    → a new `dub` job that re-speaks only the changed lines (the rest comes from the worker's line cache) and
    replaces this track when done."""
    p = own_project(request, user)
    a = db.get("assets", request.path_params["asset_id"])
    if not a or a["project_id"] != p["id"] or a["kind"] != "dub":
        raise ApiError(404, "voice track नहीं मिला")
    data = await body(request)
    busy = db.conn().execute("SELECT COUNT(*) FROM jobs WHERE project_id = ? AND kind = 'dub' AND status IN ('queued','running')",
                             (p["id"],)).fetchone()[0]
    if busy:
        raise ApiError(409, "एक AI voice-over पहले से बन रहा है — उसके पूरा होने दें")
    try:
        payload = dub.redo_payload(a, list(data.get("edits") or []), redo_all=bool(data.get("redo_all")))
    except ValueError as e:
        raise ApiError(422, str(e))
    rs = (p.get("settings") or {}).get("render") or {}
    payload["fixes"] = dub.fixes_map(rs.get("tts_fixes"))
    with db.tx() as c:
        job = queue.enqueue(c, p["id"], "dub", payload)
        db.update(c, "projects", p["id"], {"status_note": f"voice track की {payload['changed']} line{'s' if payload['changed'] > 1 else ''} फिर बन रही है",
                                           "updated_at": db.now()})
        service.log(c, user["workspace_id"], "dub.redo", user_id=user["id"], project_id=p["id"],
                    detail={"asset": a["id"], "changed": payload["changed"]})
    return ok({"job": {k: v for k, v in job.items() if k != "payload"}, "changed": payload["changed"]})


@require("viewer")
async def dub_lines(request: Request, user: dict):
    """The lines of a voice track (text, timing, speaker, per-line overrides) for the editor's line panel."""
    p = own_project(request, user)
    a = db.get("assets", request.path_params["asset_id"])
    if not a or a["project_id"] != p["id"] or a["kind"] != "dub":
        raise ApiError(404, "voice track नहीं मिला")
    m = a.get("meta") or {}
    return ok({"segments": [{k: v for k, v in s.items() if k != "words"} for s in (m.get("segments") or [])],
               "speakers": m.get("speakers") or {}, "voice": m.get("voice") or {}, "pitch": m.get("pitch", 0),
               "mode": m.get("mode"), "language": m.get("language"), "cached": m.get("cached", 0)})


@require("editor")
async def delete_dub(request: Request, user: dict):
    p = own_project(request, user)
    a = db.get("assets", request.path_params["asset_id"])
    if not a or a["project_id"] != p["id"] or a["kind"] != "dub":
        raise ApiError(404, "dub track नहीं मिला")
    st = p.get("settings") or {}
    rs = dict(st.get("render") or {})
    eff = dict(rs.get("effects") or {})
    with db.tx() as c:
        try:
            storage.abs_path(a["path"]).unlink(missing_ok=True)
        except (ValueError, OSError):
            pass
        c.execute("DELETE FROM assets WHERE id = ?", (a["id"],))
        if eff.get("voice_track") == a["id"]:
            eff["voice_track"] = "original"
            rs["effects"] = eff
            db.update(c, "projects", p["id"], {"settings": {**st, "render": rs}, "updated_at": db.now()})
        service.log(c, user["workspace_id"], "dub.delete", user_id=user["id"], project_id=p["id"], detail={"asset": a["id"]})
    return ok()


routes = [
    Route("/projects/{project_id}/dub", create_dub, methods=["POST"]),
    Route("/projects/{project_id}/dub/{asset_id}", delete_dub, methods=["DELETE"]),
    Route("/projects/{project_id}/dub/{asset_id}/lines", dub_lines, methods=["GET"]),
    Route("/projects/{project_id}/dub/{asset_id}/lines", redo_lines, methods=["POST"]),
]
