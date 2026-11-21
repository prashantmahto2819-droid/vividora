"""Rig a Library 3D model on a cloud GPU (UniRig) → a rigged .glb saved next to it.

POST /rig        {library_id, template?: mixamo|vroid|articulationxl, name?}  → 202 {job_id}
GET  /rig/{id}   → {status, message, error, item}
GET  /rig/health → {configured}
"""

from __future__ import annotations

import logging
import tempfile
import threading
import time
import uuid
from pathlib import Path

from starlette.requests import Request
from starlette.routing import Route

from .. import db, service, storage
from .deps import ApiError, body, ok, require

log = logging.getLogger("vividora.api.rig")
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


def _run(job_id: str, ws: str, user_id: str, src: Path, name: str, template: str):
    from ..engine import unirig
    from .library import _add_file, _view
    st = _JOBS[job_id]
    try:
        st.update(message="GPU worker को भेज रहे हैं…")
        data = unirig.rig(src.read_bytes(), template, on_status=lambda s: st.update(message={"IN_QUEUE": "GPU की कतार में (cold start में 1–3 मिनट)", "IN_PROGRESS": "GPU पर rigging चल रही है"}.get(s, str(s))))
        with tempfile.TemporaryDirectory(prefix="rig_") as td:
            out = Path(td) / "rigged.glb"
            out.write_bytes(data)
            item = _add_file(ws, user_id, "3d_model", out, name=f"{name} (rigged)"[:120], tags="3d,glb,rigged", source="unirig",
                             license="UniRig output — model का license आपके original पर निर्भर", analyse=False)
        with db.tx() as c:
            service.log(c, ws, "rig.done", user_id=user_id, detail={"item_id": item["id"], "template": template})
        st.update(status="done", message="तैयार", item=_view(item), finished=time.time())
    except Exception as e:  # noqa: BLE001 — shown to the user
        log.warning("rig failed: %s", e)
        st.update(status="failed", error=(str(e) or e.__class__.__name__)[:300], finished=time.time())
    from .. import webhooks
    webhooks.notify(st, job_id, "rig")


@require("viewer")
async def health(request: Request, user: dict):
    from ..engine import unirig
    return ok({"configured": unirig.configured(), "templates": list(unirig.TEMPLATES)})


@require("editor")
async def start(request: Request, user: dict):
    from ..engine import unirig
    b = await body(request)
    if not unirig.configured():
        raise ApiError(409, "cloud GPU rigging सेट नहीं है — .env में UNIRIG_ENDPOINT_ID और RUNPOD_API_KEY डालें (gpu-worker/unirig/README.md)")
    item = db.get("library", str(b.get("library_id") or ""))
    if not item or item["workspace_id"] != user["workspace_id"] or item["kind"] != "3d_model":
        raise ApiError(404, "3D model Library में नहीं मिला")
    template = str(b.get("template") or "mixamo")
    if template not in unirig.TEMPLATES:
        raise ApiError(422, "template: " + " | ".join(unirig.TEMPLATES))
    src = storage.abs_path(item["path"])
    if src.stat().st_size > unirig.MAX_INPUT:
        raise ApiError(413, f"model बहुत बड़ा (max {unirig.MAX_INPUT // 1048576} MB)")
    ws = user["workspace_id"]
    with _LOCK:
        for k in [k for k, j in _JOBS.items() if j.get("finished") and time.time() - j["finished"] > 3600]:
            _JOBS.pop(k, None)
        if any(j["status"] == "running" and j["ws"] == ws for j in _JOBS.values()):
            raise ApiError(429, "एक rigging अभी चल रही है — ख़त्म होने दें")
        job_id = uuid.uuid4().hex[:16]
        _JOBS[job_id] = {"status": "running", "ws": ws, "started": time.time(), "message": "शुरू", "callback": None}
    name = str(b.get("name") or item["name"])[:100]
    threading.Thread(target=_run, args=(job_id, ws, user["id"], src, name, template), daemon=True).start()
    return ok({"job_id": job_id}, 202)


@require("viewer")
async def status(request: Request, user: dict):
    st = _JOBS.get(request.path_params["job_id"])
    if not st or st["ws"] != user["workspace_id"]:
        raise ApiError(404, "job नहीं मिला (server restart के बाद Library देखें)")
    return ok({"status": st["status"], "message": st.get("message"), "error": st.get("error"), "item": st.get("item"),
               "seconds": int((st.get("finished") or time.time()) - st["started"])})


routes = [
    Route("/rig/health", health),
    Route("/rig", start, methods=["POST"]),
    Route("/rig/{job_id}", status),
]
