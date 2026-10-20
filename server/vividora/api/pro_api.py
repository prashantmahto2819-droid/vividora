"""Pro editing endpoints (contract: docs/editor-schema.md).

POST /api/projects/{id}/textcut      text-based editing (delete / restore words, fillers, silences)
GET  /api/projects/{id}/textcut      words with their removed/kept state
POST /api/projects/{id}/scenes       scene changes of the recording or a library clip
POST /api/projects/{id}/color/match  colour-match params for a clip from a reference frame
POST /api/projects/{id}/music/fit    remix plan for a library song to a target length
GET  /api/pro/catalog                the pro catalogs (same as presets.pro)
"""

from __future__ import annotations

from pathlib import Path

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.routing import Route

from .. import db, service, storage
from ..engine import procatalog
from .deps import ApiError, body, ok, own_project, require


def _project_video(p: dict) -> Path:
    a = service.asset_of(p["id"], "proxy") or service.asset_of(p["id"], "raw")
    if not a:
        raise ApiError(400, "recording नहीं मिली")
    return storage.abs_path(a["path"])


def _library_file(user: dict, item_id: str) -> Path:
    it = db.get("library", item_id or "")
    if not it or it["workspace_id"] != user["workspace_id"]:
        raise ApiError(404, "library item not found")
    p = storage.abs_path(it["path"])
    if not p.exists():
        raise ApiError(404, "file missing on disk")
    return p


def _source(p: dict, user: dict, spec: dict | None) -> tuple[Path, float]:
    """{"kind": "project"} (default) or {"kind": "library", "id": …}, plus "t" seconds."""
    spec = spec or {}
    t = max(0.0, float(spec.get("t") or 0))
    if spec.get("kind") == "library" or spec.get("id"):
        return _library_file(user, spec.get("id")), t
    return _project_video(p), t


def _save_edl(p: dict, user: dict, edl: dict, note: str) -> None:
    with db.tx() as c:
        last = db.row(c.execute("SELECT created_at FROM history WHERE project_id = ? ORDER BY id DESC LIMIT 1", (p["id"],)).fetchone())
        if not (last and db.now()[:16] == last["created_at"][:16]):
            db.insert(c, "history", {"project_id": p["id"], "user_id": user["id"], "note": note, "settings": p["settings"],
                                     "edl": p.get("edl"), "meta": {"shorts": (p.get("meta") or {}).get("shorts")},
                                     "created_at": db.now()})
        db.update(c, "projects", p["id"], {"edl": edl, "updated_at": db.now()})
        service.log(c, user["workspace_id"], "project.textcut", user_id=user["id"], project_id=p["id"], detail={"note": note})


@require("viewer")
async def textcut_state(request: Request, user: dict):
    from ..engine import textedit
    from ..engine.autocut import words_of
    p = own_project(request, user)
    words = words_of(p.get("transcript") or {})
    edl = {"duration": float((p.get("meta") or {}).get("duration") or 0), "cuts": [], **(p.get("edl") or {})}
    gone = set(textedit.removed_words(edl, words))
    return ok({"words": [{"i": i, "w": w["w"], "start": w["start"], "end": w["end"], "removed": i in gone} for i, w in enumerate(words)]})


@require("editor")
async def textcut(request: Request, user: dict):
    from ..engine import textedit
    p = own_project(request, user)
    if not p.get("transcript"):
        raise ApiError(400, "पहले transcript बनने दें")
    data = await body(request)
    edl = {"duration": float((p.get("meta") or {}).get("duration") or 0), "cuts": [], **(p.get("edl") or {})}
    try:
        res = textedit.apply(edl, p["transcript"], data)
    except (TypeError, ValueError) as e:
        raise ApiError(422, f"गलत input: {e}") from None
    if not data.get("dry_run"):
        _save_edl(p, user, res["edl"], data.get("note") or "text edit")
    return ok(res)


@require("viewer")
async def scenes(request: Request, user: dict):
    from ..engine import scenes as sc
    p = own_project(request, user)
    data = await body(request)
    path, _ = _source(p, user, data.get("source"))
    end = data.get("end")
    found = await run_in_threadpool(sc.detect, path, float(data.get("threshold", 0.3) or 0.3), float(data.get("start") or 0),
                                    float(end) if end not in (None, "") else None, float(data.get("min_gap", 0.6) or 0.6))
    return ok({"scenes": found, "markers": [{"t": s["t"], "label": f"Scene {i + 2}", "kind": "note"} for i, s in enumerate(found)]})


@require("viewer")
async def color_match(request: Request, user: dict):
    from ..engine import colorpro
    p = own_project(request, user)
    data = await body(request)
    if not data.get("ref"):
        raise ApiError(422, "ref (reference clip/frame) चाहिए")
    src_path, src_t = _source(p, user, data.get("clip"))
    ref_path, ref_t = _source(p, user, data.get("ref"))

    def work():
        a = colorpro.frame_rgb(src_path, src_t)
        b = colorpro.frame_rgb(ref_path, ref_t)
        return colorpro.match(a, b, float(data.get("amount", 1.0) or 1.0), bool(data.get("keep_luma")))
    try:
        res = await run_in_threadpool(work)
    except Exception as e:  # noqa: BLE001
        raise ApiError(500, f"frame नहीं पढ़ा गया: {str(e)[-200:]}") from None
    return ok({"color": res, "hint": "इसे clip के color (या effects.pro.color) में merge करें"})


@require("viewer")
async def music_fit(request: Request, user: dict):
    from ..engine import musicfit
    from ..engine.render import out_timeline
    p = own_project(request, user)
    data = await body(request)
    path = _library_file(user, data.get("music_id") or "")
    target = data.get("target")
    if target in (None, ""):
        rs = {**service.DEFAULT_RENDER, **(p.get("settings") or {}).get("render", {})}
        edl = {"duration": float((p.get("meta") or {}).get("duration") or 0), "cuts": [], **(p.get("edl") or {})}
        _, target = out_timeline(edl, float((p.get("meta") or {}).get("fps") or 30), rs.get("effects"))
    try:
        plan = await run_in_threadpool(musicfit.plan, path, float(target))
    except Exception as e:  # noqa: BLE001
        raise ApiError(422, f"music fit नहीं बना: {str(e)[-200:]}") from None
    return ok({"plan": plan, "hint": "render में लगाने के लिए effects.music.fit = true"})


@require("viewer")
async def pro_catalog(request: Request, user: dict):
    return ok(procatalog.pro_json())


routes = [
    Route("/projects/{project_id}/textcut", textcut_state),
    Route("/projects/{project_id}/textcut", textcut, methods=["POST"]),
    Route("/projects/{project_id}/scenes", scenes, methods=["POST"]),
    Route("/projects/{project_id}/color/match", color_match, methods=["POST"]),
    Route("/projects/{project_id}/music/fit", music_fit, methods=["POST"]),
    Route("/pro/catalog", pro_catalog),
]
