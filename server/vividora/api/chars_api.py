"""Character Studio + Scene builder API.

  GET  /chars                         library (200 built-in + this workspace's saved ones) + options
  GET  /chars/{id}/preview.png        one frame (query: pose JSON, expr, viseme, w, h)
  GET  /chars/{id}/sheet.png?clip=    frames of a pose clip
  GET  /chars/{id}/clip.webm?clip=&dur=  animated transparent clip (preview)
  POST /chars/render                  {params, pose} → svg (customiser, live)
  POST /chars                         save a custom character {name, params, base}
  DELETE /chars/{id}
  GET  /scenes/envs                   environments, props, clips, expressions
  POST /scenes/render                 {scene spec, w, h} → svg (storyboard preview)
  GET/POST/DELETE /storyboards        saved storyboards
  POST /storyboards/build             {storyboard, title?, auto_render?, project_id?} → project + job
"""

from __future__ import annotations

import json
import urllib.parse

from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.routing import Route

from .. import db, service
from ..engine.chars import anim, catalog, render, rig, scenes2d
from ..engine.chars import storyboard as sb
from ..engine import tts
from .deps import ApiError, body, ok, require


def _custom(workspace_id: str) -> list[dict]:
    rows = db.rows(db.conn().execute("SELECT * FROM characters WHERE workspace_id = ? ORDER BY created_at DESC", (workspace_id,)))
    out = []
    for r in rows:
        m = r.get("meta") or {}
        out.append({"id": r["id"], "name": r["name"], "label": r["name"], "profession": m.get("profession") or "", "category": m.get("category") or "custom",
                    "params": {**catalog.DEFAULT_PARAMS, **(m.get("params") or {})}, "custom": True, "base": r.get("base")})
    return out


def _find(workspace_id: str, cid: str) -> dict | None:
    p = catalog.get(cid)
    if p:
        return p
    r = db.get("characters", cid)
    if r and r["workspace_id"] == workspace_id:
        m = r.get("meta") or {}
        return {"id": r["id"], "name": r["name"], "label": r["name"], "params": {**catalog.DEFAULT_PARAMS, **(m.get("params") or {})}, "custom": True}
    return None


def _char_from_query(request: Request, user: dict) -> dict:
    c = _find(user["workspace_id"], request.path_params["char_id"])
    if not c:
        raise ApiError(404, "character नहीं मिला")
    return c


def _pose_from_query(q) -> dict:
    pose: dict = {}
    if q.get("pose"):
        try:
            pose = json.loads(q["pose"])
        except ValueError:
            raise ApiError(422, "pose JSON ठीक नहीं")
    for k in ("expr", "viseme"):
        if q.get(k):
            pose[k] = q[k]
    if q.get("mouth_open"):
        pose["mouth_open"] = float(q["mouth_open"])
    if q.get("flip"):
        pose["flip"] = 1
    if q.get("clip") and q["clip"] in anim.CLIPS:
        pose = {**anim.compose(float(q.get("t") or 0.6), q["clip"]), **pose}
    return pose


@require("viewer")
async def list_chars(request: Request, user: dict):
    return ok({"library": catalog.library(), "custom": _custom(user["workspace_id"]), "options": catalog.options(),
               "clips": anim.clip_list(), "voices": [{k: v.get(k) for k in ("id", "label", "lang", "gender", "engine", "cloud")} for v in tts.available_voices()]})


@require("viewer")
async def preview_png(request: Request, user: dict):
    c = _char_from_query(request, user)
    q = request.query_params
    w, h = int(q.get("w") or 300), int(q.get("h") or 600)
    if not (40 <= w <= 1200 and 40 <= h <= 2400):
        raise ApiError(422, "size 40–1200 px")
    try:
        p = render.preview_png(c["params"], _pose_from_query(q), w, h)
    except ValueError as e:
        raise ApiError(422, str(e))
    return FileResponse(str(p), media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


@require("viewer")
async def sheet_png(request: Request, user: dict):
    c = _char_from_query(request, user)
    clip = request.query_params.get("clip") or "idle"
    if clip not in anim.CLIPS:
        raise ApiError(422, "clip नहीं है")
    p = render.sheet_png(c["params"], clip)
    return FileResponse(str(p), media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


@require("viewer")
async def clip_webm(request: Request, user: dict):
    c = _char_from_query(request, user)
    q = request.query_params
    clip = q.get("clip") or "idle"
    if clip not in anim.CLIPS:
        raise ApiError(422, "clip नहीं है")
    dur = min(8.0, max(0.5, float(q.get("dur") or 3.0)))
    spec = {"dur": dur, "base": clip if clip in ("walk", "run", "sit", "drive", "dance1", "dance2") else "idle",
            "gesture": clip, "expr": q.get("expr") or "neutral", "seed": 1, "flip": bool(q.get("flip"))}
    if q.get("say"):
        words = tts.word_times(q["say"], 0.3, min(dur - 0.2, 0.3 + len(q["say"]) / 14.0))
        spec["lip"] = {"words": words, "wav": None, "wav_sig": q["say"]}
    p = render.clip_webm(c["params"], spec, 360, 720)
    return FileResponse(str(p), media_type="video/webm", headers={"Cache-Control": "private, max-age=86400"})


@require("viewer")
async def render_svg(request: Request, user: dict):
    data = await body(request)
    try:
        s = rig.svg(data.get("params") or {}, data.get("pose") or {}, width=int(data.get("w") or 400), height=int(data.get("h") or 800))
    except ValueError as e:
        raise ApiError(422, str(e))
    return Response(s, media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@require("editor")
async def save_char(request: Request, user: dict):
    data = await body(request)
    try:
        params = rig.validate(data.get("params") or {})
    except ValueError as e:
        raise ApiError(422, str(e))
    name = str(data.get("name") or params.get("name") or "मेरा character").strip()[:80]
    cid = data.get("id") if data.get("id") and db.get("characters", data["id"]) else db.new_id()
    row = {"id": cid, "workspace_id": user["workspace_id"], "name": name, "base": str(data.get("base") or "")[:20],
           "meta": {"params": {**params, "name": name}, "profession": str(data.get("profession") or params.get("profession") or "")[:60],
                    "category": str(data.get("category") or "custom")[:30]},
           "created_by": user["id"], "created_at": db.now(), "updated_at": db.now()}
    with db.tx() as c:
        if db.get("characters", cid):
            db.update(c, "characters", cid, {k: row[k] for k in ("name", "base", "meta", "updated_at")})
        else:
            db.insert(c, "characters", row)
    return ok(_find(user["workspace_id"], cid), 201)


@require("editor")
async def delete_char(request: Request, user: dict):
    r = db.get("characters", request.path_params["char_id"])
    if not r or r["workspace_id"] != user["workspace_id"]:
        raise ApiError(404, "सिर्फ़ अपने बनाए character हटाए जा सकते हैं")
    with db.tx() as c:
        c.execute("DELETE FROM characters WHERE id = ?", (r["id"],))
    return ok()


@require("viewer")
async def envs(request: Request, user: dict):
    return ok({"envs": scenes2d.env_list(), "props": scenes2d.PROPS, "framing": list(scenes2d.FRAMING), "light": list(scenes2d.LIGHT),
               "clips": anim.clip_list(), "expressions": catalog.EXPRESSIONS, "presets": list(sb.PRESET_SIZE)})


def _resolve_chars(workspace_id: str, scene: dict) -> dict:
    out = dict(scene)
    chars = []
    for ch in scene.get("chars") or []:
        params = ch.get("params")
        if not params and ch.get("profile"):
            c = _find(workspace_id, ch["profile"])
            if not c:
                raise ApiError(422, f"character {ch['profile']} नहीं मिला")
            params = c["params"]
        chars.append({**ch, "params": params or catalog.DEFAULT_PARAMS})
    out["chars"] = chars
    return out


@require("viewer")
async def render_scene(request: Request, user: dict):
    data = await body(request)
    w, h = int(data.get("w") or 960), int(data.get("h") or 540)
    try:
        s = scenes2d.scene_svg(_resolve_chars(user["workspace_id"], data.get("scene") or {}), w, h, with_chars=data.get("chars", True) is not False)
    except ValueError as e:
        raise ApiError(422, str(e))
    return Response(s, media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@require("viewer")
async def list_storyboards(request: Request, user: dict):
    rows = db.rows(db.conn().execute("SELECT * FROM storyboards WHERE workspace_id = ? ORDER BY updated_at DESC LIMIT 100", (user["workspace_id"],)))
    return ok([{"id": r["id"], "name": r["name"], "project_id": r.get("project_id"), "updated_at": r["updated_at"],
                "scenes": len(((r.get("meta") or {}).get("spec") or {}).get("scenes") or []), "spec": (r.get("meta") or {}).get("spec")} for r in rows])


@require("editor")
async def save_storyboard(request: Request, user: dict):
    data = await body(request)
    spec = data.get("spec") or data.get("storyboard") or {}
    name = str(data.get("name") or spec.get("title") or "Storyboard").strip()[:120]
    sid = data.get("id") if data.get("id") and db.get("storyboards", data["id"]) else db.new_id()
    with db.tx() as c:
        if db.get("storyboards", sid):
            db.update(c, "storyboards", sid, {"name": name, "meta": {"spec": spec}, "updated_at": db.now()})
        else:
            db.insert(c, "storyboards", {"id": sid, "workspace_id": user["workspace_id"], "name": name, "meta": {"spec": spec},
                                         "project_id": None, "created_by": user["id"], "created_at": db.now(), "updated_at": db.now()})
    return ok({"id": sid, "name": name}, 201)


@require("editor")
async def delete_storyboard(request: Request, user: dict):
    r = db.get("storyboards", request.path_params["sb_id"])
    if not r or r["workspace_id"] != user["workspace_id"]:
        raise ApiError(404, "storyboard नहीं मिला")
    with db.tx() as c:
        c.execute("DELETE FROM storyboards WHERE id = ?", (r["id"],))
    return ok()


@require("editor")
async def build(request: Request, user: dict):
    """Storyboard → a new project (or an existing explainer project re-built) + the explainer job."""
    data = await body(request)
    spec = dict(data.get("storyboard") or data.get("spec") or {})
    # profiles saved in this workspace resolve here; the worker only sees params
    for sc in spec.get("scenes") or []:
        for ch in sc.get("chars") or []:
            if not ch.get("params") and ch.get("profile"):
                c = _find(user["workspace_id"], ch["profile"])
                if not c:
                    raise ApiError(422, f"character {ch['profile']} नहीं मिला")
                ch["params"] = c["params"]
                ch.setdefault("name", c.get("name"))
    title = str(data.get("title") or spec.get("title") or "Explainer").strip()[:200]
    spec["title"] = title
    try:
        sb.normalise(spec)
    except ValueError as e:
        raise ApiError(422, str(e))
    with db.tx() as c:
        if data.get("project_id"):
            p = db.get("projects", data["project_id"])
            if not p or p["workspace_id"] != user["workspace_id"]:
                raise ApiError(404, "project नहीं मिला")
        else:
            from .projects import new_project_row
            p = new_project_row(user, {"title": title, "language": spec.get("language") or "hi", "kind": "explainer",
                                       "channel_id": data.get("channel_id"), "theme_id": spec.get("theme_id")})
            db.insert(c, "projects", p)
        try:
            job = service.request_explainer(c, p, spec, auto_render=bool(data.get("auto_render")))
        except ValueError as e:
            raise ApiError(422, str(e))
        if data.get("storyboard_id") and db.get("storyboards", data["storyboard_id"]):
            db.update(c, "storyboards", data["storyboard_id"], {"project_id": p["id"], "meta": {"spec": spec}, "updated_at": db.now()})
        service.log(c, user["workspace_id"], "explainer.build", user_id=user["id"], project_id=p["id"], detail={"title": title})
    return ok({"project_id": p["id"], "job": job}, 201)


routes = [
    Route("/chars", list_chars),
    Route("/chars", save_char, methods=["POST"]),
    Route("/chars/render", render_svg, methods=["POST"]),
    Route("/chars/{char_id}/preview.png", preview_png),
    Route("/chars/{char_id}/sheet.png", sheet_png),
    Route("/chars/{char_id}/clip.webm", clip_webm),
    Route("/chars/{char_id}", delete_char, methods=["DELETE"]),
    Route("/scenes/envs", envs),
    Route("/scenes/render", render_scene, methods=["POST"]),
    Route("/storyboards", list_storyboards),
    Route("/storyboards", save_storyboard, methods=["POST"]),
    Route("/storyboards/build", build, methods=["POST"]),
    Route("/storyboards/{sb_id}", delete_storyboard, methods=["DELETE"]),
]
