"""API keys — managed from the dashboard (login session only; an API key cannot create or list keys).

GET    /keys          this workspace's active keys (never the secret)
POST   /keys          {name, role?: viewer|editor} → the full key, shown ONCE
DELETE /keys/{id}     revoke
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.routing import Route

from .. import apikeys, db, service
from ..security import ROLE_RANK
from .deps import ApiError, body, ok, require


def _session_only(user: dict) -> None:
    if user.get("_api_key"):
        raise ApiError(403, "API key बनाना/हटाना सिर्फ़ dashboard login से हो सकता है")


@require("editor")
async def list_keys(request: Request, user: dict):
    _session_only(user)
    return ok({"keys": apikeys.list_for(user["workspace_id"])})


@require("editor")
async def create_key(request: Request, user: dict):
    _session_only(user)
    b = await body(request)
    name = str(b.get("name") or "").strip()[:60]
    if not name:
        raise ApiError(422, "key का नाम लिखें (जैसे: n8n, my-app)")
    role = b.get("role") or "editor"
    if role not in ("viewer", "editor"):
        raise ApiError(422, "role viewer या editor होना चाहिए")
    if ROLE_RANK[role] > ROLE_RANK[user["role"]]:
        role = user["role"]
    if apikeys.count(user["workspace_id"]) >= apikeys.MAX_KEYS:
        raise ApiError(409, f"अधिकतम {apikeys.MAX_KEYS} keys — पुरानी हटाएँ")
    key, rec = apikeys.create(user["workspace_id"], user["id"], name, role)
    with db.tx() as c:
        service.log(c, user["workspace_id"], "apikey.create", user_id=user["id"], detail={"name": name, "role": role})
    return ok({"key": key, "info": rec, "note": "इस key को अभी कॉपी कर लें — दोबारा नहीं दिखेगी"}, 201)


@require("editor")
async def revoke_key(request: Request, user: dict):
    _session_only(user)
    if not apikeys.revoke(user["workspace_id"], request.path_params["key_id"]):
        raise ApiError(404, "key नहीं मिली")
    with db.tx() as c:
        service.log(c, user["workspace_id"], "apikey.revoke", user_id=user["id"], detail={"id": request.path_params["key_id"]})
    return ok()


routes = [
    Route("/keys", list_keys),
    Route("/keys", create_key, methods=["POST"]),
    Route("/keys/{key_id}", revoke_key, methods=["DELETE"]),
]
