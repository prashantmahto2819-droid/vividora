"""Outside-service keys from the dashboard (provkeys.py). The server's owner only: the admin of the operator workspace,
with a dashboard login (an API key can never read or change these).

GET    /providers            [{env, label, group, use, link, set, source, shown (masked), …}]  + can_edit
PUT    /providers/{env}      {value}
DELETE /providers/{env}      back to the .env value (or empty)
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.routing import Route

from .. import db, provkeys, service
from ..config import settings
from .deps import ApiError, body, ok, require


def _operator(user: dict) -> bool:
    if user.get("_api_key") or user.get("role") != "admin":
        return False
    op = settings.operator_workspace or db.conn().execute("SELECT id FROM workspaces ORDER BY created_at LIMIT 1").fetchone()[0]
    return user["workspace_id"] == op


@require("editor")
async def list_providers(request: Request, user: dict):
    can = _operator(user)
    rows = provkeys.status()
    if not can:      # others only see what is available, never a value (not even masked)
        rows = [{**r, "shown": "", "updated_at": None} for r in rows]
    return ok({"providers": rows, "groups": provkeys.GROUPS, "can_edit": can})


@require("admin")
async def put_provider(request: Request, user: dict):
    if not _operator(user):
        raise ApiError(403, "ये keys सिर्फ़ server के मालिक (पहले workspace के admin) dashboard login से बदल सकते हैं")
    env = request.path_params["env"]
    try:
        provkeys.set_key(env, (await body(request)).get("value"), user["id"])
    except ValueError as e:
        raise ApiError(422, str(e))
    with db.tx() as c:
        service.log(c, user["workspace_id"], "provider_key.set", user_id=user["id"], detail={"env": env})
    return ok({"provider": next(r for r in provkeys.status() if r["env"] == env)})


@require("admin")
async def delete_provider(request: Request, user: dict):
    if not _operator(user):
        raise ApiError(403, "ये keys सिर्फ़ server के मालिक (पहले workspace के admin) dashboard login से बदल सकते हैं")
    env = request.path_params["env"]
    try:
        provkeys.clear_key(env)
    except ValueError as e:
        raise ApiError(422, str(e))
    with db.tx() as c:
        service.log(c, user["workspace_id"], "provider_key.clear", user_id=user["id"], detail={"env": env})
    return ok({"provider": next(r for r in provkeys.status() if r["env"] == env)})


@require("editor")
async def spend_summary(request: Request, user: dict):
    """This month's paid-service spending. The log itself only for the server's owner."""
    from .. import spend
    s = spend.summary()
    if not _operator(user):
        s = {k: s[k] for k in ("period", "cap", "total", "left")}
    return ok({**s, "can_edit": _operator(user)})


routes = [
    Route("/spend", spend_summary),
    Route("/providers", list_providers),
    Route("/providers/{env}", put_provider, methods=["PUT"]),
    Route("/providers/{env}", delete_provider, methods=["DELETE"]),
]
