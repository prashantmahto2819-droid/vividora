from __future__ import annotations

from starlette.requests import Request
from starlette.routing import Route

import secrets as pysecrets

from .. import db, saas, service
from ..config import settings
from ..security import ROLES, access_token, hash_password, password_problem, verify_password
from .deps import ApiError, body, client_ip, need, ok, rate_limit, require


def public_user(u: dict) -> dict:
    return {k: u[k] for k in ("id", "email", "name", "role", "active", "created_at", "last_login_at")}


def _session(user: dict):
    ws = db.get("workspaces", user["workspace_id"])
    tok = access_token(user["id"], user.get("token_version") or 0)
    resp = ok({"token": tok, "user": public_user(user), "workspace": {"id": ws["id"], "name": ws["name"]},
               "saas": saas.enabled()})
    resp.set_cookie("vividora_token", tok, httponly=True, samesite="lax", max_age=72 * 3600, path="/")
    return resp


async def login(request: Request):
    rate_limit(request, "auth", 30, 60)
    data = await body(request)
    need(data, "email", "password")
    email = data["email"].strip().lower()
    key = f"{email}|{client_ip(request)}"
    left = saas.login_blocked(key)
    if left:
        raise ApiError(429, f"5 गलत कोशिशों के बाद login {max(1, left // 60)} मिनट के लिए बंद है")
    user = db.row(db.conn().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone())
    if not user or not user["active"] or not verify_password(data["password"], user["password_hash"]):
        saas.login_failed(key)
        raise ApiError(401, "email या password गलत है")
    if saas.enabled() and not user.get("verified", 1):
        raise ApiError(403, "पहले email verify करें (inbox में link है)", unverified=True)
    saas.login_ok(key)
    with db.tx() as c:
        db.update(c, "users", user["id"], {"last_login_at": db.now()})
        service.log(c, user["workspace_id"], "login", user_id=user["id"], detail={"ip": client_ip(request)})
    return _session(user)


async def signup(request: Request):
    """SAAS_MODE only: email + password (+ optional invite code) → new workspace with a Free trial, or —
    with a workspace invite — a user in that workspace."""
    if not saas.enabled():
        raise ApiError(404, "signup बंद है — admin से account लें")
    rate_limit(request, "signup", 10, 10)
    data = await body(request)
    need(data, "email", "password", "name")
    email = data["email"].strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise ApiError(422, "सही email लिखें")
    prob = password_problem(data["password"])
    if prob:
        raise ApiError(422, prob)
    if db.conn().execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        raise ApiError(409, "यह email पहले से है — login करें")
    code = (data.get("invite") or "").strip()
    inv = db.get("invites", code, key="code") if code else None
    if inv and (inv["uses_left"] <= 0 or (inv["expires_at"] and inv["expires_at"] < db.now())):
        raise ApiError(410, "invite link खत्म हो गया")
    if inv and inv.get("email") and inv["email"].lower() != email:
        raise ApiError(403, "यह invite किसी और email के लिए है")
    if not inv and (settings.invite_only or not settings.signup_open):
        raise ApiError(403, "अभी invite से ही signup होता है")
    verify = pysecrets.token_urlsafe(24)
    with db.tx() as c:
        if inv and inv.get("workspace_id"):
            ws_id, role = inv["workspace_id"], inv["role"]
        else:
            ws = {"id": db.new_id(), "name": (data.get("workspace") or data["name"]).strip()[:80] or "My studio",
                  "settings": {}, "created_at": db.now()}
            db.insert(c, "workspaces", ws)
            ws_id, role = ws["id"], "admin"
            saas.start_trial(c, ws_id)
        u = {"id": db.new_id(), "workspace_id": ws_id, "email": email, "name": data["name"].strip()[:80],
             "password_hash": hash_password(data["password"]), "role": role, "active": True,
             "created_at": db.now(), "last_login_at": None, "token_version": 0,
             # email verification: the token is stored; sending mail is the operator's job (no SMTP wired yet),
             # so accounts start verified unless REQUIRE_EMAIL_VERIFY=1
             "verified": 0 if settings.require_email_verify else 1, "verify_token": verify}
        db.insert(c, "users", u)
        if role == "admin":
            db.update(c, "workspaces", ws_id, {"owner_id": u["id"]})
        if inv:
            db.update(c, "invites", code, {"uses_left": inv["uses_left"] - 1}, key="code")
        service.log(c, ws_id, "signup", user_id=u["id"], detail={"email": email, "invite": bool(inv), "ip": client_ip(request)})
    if not u["verified"]:
        return ok({"verify_needed": True, "message": "account बना — email में आया link खोलकर verify करें"}, 201)
    return _session(u)


async def verify_email(request: Request):
    tok = request.query_params.get("t") or ""
    u = db.row(db.conn().execute("SELECT * FROM users WHERE verify_token = ?", (tok,)).fetchone()) if tok else None
    if not u:
        raise ApiError(404, "verify link गलत या पुराना है")
    with db.tx() as c:
        db.update(c, "users", u["id"], {"verified": 1, "verify_token": None})
    return _session(db.get("users", u["id"]))


@require("viewer")
async def logout_all(request: Request, user: dict):
    """Every token of this user stops working (phone, laptop, shared PC)."""
    with db.tx() as c:
        db.update(c, "users", user["id"], {"token_version": int(user.get("token_version") or 0) + 1})
        service.log(c, user["workspace_id"], "logout_all", user_id=user["id"])
    resp = ok()
    resp.delete_cookie("vividora_token", path="/")
    return resp


@require("admin")
async def make_invite(request: Request, user: dict):
    data = await body(request)
    role = data.get("role", "editor")
    if role not in ROLES:
        raise ApiError(422, "role: admin / editor / viewer")
    inv = {"code": pysecrets.token_urlsafe(12), "workspace_id": user["workspace_id"], "role": role,
           "email": (data.get("email") or "").strip().lower() or None, "created_by": user["id"],
           "uses_left": int(data.get("uses") or 1), "expires_at": data.get("expires_at"), "created_at": db.now()}
    with db.tx() as c:
        db.insert(c, "invites", inv)
    base = settings.public_url or ""
    return ok({**inv, "url": f"{base}/#/signup?invite={inv['code']}"}, 201)


@require("admin")
async def list_invites(request: Request, user: dict):
    return ok(db.rows(db.conn().execute("SELECT * FROM invites WHERE workspace_id = ? ORDER BY created_at DESC", (user["workspace_id"],))))


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
    prob = password_problem(data["new"])
    if prob:
        raise ApiError(422, prob)
    with db.tx() as c:
        db.update(c, "users", user["id"], {"password_hash": hash_password(data["new"]),
                                           "token_version": int(user.get("token_version") or 0) + 1})
    return _session(db.get("users", user["id"]))


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
    prob = password_problem(data["password"])
    if prob:
        raise ApiError(422, prob)
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
    keys = ("name", "logo_id", "primary", "highlight", "font", "caption_style", "grade_preset", "music", "watermark_pos", "hashtags", "cta", "vocab_words", "voice_preset", "cta_popup", "autopilot", "title_style")
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
    Route("/auth/signup", signup, methods=["POST"]),
    Route("/auth/verify", verify_email),
    Route("/auth/logout", logout, methods=["POST"]),
    Route("/auth/logout-all", logout_all, methods=["POST"]),
    Route("/invites", list_invites),
    Route("/invites", make_invite, methods=["POST"]),
    Route("/auth/me", me),
    Route("/auth/password", change_password, methods=["POST"]),
    Route("/users", list_users),
    Route("/users", create_user, methods=["POST"]),
    Route("/users/{user_id}", update_user, methods=["PATCH"]),
]
