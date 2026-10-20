"""Disk space page: what uses the server's disk, and one-click cleanup."""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.routing import Route

from .. import cleanup, db, service
from .deps import body, ok, require


@require("admin")
async def storage_usage(request: Request, user: dict):
    return ok(await run_in_threadpool(cleanup.usage, user["workspace_id"]))


@require("admin")
async def storage_clean(request: Request, user: dict):
    data = await body(request)
    what = [w for w in (data.get("what") or []) if w in ("orphans", "uploads", "cache", "sources", "renders")]
    days = int(data.get("days", 7))
    r = await run_in_threadpool(cleanup.clean, user["workspace_id"], what, days)
    with db.tx() as c:
        service.log(c, user["workspace_id"], "storage.clean", user_id=user["id"], detail={"what": what, "days": days, "freed": r["freed"]})
    return ok(r)


routes = [
    Route("/storage", storage_usage),
    Route("/storage/clean", storage_clean, methods=["POST"]),
]
