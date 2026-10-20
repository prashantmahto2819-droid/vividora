from __future__ import annotations

from starlette.requests import Request
from starlette.routing import Route

from .. import db, service
from ..security import ROLES, access_token, hash_password, verify_password
from .deps import ApiError, body, need, ok, require


def public_user(u: dict) -> dict:
    return {k: u[k] for k in ("id", "email", "name", "role", "active", "created_at", "last_login_at")}


async def login(request: Request):
    data = await body(request)
    need(data, "email", "password")
    user = db.row(db.conn().execute("SELECT * FROM users WHERE email = ?",
                                    (data["email"].strip().lower(),)).fetchone())
    if not user or not user["active"] or not verify_password(data["password"], user["password_hash"]):
        raise ApiError(401, "email या password गलत है")
    with db.tx() as c:
        db.update(c, "users", user["id"], {"last_login_at": db.now()})
        service.log(c, user["workspace_id"], "login", user_id=user["id"])
    ws = db.get("workspaces", user["workspace_id"])
    resp = ok({"token": access_token(user["id"]), "user": public_user(user),
               "workspace": {"id": ws["id"], "name": ws["name"]}})
    resp.set_cookie("vividora_token", access_token(user["id"]), httponly=True, samesite="lax",
                    max_age=72 * 3600, path="/")
    return resp


async def logout(request: Request):
    resp = ok()
    resp.delete_cookie("vividora_token", path="/")
    return resp


@require("viewer")
async def me(request: Request, user: dict):
    ws = db.get("workspaces", user["workspace_id"])
    return ok({"user": public_user(user), "workspace": {"id": ws["id"], "name": ws["name"],
                                                         "settings": ws["settings"]}})


@require("viewer")
async def change_password(request: Request, user: dict):
    data = await body(request)
    need(data, "current", "new")
    if not verify_password(data["current"], user["password_hash"]):
        raise ApiError(400, "मौजूदा password गलत है")
    if len(data["new"]) < 8:
        raise ApiError(422, "नया password कम से कम 8 अक्षर का हो")
    with db.tx() as c:
        db.update(c, "users", user["id"], {"password_hash": hash_password(data["new"])})
    return ok()


@require("admin")
async def list_users(request: Request, user: dict):
    us = db.rows(db.conn().execute("SELECT * FROM users WHERE workspace_id = ? ORDER BY created_at",
                                   (user["workspace_id"],)))
    return ok([public_user(u) for u in us])


@require("admin")
async def create_user(request: Request, user: dict):
    data = await body(request)
    need(data, "email", "name", "password")
    role = data.get("role", "editor")
    if role not in ROLES:
        raise ApiError(422, "role: admin / editor / viewer")
    if len(data["password"]) < 8:
        raise ApiError(422, "password कम से कम 8 अक्षर का हो")
    email = data["email"].strip().lower()
    if db.conn().execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        raise ApiError(409, "यह email पहले से है")
    u = {"id": db.new_id(), "workspace_id": user["workspace_id"], "email": email,
         "name": data["name"].strip(), "password_hash": hash_password(data["password"]),
         "role": role, "active": True, "created_at": db.now(), "last_login_at": None}
    with db.tx() as c:
        db.insert(c, "users", u)
        service.log(c, user["workspace_id"], "user.create", user_id=user["id"],
                    detail={"email": email, "role": role})
    return ok(public_user(u), 201)


@require("admin")
async def update_user(request: Request, user: dict):
    target = db.get("users", request.path_params["user_id"])
    if not target or target["workspace_id"] != user["workspace_id"]:
        raise ApiError(404, "user not found")
    data = await body(request)
    changes: dict = {}
    if "role" in data:
        if data["role"] not in ROLES:
            raise ApiError(422, "bad role")
        changes["role"] = data["role"]
    if "active" in data:
        changes["active"] = bool(data["active"])
    if "name" in data and data["name"].strip():
        changes["name"] = data["name"].strip()
    if data.get("password"):
        if len(data["password"]) < 8:
            raise ApiError(422, "password कम से कम 8 अक्षर का हो")
        changes["password_hash"] = hash_password(data["password"])
    if target["id"] == user["id"] and (changes.get("role") not in (None, "admin") or changes.get("active") is False):
        raise ApiError(400, "आप खुद को admin से नहीं हटा सकते")
    with db.tx() as c:
        db.update(c, "users", target["id"], changes)
        service.log(c, user["workspace_id"], "user.update", user_id=user["id"],
                    detail={"target": target["email"], **{k: v for k, v in changes.items() if k != 'password_hash'}})
    return ok(public_user(db.get("users", target["id"])))


@require("viewer")
async def brand_get(request: Request, user: dict):
    from .channels import get_channel
    ch = get_channel(user["workspace_id"], request.query_params.get("channel"))
    return ok(((ch or {}).get("settings") or {}).get("brand", {}))


@require("admin")
async def brand_set(request: Request, user: dict):
    data = await body(request)
    keys = ("name", "logo_id", "primary", "highlight", "font", "caption_style", "grade_preset", "music", "watermark_pos", "hashtags", "cta", "vocab_words", "voice_preset", "cta_popup")
    brand = {k: data[k] for k in keys if k in data}
    from .channels import get_channel
    ch = get_channel(user["workspace_id"], data.get("channel_id") or request.query_params.get("channel"))
    if not ch:
        raise ApiError(404, "channel not found")
    st = ch.get("settings") or {}
    with db.tx() as c:
        db.update(c, "channels", ch["id"], {"settings": {**st, "brand": {**st.get("brand", {}), **brand}}, "updated_at": db.now()})
        service.log(c, user["workspace_id"], "brand.update", user_id=user["id"], detail={"channel": ch["id"], "fields": list(brand)})
    return ok(brand)


routes = [
    Route("/brand", brand_get),
    Route("/brand", brand_set, methods=["PUT"]),
    Route("/auth/login", login, methods=["POST"]),
    Route("/auth/logout", logout, methods=["POST"]),
    Route("/auth/me", me),
    Route("/auth/password", change_password, methods=["POST"]),
    Route("/users", list_users),
    Route("/users", create_user, methods=["POST"]),
    Route("/users/{user_id}", update_user, methods=["PATCH"]),
]
