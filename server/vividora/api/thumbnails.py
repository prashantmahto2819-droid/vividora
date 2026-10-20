"""Thumbnail studio API.

GET    /thumbnails/templates                         templates, fonts, styles (for the gallery)
GET    /projects/{id}/thumbnails                     saved thumbnails + selected + best frames
GET    /projects/{id}/thumbnails/frames?refresh=1    best-frame timestamps
GET    /projects/{id}/thumbnails/frame?t=&w=         one still (JPEG)
POST   /projects/{id}/thumbnails/preview             {settings} → JPEG (lint in X-Thumb-Lint header)
POST   /projects/{id}/thumbnails/layers              {settings, have} → background + one sprite per layer (direct editing)
POST   /projects/{id}/thumbnails/lint                {settings} → {warnings, info}
POST   /projects/{id}/thumbnails/text                AI / heuristic thumbnail texts
POST   /projects/{id}/thumbnails                     {settings, select} → saved asset
POST   /projects/{id}/thumbnails/variants            {n, size, base} → saved A/B candidates
POST   /projects/{id}/thumbnails/{asset_id}/select   mark as the one to publish
DELETE /projects/{id}/thumbnails/{asset_id}
"""

from __future__ import annotations

import json

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from .. import service, thumbs
from ..engine import thumbnail as T
from .deps import ApiError, body, ok, own_project, require


def _has_video(p: dict) -> None:
    if thumbs.source_video(p) is None:
        raise ApiError(400, "पहले वीडियो upload / preview बनने दें")


@require("viewer")
async def templates(request: Request, user: dict):
    return ok({"templates": T.templates_json(), "fonts": list(T.FONTS), "styles": T.STYLES, "bg_types": T.BG_TYPES,
               "shapes": T.SHAPES, "sizes": {k: list(v) for k, v in T.SIZES.items()}, "raqm": T.RAQM,
               "grades": T.GRADES, "overlays": T.OVERLAYS, "shadows": T.SHADOWS, "style_defaults": T.STYLE_DEF,
               "max_stickers": T.MAX_STICKERS, "emoji": any(p.exists() for p in T.EMOJI_FONTS)})


@require("viewer")
async def overview(request: Request, user: dict):
    p = own_project(request, user)
    frames = (p.get("meta") or {}).get("thumb_frames", {}).get("frames") or []
    alpha = service.asset_of(p["id"], "alpha") is not None
    return ok({"saved": thumbs.list_saved(p), "selected": thumbs.selected_map(p), "frames": frames,
               "duration": thumbs.duration(p), "title": p["title"], "has_video": thumbs.source_video(p) is not None,
               "has_alpha": alpha, "brand_logo": bool(thumbs.brand(p).get("logo_id"))})


@require("viewer")
async def frames(request: Request, user: dict):
    p = own_project(request, user)
    _has_video(p)
    fr = await run_in_threadpool(thumbs.best_frames, p, request.query_params.get("refresh") in ("1", "true"))
    return ok({"frames": fr, "duration": thumbs.duration(p)})


@require("viewer")
async def frame(request: Request, user: dict):
    p = own_project(request, user)
    _has_video(p)
    try:
        t = float(request.query_params.get("t") or 0)
        w = int(request.query_params.get("w") or 320)
    except ValueError:
        raise ApiError(422, "t / w संख्या होनी चाहिए")
    try:
        jpg = await run_in_threadpool(thumbs.frame_jpeg, p, t, w)
    except Exception as e:  # noqa: BLE001
        raise ApiError(500, f"frame नहीं निकला: {str(e)[-200:]}")
    return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


async def _render(request: Request, user: dict):
    p = own_project(request, user)
    _has_video(p)
    data = await body(request)
    try:
        return p, await run_in_threadpool(thumbs.render, p, data.get("settings") or data)
    except Exception as e:  # noqa: BLE001
        raise ApiError(500, f"thumbnail नहीं बना: {str(e)[-300:]}")


@require("viewer")
async def preview(request: Request, user: dict):
    _p, (jpg, info, warnings) = await _render(request, user)
    hdr = json.dumps({"warnings": warnings, "info": {k: info.get(k) for k in ("font_px", "contrast", "cutout", "t", "words")}}, ensure_ascii=True)
    return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "no-store", "X-Thumb-Lint": hdr,
                                                           "Access-Control-Expose-Headers": "X-Thumb-Lint"})


@require("viewer")
async def layers(request: Request, user: dict):
    p = own_project(request, user)
    _has_video(p)
    data = await body(request)
    try:
        return ok(await run_in_threadpool(thumbs.render_layers, p, data.get("settings") or {}, data.get("have") or []))
    except Exception as e:  # noqa: BLE001
        raise ApiError(500, f"thumbnail नहीं बना: {str(e)[-300:]}")


@require("viewer")
async def lint(request: Request, user: dict):
    _p, (_jpg, info, warnings) = await _render(request, user)
    return ok({"warnings": warnings, "info": info})


@require("viewer")
async def text(request: Request, user: dict):
    p = own_project(request, user)
    return ok(await run_in_threadpool(thumbs.auto_text, p))


@require("editor")
async def save(request: Request, user: dict):
    p = own_project(request, user)
    _has_video(p)
    data = await body(request)
    try:
        a = await run_in_threadpool(lambda: thumbs.save(p, data.get("settings") or {}, user_id=user["id"], select=bool(data.get("select"))))
    except Exception as e:  # noqa: BLE001
        raise ApiError(500, f"save नहीं हुआ: {str(e)[-300:]}")
    return ok(a, 201)


@require("editor")
async def variants(request: Request, user: dict):
    p = own_project(request, user)
    _has_video(p)
    data = await body(request)
    size = data.get("size") if data.get("size") in T.SIZES else "yt"
    n = max(1, min(6, int(data.get("n") or 3)))
    made = await run_in_threadpool(lambda: thumbs.make_variants(p, n, size, data.get("base") or None, user_id=user["id"]))
    if not made:
        raise ApiError(500, "variants नहीं बने")
    return ok({"made": made, "saved": thumbs.list_saved(service_project(p["id"]))})


def service_project(pid: str) -> dict:
    from .. import db
    return db.get("projects", pid) or {"id": pid, "meta": {}}


@require("editor")
async def select(request: Request, user: dict):
    p = own_project(request, user)
    try:
        sel = thumbs.select(p, request.path_params["asset_id"])
    except ValueError as e:
        raise ApiError(404, str(e))
    return ok({"selected": sel})


@require("editor")
async def delete(request: Request, user: dict):
    p = own_project(request, user)
    try:
        thumbs.delete(p, request.path_params["asset_id"])
    except ValueError as e:
        raise ApiError(404, str(e))
    return ok()


routes = [
    Route("/thumbnails/templates", templates),
    Route("/projects/{project_id}/thumbnails", overview),
    Route("/projects/{project_id}/thumbnails", save, methods=["POST"]),
    Route("/projects/{project_id}/thumbnails/frames", frames),
    Route("/projects/{project_id}/thumbnails/frame", frame),
    Route("/projects/{project_id}/thumbnails/preview", preview, methods=["POST"]),
    Route("/projects/{project_id}/thumbnails/layers", layers, methods=["POST"]),
    Route("/projects/{project_id}/thumbnails/lint", lint, methods=["POST"]),
    Route("/projects/{project_id}/thumbnails/text", text, methods=["POST"]),
    Route("/projects/{project_id}/thumbnails/variants", variants, methods=["POST"]),
    Route("/projects/{project_id}/thumbnails/{asset_id}/select", select, methods=["POST"]),
    Route("/projects/{project_id}/thumbnails/{asset_id}", delete, methods=["DELETE"]),
]
