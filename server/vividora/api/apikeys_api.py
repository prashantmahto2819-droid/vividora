"""API keys — let another platform (e.g. the AI App Builder) use Vividora's models over HTTP.

POST   /keys        {name, scopes?: ["tts","3d"]} → {key (shown ONCE), id, prefix, scopes}   (admin, login only)
GET    /keys        → keys of this workspace (prefix, scopes, last use) — never the key itself
DELETE /keys/{id}   → revoke

A key sends `Authorization: Bearer vvk_…` and can only call the endpoints listed in security.API_SCOPES
(voice-over / VoiceStudio for "tts", image→3D for "3d"). It can never manage keys, billing, the library or users.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.routing import Route

from .. import db, service
from ..security import API_SCOPES, new_api_key
from .deps import ApiError, body, ok, require

MAX_KEYS = 20


@require("admin")
async def create(request: Request, user: dict):
    b = await body(request)
    name = str(b.get("name") or "").strip()[:60]
    if not name:
        raise ApiError(422, "key ka naam likhein")
    scopes = b.get("scopes") or list(API_SCOPES)
    if not isinstance(scopes, list) or not scopes or any(s not in API_SCOPES for s in scopes):
        raise ApiError(422, "scopes: " + ", ".join(API_SCOPES))
    ws = user["workspace_id"]
    n = db.conn().execute("SELECT COUNT(*) FROM api_keys WHERE workspace_id = ? AND revoked_at IS NULL", (ws,)).fetchone()[0]
    if n >= MAX_KEYS:
        raise ApiError(429, f"max {MAX_KEYS} active keys")
    key, prefix, h = new_api_key()
    rec = {"id": db.new_id(), "workspace_id": ws, "user_id": user["id"], "name": name, "prefix": prefix, "key_hash": h,
           "scopes": ",".join(dict.fromkeys(scopes)), "created_at": db.now()}
    with db.tx() as c:
        db.insert(c, "api_keys", rec)
        service.log(c, ws, "apikey.create", user_id=user["id"], detail={"id": rec["id"], "name": name, "scopes": rec["scopes"]})
    return ok({"key": key, "id": rec["id"], "prefix": prefix, "scopes": rec["scopes"].split(","),
               "note": "yeh key ab dobara nahi dikhegi — abhi copy karein"}, 201)


@require("admin")
async def listing(request: Request, user: dict):
    rows = db.rows(db.conn().execute("SELECT id, name, prefix, scopes, created_at, last_used_at, revoked_at FROM api_keys "
                                     "WHERE workspace_id = ? ORDER BY created_at DESC", (user["workspace_id"],)))
    return ok({"keys": [{**r, "scopes": r["scopes"].split(",")} for r in rows]})


@require("admin")
async def revoke(request: Request, user: dict):
    k = db.get("api_keys", request.path_params["key_id"])
    if not k or k["workspace_id"] != user["workspace_id"]:
        raise ApiError(404, "key nahi mili")
    with db.tx() as c:
        db.update(c, "api_keys", k["id"], {"revoked_at": db.now()})
        service.log(c, user["workspace_id"], "apikey.revoke", user_id=user["id"], detail={"id": k["id"]})
    return ok()


routes = [
    Route("/keys", create, methods=["POST"]),
    Route("/keys", listing),
    Route("/keys/{key_id}", revoke, methods=["DELETE"]),
]
