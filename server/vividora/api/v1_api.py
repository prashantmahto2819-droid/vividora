"""Public integration API  /api/v1  — for n8n, Zapier, Make, your own apps and scripts.

Auth:  Authorization: Bearer vk_…   (or header  X-API-Key: vk_…)   — create keys in the dashboard → "API & Integrations".
Every call is limited to the key owner's workspace and role. Long jobs return a job_id; poll GET /v1/jobs/{id}
(or pass callback_url) and download the result with GET /v1/files/{file_id}.
"""

from __future__ import annotations

import time

from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.routing import Route

from .. import __version__, db, storage
from ..config import settings
from . import chars3d_api, sfx_api, triposr_api, voiceover_api
from .deps import ApiError, ok, require


def _file(it: dict | None) -> dict | None:
    if not it:
        return None
    return {"id": it["id"], "name": it["name"], "kind": it["kind"], "mime": it.get("mime"),
            "download": f"/api/v1/files/{it['id']}"}


@require("viewer")
async def me(request: Request, user: dict):
    ws = db.get("workspaces", user["workspace_id"])
    return ok({"user": {"id": user["id"], "email": user["email"], "name": user["name"]}, "role": user["role"],
               "workspace": {"id": ws["id"], "name": ws["name"]}, "via_api_key": bool(user.get("_api_key")), "version": __version__})


@require("viewer")
async def voices(request: Request, user: dict):
    from ..engine import tts
    out = [{"id": v.get("id"), "name": v.get("name"), "lang": v.get("lang"), "engine": v.get("engine"), "gender": v.get("gender")}
           for v in tts.available_voices()]
    return ok({"voices": out})


@require("editor")
async def character_video(request: Request, user: dict):
    """Same body as the 3D Studio: {glb|profile, lines:[{text,voice?}], animation?, camera?, seconds?, width?, height?, scene?, lighting?}"""
    res = await chars3d_api.render(request)
    import json
    d = json.loads(res.body)
    j = d.get("job") or {}
    return ok({"job_id": j.get("id"), "status": j.get("status", "queued")}, 202)


@require("viewer")
async def job(request: Request, user: dict):
    jid = request.path_params["job_id"]
    ws = user["workspace_id"]
    for store, kind in ((triposr_api._JOBS, "image_to_3d"), (voiceover_api._JOBS, "voiceover")):
        st = store.get(jid)
        if st and st["ws"] == ws:
            item = st.get("item")
            return ok({"job_id": jid, "kind": kind, "status": st["status"], "error": st.get("error"),
                       "seconds": int((st.get("finished") or time.time()) - st["started"]),
                       "file": _file(item) if item else None})
    j = db.get("jobs", jid)
    pr = db.get("projects", j["project_id"]) if j else None
    if not j or not pr or pr["workspace_id"] != ws or j["kind"] not in ("char3d", "storyboard3d", "image_to_3d"):
        raise ApiError(404, "job नहीं मिला (server restart के बाद memory वाले jobs नहीं बचते — /v1/files या Library देखें)")
    res = j.get("result") or {}
    item = db.get("library", res["library_id"]) if res.get("library_id") else None
    return ok({"job_id": jid, "kind": j["kind"], "status": j["status"], "progress": j.get("progress"), "message": j.get("message"),
               "error": j.get("error"), "file": _file(item)})


@require("viewer")
async def files(request: Request, user: dict):
    """Download a result file (wav / glb / webm / mp4 …) — authenticated, link never expires."""
    it = db.get("library", request.path_params["file_id"])
    if not it or it["workspace_id"] != user["workspace_id"]:
        raise ApiError(404, "file नहीं मिली")
    p = storage.abs_path(it["path"])
    if not p.exists():
        raise ApiError(404, "file disk पर नहीं है")
    ext = p.suffix or ""
    return FileResponse(p, media_type=it["mime"] or "application/octet-stream",
                        filename=(it["name"] or "file")[:80] + ("" if (it["name"] or "").lower().endswith(ext.lower()) else ext))


# ---------------------------------------------------------------- OpenAPI + docs
_AUTH = [{"bearer": []}]
_JOB_REF = {"description": "Job accepted", "content": {"application/json": {"schema": {"type": "object", "properties": {"job_id": {"type": "string"}}}}}}


def spec() -> dict:
    base = settings.public_url.rstrip("/") if settings.public_url else ""
    return {
        "openapi": "3.0.3",
        "info": {"title": "Vividora API", "version": "1", "description":
                 "Image→3D, text→speech, 3D character videos. Auth: `Authorization: Bearer vk_…`. Long jobs: poll /v1/jobs/{id} or pass callback_url."},
        "servers": [{"url": base + "/api"}] if base else [{"url": "/api"}],
        "components": {"securitySchemes": {"bearer": {"type": "http", "scheme": "bearer", "description": "API key (vk_…) from the dashboard"}}},
        "security": _AUTH,
        "paths": {
            "/v1/me": {"get": {"summary": "Who am I (checks the key)", "responses": {"200": {"description": "OK"}}}},
            "/v1/voices": {"get": {"summary": "Voices usable for text-to-speech / character lines", "responses": {"200": {"description": "OK"}}}},
            "/v1/text-to-speech": {"post": {
                "summary": "Text → speech (WAV, saved in Library)", "requestBody": {"required": True, "content": {"application/json": {"schema": {
                    "type": "object", "required": ["text"], "properties": {
                        "text": {"type": "string", "maxLength": 4000}, "voice": {"type": "string", "description": "id from /v1/voices"},
                        "lang": {"type": "string", "example": "hi"}, "speed": {"type": "number", "minimum": 0.5, "maximum": 2},
                        "name": {"type": "string"}, "callback_url": {"type": "string"}}}}}},
                "responses": {"202": _JOB_REF}}},
            "/v1/image-to-3d": {"post": {
                "summary": "Image → 3D model (.glb). multipart/form-data", "requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {
                    "type": "object", "required": ["file"], "properties": {
                        "file": {"type": "string", "format": "binary"}, "name": {"type": "string"}, "callback_url": {"type": "string"}}}}}},
                "responses": {"202": _JOB_REF}}},
            "/v1/models3d": {
                "get": {"summary": "List your 3D models (.glb)", "responses": {"200": {"description": "OK"}}},
                "post": {"summary": "Upload a ready .glb. multipart/form-data (file, name)", "responses": {"201": {"description": "Created"}}}},
            "/v1/character-video": {"post": {
                "summary": "3D character talking video (transparent webm). Runs on the worker; poll the job.",
                "requestBody": {"required": True, "content": {"application/json": {"schema": {
                    "type": "object", "properties": {
                        "glb": {"type": "string", "description": "id of a 3D model (from /v1/models3d)"},
                        "profile": {"type": "string", "description": "built-in character id (alternative to glb)"},
                        "lines": {"type": "array", "items": {"type": "object", "properties": {"text": {"type": "string"}, "voice": {"type": "string"}}}},
                        "animation": {"type": "string"}, "camera": {"type": "string", "enum": ["full", "medium", "close", "wide"]},
                        "seconds": {"type": "number"}, "width": {"type": "integer"}, "height": {"type": "integer"}}}}}},
                "responses": {"202": _JOB_REF}}},
            "/v1/auto-sfx": {"post": {
                "summary": "Auto sound effects: places whoosh/pop/tick sounds from the timeline events (titles, B-roll, stickers, cuts)",
                "requestBody": {"required": True, "content": {"application/json": {"schema": {
                    "type": "object", "properties": {
                        "project_id": {"type": "string", "description": "use this project's saved effects + cuts"},
                        "effects": {"type": "object", "description": "editor effects (alternative to project_id)"},
                        "duration": {"type": "number", "description": "output length in seconds (needed with effects)"},
                        "cut_times": {"type": "array", "items": {"type": "number"}},
                        "density": {"type": "string", "enum": ["low", "normal", "high"]},
                        "level": {"type": "number", "minimum": 0.3, "maximum": 1.5}}}}}},
                "responses": {"200": {"description": "{sfx:[...], added:n}"}}}},
            "/v1/jobs/{job_id}": {"get": {"summary": "Job status: running | done | failed (+ file when done)",
                                          "parameters": [{"name": "job_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                                          "responses": {"200": {"description": "OK"}}}},
            "/v1/files/{file_id}": {"get": {"summary": "Download a result file (needs the key; link never expires)",
                                            "parameters": [{"name": "file_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                                            "responses": {"200": {"description": "File"}}}},
        },
    }


async def openapi(request: Request):
    return JSONResponse(spec())


_DOCS = """<!doctype html><html lang="hi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vividora API</title><style>
body{font:15px/1.55 system-ui,sans-serif;max-width:860px;margin:0 auto;padding:20px 16px;background:#0f1218;color:#e6e9ef}
h1{margin:.2em 0}h2{margin-top:1.8em;border-bottom:1px solid #2a3140;padding-bottom:.2em}
code,pre{background:#1a2030;border-radius:6px;font:13px ui-monospace,Menlo,monospace}code{padding:1px 5px}pre{padding:12px;overflow:auto}
.m{display:inline-block;min-width:52px;text-align:center;border-radius:4px;padding:1px 6px;font:600 12px monospace;margin-right:8px}
.GET{background:#1f6f43}.POST{background:#9a5b12}a{color:#7fb3ff}.s{color:#9aa4b5}
</style></head><body><h1>Vividora API</h1>
<p class="s">Image→3D · Text→Speech · 3D character video. Machine-readable: <a href="openapi.json">openapi.json</a> (import into Postman / n8n / Swagger).</p>
<h2>Auth</h2><p>Dashboard → <b>API &amp; Integrations</b> mein key banao (<code>vk_…</code>). Har request mein:</p>
<pre>Authorization: Bearer vk_XXXXXXXX</pre>
<h2>Quick start</h2>
<pre># 1) text → speech
curl -X POST __BASE__/api/v1/text-to-speech -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \\
  -d '{"text":"नमस्ते दोस्तों","lang":"hi"}'            # → {"job_id":"…"}
# 2) status (done होने तक दोहराओ)
curl __BASE__/api/v1/jobs/JOB_ID -H "Authorization: Bearer $KEY"   # → {"status":"done","file":{"id":"…","download":"/api/v1/files/…"}}
# 3) download
curl -o voice.wav __BASE__/api/v1/files/FILE_ID -H "Authorization: Bearer $KEY"

# image → 3D (1–3 min)
curl -X POST __BASE__/api/v1/image-to-3d -H "Authorization: Bearer $KEY" -F file=@object.png -F name=chair

# 3D character video (model id from /v1/models3d)
curl -X POST __BASE__/api/v1/character-video -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \\
  -d '{"glb":"MODEL_ID","lines":[{"text":"Hello"}],"camera":"full","seconds":6}'</pre>
<h2>Endpoints</h2>__ROWS__
<h2>Webhook (optional)</h2><p><code>callback_url</code> do (text-to-speech / image-to-3d): kaam khatam hone par Vividora us URL par
<code>{"event":"job.finished","job_id","kind","status","item_id","error"}</code> POST karta hai. Asli detail <code>GET /v1/jobs/{id}</code> se lo
(isi se confirm hota hai ki call asli hai). Private/local addresses allowed nahi.</p>
<h2>Limits &amp; errors</h2><p>120 requests/min per key. <code>401</code> key galat · <code>403</code> role kam · <code>429</code> ek job pehle se chal raha ·
<code>503</code> service band. Ek waqt mein ek 3D / ek voice job.</p></body></html>"""


async def docs(request: Request):
    rows = []
    for path, ops in spec()["paths"].items():
        for method, op in ops.items():
            rows.append(f'<p><span class="m {method.upper()}">{method.upper()}</span><code>/api{path}</code> — {op["summary"]}</p>')
    base = (settings.public_url or "").rstrip("/") or f"{request.url.scheme}://{request.url.netloc}"
    return HTMLResponse(_DOCS.replace("__ROWS__", "".join(rows)).replace("__BASE__", base))


routes = [
    Route("/v1/me", me),
    Route("/v1/voices", voices),
    Route("/v1/text-to-speech", voiceover_api.create, methods=["POST"]),
    Route("/v1/image-to-3d", triposr_api.generate, methods=["POST"]),
    Route("/v1/models3d", triposr_api.models),
    Route("/v1/models3d", triposr_api.import_glb, methods=["POST"]),
    Route("/v1/character-video", character_video, methods=["POST"]),
    Route("/v1/auto-sfx", sfx_api.auto, methods=["POST"]),
    Route("/v1/jobs/{job_id}", job),
    Route("/v1/files/{file_id}", files),
    Route("/v1/openapi.json", openapi),
    Route("/v1/docs", docs),
]
