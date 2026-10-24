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
    effects = ((p.get("settings") or {}).get("render") or {}).get("effects") or {}
    try:
        pl = await run_in_threadpool(dub.plan, p, mode=mode, language=data.get("language"),
                                     script=str(data.get("script") or ""), effects=effects)
        voice = dub.resolve_voice(data.get("voice"), data.get("description"), pl["language"])
    except ValueError as e:
        raise ApiError(422, str(e))
    from .. import saas
    from ..engine import tts as _tts
    saas.check_voice(p["workspace_id"], _tts.is_premium(voice))
    payload = {**pl, "voice": voice, "speed": speed}
    with db.tx() as c:
        job = queue.enqueue(c, p["id"], "dub", payload)
        db.update(c, "projects", p["id"], {"status_note": f"AI voice-over बन रहा है ({len(pl['segments'])} lines, {voice.get('label', '')})",
                                           "updated_at": db.now()})
        service.log(c, user["workspace_id"], "dub.start", user_id=user["id"], project_id=p["id"],
                    detail={"mode": mode, "language": pl["language"], "voice": voice.get("id"), "lines": len(pl["segments"])})
    return ok({"job": {k: v for k, v in job.items() if k != "payload"}, "lines": len(pl["segments"]),
               "language": pl["language"], "translated": [s.get("text") for s in pl["segments"][:3]] if mode == "dub" else None})


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
]
