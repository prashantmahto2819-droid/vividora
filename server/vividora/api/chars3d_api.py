"""3D Studio API — procedural characters (60 profiles), animations, scenes, lip-synced clips, 3D explainers.

GET  /chars3d                      catalogue (profiles, animations, scenes, lighting, cameras, expressions)
GET  /chars3d/preview/{profile}.png cached poster render of a profile (first frame, transparent)
GET  /chars3d/jobs                 this workspace's 3D jobs (char3d + storyboard3d)
POST /chars3d/render               {profile|spec, animation, lines[], seconds, …} → job char3d → library item (alpha webm)
POST /chars3d/jobs/{id}/cancel
POST /chars3d/storyboard           {title, scenes[]} → job storyboard3d → a new project with the explainer as its recording
"""

from __future__ import annotations

from pathlib import Path

from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.routing import Route

from .. import config, db, queue, service
from ..engine import chars3d as c3
from .deps import ApiError, body, ok, require
from .library import _view

KINDS = ("char3d", "storyboard3d")


def _page_url() -> str:
    return (config.settings.public_url if hasattr(config.settings, "public_url") and config.settings.public_url else "http://127.0.0.1:8000") + "/assets/3d.html"


@require("viewer")
async def catalogue(request: Request, user: dict):
    cat = c3.catalogue()
    cat["voices"] = [{"id": v["id"], "label": v["label"], "lang": v["lang"], "gender": v["gender"]} for v in __import__("vividora.engine.tts", fromlist=["x"]).VOICE_PRESETS]
    return ok(cat)


async def preview(request: Request):
    """<img> tags carry no Authorization header: the access token may come as ?t= (same token the app holds)."""
    from .deps import current_user
    from ..security import read_token
    try:
        current_user(request)
    except ApiError:
        data = read_token(request.query_params.get("t", ""), kind="access") if request.query_params.get("t") else None
        if not data or not db.get("users", data["sub"]):
            raise ApiError(401, "login required")
    pid = request.path_params["profile"]
    prof = c3.BY_ID.get(pid)
    if not prof:
        raise ApiError(404, "profile नहीं")
    cache = Path(config.settings.data_root) / "cache" / "chars3d"
    cache.mkdir(parents=True, exist_ok=True)
    key = c3.spec_hash({"v": 2, **prof["spec"]})
    png = cache / f"{pid}_{key}.png"
    if not png.exists():
        work = cache / f"_{pid}"
        try:
            spec = {"width": 360, "height": 480, "fps": 1, "duration": 1, "transparent": True, "camera": {"preset": "medium"},
                    "characters": [{"spec": prof["spec"], "animation": "idle", "expression": "smile", "expressionAmount": 0.5}]}
            import os
            r = c3.render_frames(spec, work, page_url=os.getenv("CHARS3D_PAGE_URL") or f"http://127.0.0.1:{request.url.port or 8000}/assets/3d.html")
            (work / f"00001.{r['ext']}").replace(png)
        except Exception as e:  # noqa: BLE001 — no browser on this box: a 1×1 transparent png, the UI draws the live preview itself
            png.write_bytes(bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8ffff3f0300050201ff19e5e4090000000049454e44ae426082"))
            return Response(png.read_bytes(), media_type="image/png", headers={"X-Preview-Error": str(e)[:200], "Cache-Control": "no-store"})
        finally:
            import shutil
            shutil.rmtree(work, ignore_errors=True)
    return FileResponse(png, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


def _jobs(workspace_id: str) -> list[dict]:
    cn = db.conn()
    tp = db.row(cn.execute("SELECT id FROM projects WHERE workspace_id = ? AND kind = 'tools' LIMIT 1", (workspace_id,)).fetchone())
    if not tp:
        return []
    jobs = db.rows(cn.execute("SELECT * FROM jobs WHERE project_id = ? AND kind IN ('char3d','storyboard3d') ORDER BY created_at DESC LIMIT 40", (tp["id"],)))
    out = []
    for j in jobs:
        res = j.get("result") or {}
        item = db.get("library", res["library_id"]) if res.get("library_id") else None
        out.append({"id": j["id"], "kind": j["kind"], "status": j["status"], "progress": j.get("progress"), "message": j.get("message"), "error": j.get("error"),
                    "created_at": j["created_at"], "finished_at": j.get("finished_at"), "attempts": j.get("attempts"),
                    "payload": {k: v for k, v in (j.get("payload") or {}).items() if k not in ("user_id",)},
                    "result": {k: v for k, v in res.items() if k != "files"}, "item": _view(item) if item else None,
                    "project_id": res.get("project_id")})
    return out


@require("viewer")
async def jobs(request: Request, user: dict):
    return ok({"jobs": _jobs(user["workspace_id"])})


def _clean_lines(lines) -> list[dict]:
    out = []
    for ln in lines or []:
        if not isinstance(ln, dict):
            continue
        text = str(ln.get("text") or "").strip()[:600]
        if text:
            out.append({"text": text, "voice": str(ln.get("voice") or "")[:40] or None, "speaker": int(ln.get("speaker") or 0),
                        "lang": (ln.get("lang") or None), "speed": float(ln.get("speed") or 1.0)})
    return out[:60]


def _clean_char(c: dict) -> dict:
    spec = c.get("spec") if isinstance(c.get("spec"), dict) else {}
    keep = {k: v for k, v in spec.items() if k in ("height", "build", "age", "gender", "skin", "hair", "hairColor", "outfit", "colors", "props", "beard", "expression", "expressionAmount")}
    return {"profile": c.get("profile") if c.get("profile") in c3.BY_ID else None, "spec": keep, "slot": int(c.get("slot") or 0),
            "animation": c.get("animation") if c.get("animation") in c3.ANIMATIONS else None,
            "talk_animation": c.get("talk_animation") if c.get("talk_animation") in c3.ANIMATIONS else None,
            "expression": c.get("expression") if c.get("expression") in c3.EXPRESSIONS else "smile"}


@require("editor")
async def render(request: Request, user: dict):
    d = await body(request)
    ch = _clean_char(d)
    if not ch["profile"] and not ch["spec"]:
        raise ApiError(422, "character चुनें")
    pl = {"user_id": user["id"], **ch, "name": str(d.get("name") or (c3.BY_ID[ch["profile"]]["name"] if ch["profile"] else "3D character"))[:80],
          "lines": _clean_lines(d.get("lines")), "seconds": min(120.0, max(1.0, float(d.get("seconds") or 5))), "fps": 25,
          "width": int(d.get("width") or 720), "height": int(d.get("height") or 1080), "camera": d.get("camera") if d.get("camera") in c3.CAMERAS else "medium",
          "expression_amount": float(d.get("expression_amount") or 0.5), "speed": float(d.get("speed") or 1.0),
          "scene": d.get("scene") if d.get("scene") in c3.SCENES else None, "lighting": d.get("lighting") if d.get("lighting") in c3.LIGHTING else "day"}
    if pl["width"] * pl["height"] > 2100 * 2100:
        raise ApiError(422, "size बहुत बड़ा")
    with db.tx() as c:
        tp = service.tools_project(c, user["workspace_id"])
        job = queue.enqueue(c, tp["id"], "char3d", pl)
        service.log(c, user["workspace_id"], "chars3d.render", user_id=user["id"], project_id=tp["id"], detail={"profile": ch["profile"], "lines": len(pl["lines"])})
    return ok({"job": job}, 201)


@require("editor")
async def cancel(request: Request, user: dict):
    job = db.get("jobs", request.path_params["job_id"])
    pr = db.get("projects", job["project_id"]) if job else None
    if not job or not pr or pr["workspace_id"] != user["workspace_id"] or job["kind"] not in KINDS:
        raise ApiError(404, "job not found")
    with db.tx() as c:
        if job["status"] in ("queued", "running"):
            db.update(c, "jobs", job["id"], {"status": "cancelled", "finished_at": db.now(), "message": "रद्द"})
    return ok()


@require("editor")
async def from_storyboard(request: Request, user: dict):
    d = await body(request)
    title = str(d.get("title") or "").strip()[:200]
    if not title:
        raise ApiError(422, "title लिखें")
    scenes = []
    for sc in (d.get("scenes") or [])[:20]:
        if not isinstance(sc, dict):
            continue
        chars = [_clean_char(c) for c in (sc.get("characters") or [])[:4] if isinstance(c, dict)]
        scenes.append({"scene": sc.get("scene") if sc.get("scene") in c3.SCENES else "office", "lighting": sc.get("lighting") if sc.get("lighting") in c3.LIGHTING else "day",
                       "camera": sc.get("camera") if sc.get("camera") in c3.CAMERAS else None, "orbit": max(-1.0, min(1.0, float(sc.get("orbit") or 0))),
                       "push": max(0.0, min(2.0, float(sc.get("push") or 0))), "hold": min(60.0, max(0.0, float(sc.get("hold") or 0))),
                       "characters": chars, "lines": _clean_lines(sc.get("lines"))})
    if not scenes:
        raise ApiError(422, "कम से कम एक scene चाहिए")
    pl = {"user_id": user["id"], "title": title, "channel_id": d.get("channel_id"), "language": d.get("language") or "hi", "scenes": scenes,
          "width": 1920 if (d.get("format") or "16:9") == "16:9" else 1080, "height": 1080 if (d.get("format") or "16:9") == "16:9" else 1920, "fps": 25,
          "autopilot": bool(d.get("autopilot", False)), "theme_id": str(d.get("theme_id") or "")[:40]}
    with db.tx() as c:
        tp = service.tools_project(c, user["workspace_id"])
        job = queue.enqueue(c, tp["id"], "storyboard3d", pl)
        service.log(c, user["workspace_id"], "chars3d.storyboard", user_id=user["id"], project_id=tp["id"], detail={"title": title, "scenes": len(scenes)})
    return ok({"job": job}, 201)


routes = [
    Route("/chars3d", catalogue),
    Route("/chars3d/preview/{profile}.png", preview),
    Route("/chars3d/jobs", jobs),
    Route("/chars3d/render", render, methods=["POST"]),
    Route("/chars3d/jobs/{job_id}/cancel", cancel, methods=["POST"]),
    Route("/chars3d/storyboard", from_storyboard, methods=["POST"]),
]
