"""One-click themes: list built-in + saved themes, apply one to a project (chosen parts only),
save a project's current settings as a reusable theme, delete a saved theme."""

from __future__ import annotations

from starlette.requests import Request
from starlette.routing import Route

from .. import db, service
from ..autopilot_flow import channel_and_library, skipped as transcript_skipped
from ..engine import themes
from .deps import ApiError, body, ok, own_project, require


@require("viewer")
async def list_themes(request: Request, user: dict):
    return ok({"themes": themes.listing(user["workspace_id"]), "parts": [{"id": p, "label": l} for p, l in themes.PARTS]})


@require("editor")
async def apply_theme(request: Request, user: dict):
    p = own_project(request, user)
    data = await body(request)
    t = themes.get(str(data.get("id") or ""), user["workspace_id"])
    if not t:
        raise ApiError(404, "theme नहीं मिला")
    parts = data.get("parts") if isinstance(data.get("parts"), list) else None
    has_tr = bool(((p.get("transcript") or {}).get("segments") or [])) and not transcript_skipped(p)
    _, lib = channel_and_library(p)
    st = dict(p.get("settings") or {})
    rs, applied, skipped = themes.apply(st.get("render") or service.DEFAULT_RENDER, t, parts, has_transcript=has_tr,
                                        library=lib, seed=p["id"])
    st["render"] = rs
    if p.get("kind") == "montage" and "montage" in applied:
        mo = dict(st.get("montage") or {})
        mo.update({k: v for k, v in themes.montage_opts(t).items() if k in ("pace", "effects_level", "look", "slowmo", "font", "text_color", "text_size")})
        mo["theme"] = t["id"]
        st["montage"] = mo
    with db.tx() as c:
        db.update(c, "projects", p["id"], {"settings": st, "updated_at": db.now()})
        service.log(c, user["workspace_id"], "theme.apply", user_id=user["id"], project_id=p["id"], detail={"theme": t["id"], "parts": applied})
    return ok({"applied": applied, "skipped": skipped, "settings": st, "theme": {"id": t["id"], "label": t.get("label")}})


@require("editor")
async def save_theme(request: Request, user: dict):
    data = await body(request)
    name = str(data.get("name") or "").strip()
    if not name:
        raise ApiError(422, "theme का नाम लिखें")
    src = None
    if data.get("project_id"):
        src = db.get("projects", str(data["project_id"]))
        if not src or src["workspace_id"] != user["workspace_id"]:
            raise ApiError(404, "project नहीं मिला")
    base = themes.get(str(data.get("from_theme") or ""), user["workspace_id"]) if data.get("from_theme") else None
    payload = themes.from_project(src, name) if src else dict(base or {})
    if isinstance(data.get("theme"), dict):  # explicit edits from the UI win
        payload.update({k: v for k, v in data["theme"].items() if k not in ("id", "builtin", "saved")})
    with db.tx() as c:
        t = themes.save(c, user["workspace_id"], name, payload, user_id=user["id"],
                        theme_id=str(data["id"]) if data.get("id") and not themes.builtin().get(str(data["id"])) else None)
        service.log(c, user["workspace_id"], "theme.save", user_id=user["id"], detail={"theme": t["id"]})
    return ok({"theme": themes._public(t)})


@require("editor")
async def delete_theme(request: Request, user: dict):
    tid = request.path_params["theme_id"]
    if tid in themes.builtin():
        raise ApiError(400, "built-in theme नहीं हटता")
    row = db.get("themes", tid)
    if not row or row["workspace_id"] != user["workspace_id"]:
        raise ApiError(404, "theme नहीं मिला")
    with db.tx() as c:
        c.execute("DELETE FROM themes WHERE id = ?", (tid,))
    return ok({"deleted": tid})


@require("editor")
async def analyze_ref(request: Request, user: dict):
    """Theme Analyzer: {library_id} or {asset_id} (a video of this project / the library) → measured numbers,
    guessed mapping and an editable theme; {save: "name"} stores it as a saved theme right away.
    Only parameters are taken from the reference — nothing of it is copied."""
    from starlette.concurrency import run_in_threadpool
    from .. import storage
    from ..engine import refanalyze
    p = own_project(request, user)
    data = await body(request)
    src = None
    if data.get("library_id"):
        it = db.get("library", str(data["library_id"]))
        if not it or it["workspace_id"] != user["workspace_id"] or it["kind"] not in ("broll", "music"):
            raise ApiError(404, "library की video नहीं मिली")
        src = it["path"]
    elif data.get("asset_id"):
        a = db.get("assets", str(data["asset_id"]))
        if not a or a["project_id"] != p["id"] or a["kind"] not in ("raw", "proxy", "render", "clip"):
            raise ApiError(404, "video नहीं मिली")
        src = a["path"]
    else:
        src = (service.asset_of(p["id"], "proxy") or service.asset_of(p["id"], "raw") or {}).get("path")
    if not src:
        raise ApiError(422, "reference video चुनें (library की clip या इस project की video)")
    try:
        res = await run_in_threadpool(refanalyze.analyze, storage.abs_path(src))
    except ValueError as e:
        raise ApiError(422, str(e))
    except Exception as e:  # noqa: BLE001 — a missing/unreadable file is the user's problem to see, not a 500
        raise ApiError(422, f"reference video पढ़ी नहीं गई: {str(e)[:160]}")
    if data.get("save"):
        with db.tx() as c:
            t = themes.save(c, user["workspace_id"], str(data["save"])[:60], res["theme"], user_id=user["id"])
            service.log(c, user["workspace_id"], "theme.from_ref", user_id=user["id"], detail={"theme": t["id"]})
        res["saved"] = themes._public(t)
    return ok(res)


routes = [
    Route("/presets/themes", list_themes),
    Route("/projects/{project_id}/analyze-ref", analyze_ref, methods=["POST"]),
    Route("/projects/{project_id}/theme", apply_theme, methods=["POST"]),
    Route("/themes", save_theme, methods=["POST"]),
    Route("/themes/{theme_id}", delete_theme, methods=["DELETE"]),
]
