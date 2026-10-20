"""POST /api/command {text, project_id?} — the 🎤 / typed command box."""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.routing import Route

from .. import command_exec
from .deps import ApiError, body, ok, require


@require("editor")
async def command(request: Request, user: dict):
    data = await body(request)
    text = str(data.get("text") or "").strip()
    if not text:
        raise ApiError(422, "कुछ बोलें या लिखें")
    r = await run_in_threadpool(command_exec.run, user["workspace_id"], user["id"], text[:500], data.get("project_id"))
    return ok(r)


routes = [Route("/command", command, methods=["POST"])]
