"""Optional 2-step verification (authenticator app, TOTP) + one-time recovery codes.

GET  /auth/2fa                   → {enabled, recovery_left}
POST /auth/2fa/setup   {password}        → {secret, uri}      (not active yet)
POST /auth/2fa/enable  {code}            → session + {recovery_codes} (shown once)
POST /auth/2fa/login   {challenge, code} → session   (code = 6-digit app code OR a recovery code)
POST /auth/2fa/disable {password, code}  → session
POST /auth/2fa/recovery {password, code} → {recovery_codes} (new set, old ones die)
POST /users/{id}/2fa-reset  (admin)      → turns 2FA off for a user who lost the phone and the codes
"""

from __future__ import annotations

import json

from starlette.requests import Request
from starlette.routing import Route

from .. import crypto, db, saas, service
from ..engine import totp
from ..security import read_token, verify_password
from .auth import _session, public_user
from .deps import ApiError, body, client_ip, need, ok, rate_limit, require


def _secret(u: dict, col: str = "totp_secret") -> str | None:
    v = crypto.decrypt_json(u.get(col)) if u.get(col) else None
    return (v or {}).get("s") if isinstance(v, dict) else None


def _recovery(u: dict) -> list[str]:
    try:
        return list(json.loads(u.get("totp_recovery") or "[]"))
    except ValueError:
        return []


def _check(u: dict, code: str, *, spend: bool = True) -> bool:
    """6-digit app code (replay-safe) or a recovery code (single use). Records the new state when spend=True."""
    sec = _secret(u)
    if not sec:
        return False
    counter = totp.verify(sec, code, last_counter=int(u.get("totp_last") or 0))
    if counter is not None:
        if spend:
            with db.tx() as c:
                db.update(c, "users", u["id"], {"totp_last": counter})
        return True
    h = totp.hash_recovery(code or "")
    rec = _recovery(u)
    if h in rec:
        if spend:
            rec.remove(h)
            with db.tx() as c:
                db.update(c, "users", u["id"], {"totp_recovery": json.dumps(rec)})
        return True
    return False


def _gate(request: Request, user_id: str) -> str:
    rate_limit(request, "2fa", 10, 10)
    key = f"2fa|{user_id}"
    left = saas.login_blocked(key)
    if left:
        raise ApiError(429, f"बहुत ग़लत code — {max(1, left // 60)} मिनट बाद फिर कोशिश करें")
    return key


@require("viewer")
async def status(request: Request, user: dict):
    return ok({"enabled": bool(user.get("totp_secret")), "recovery_left": len(_recovery(user))})


@require("viewer")
async def setup(request: Request, user: dict):
    rate_limit(request, "2fa-mgmt", 10, 10)
    data = await body(request)
    need(data, "password")
    if not verify_password(data["password"], user["password_hash"]):
        raise ApiError(400, "password गलत है")
    if user.get("totp_secret"):
        raise ApiError(409, "2-step verification पहले से चालू है")
    sec = totp.new_secret()
    with db.tx() as c:
        db.update(c, "users", user["id"], {"totp_pending": crypto.encrypt_json({"s": sec})})
    return ok({"secret": sec, "uri": totp.otpauth_uri(sec, user["email"])})


@require("viewer")
async def enable(request: Request, user: dict):
    key = _gate(request, user["id"])
    data = await body(request)
    need(data, "code")
    sec = _secret(user, "totp_pending")
    if not sec:
        raise ApiError(409, "पहले setup शुरू करें")
    counter = totp.verify(sec, data["code"])
    if counter is None:
        saas.login_failed(key)
        raise ApiError(400, "code ग़लत है — authenticator app में अभी का 6 अंकों का code डालें")
    saas.login_ok(key)
    codes = totp.new_recovery_codes()
    with db.tx() as c:
        db.update(c, "users", user["id"], {"totp_secret": crypto.encrypt_json({"s": sec}), "totp_pending": None, "totp_last": counter,
                                           "totp_recovery": json.dumps([totp.hash_recovery(x) for x in codes]),
                                           "token_version": int(user.get("token_version") or 0) + 1})  # other devices sign in again with the code
        service.log(c, user["workspace_id"], "2fa.enabled", user_id=user["id"])
    return _session(db.get("users", user["id"]), {"recovery_codes": codes})


async def login_step(request: Request):
    data = await body(request)
    need(data, "challenge", "code")
    t = read_token(str(data["challenge"]), kind="2fa")
    u = db.get("users", t["sub"]) if t else None
    if not u or not u["active"] or not u.get("totp_secret"):
        raise ApiError(401, "समय ख़त्म — password से फिर login करें")
    key = _gate(request, u["id"])
    if not _check(u, str(data["code"])):
        saas.login_failed(key)
        raise ApiError(401, "code ग़लत है")
    saas.login_ok(key)
    saas.login_ok(f"{u['email']}|{client_ip(request)}")
    with db.tx() as c:
        db.update(c, "users", u["id"], {"last_login_at": db.now()})
        service.log(c, u["workspace_id"], "login", user_id=u["id"], detail={"ip": client_ip(request), "2fa": True})
    return _session(db.get("users", u["id"]))


@require("viewer")
async def disable(request: Request, user: dict):
    key = _gate(request, user["id"])
    data = await body(request)
    need(data, "password", "code")
    if not verify_password(data["password"], user["password_hash"]):
        raise ApiError(400, "password गलत है")
    if not _check(user, str(data["code"])):
        saas.login_failed(key)
        raise ApiError(400, "code ग़लत है")
    with db.tx() as c:
        db.update(c, "users", user["id"], {"totp_secret": None, "totp_pending": None, "totp_recovery": None, "totp_last": 0,
                                           "token_version": int(user.get("token_version") or 0) + 1})
        service.log(c, user["workspace_id"], "2fa.disabled", user_id=user["id"])
    return _session(db.get("users", user["id"]))


@require("viewer")
async def new_recovery(request: Request, user: dict):
    key = _gate(request, user["id"])
    data = await body(request)
    need(data, "password", "code")
    if not verify_password(data["password"], user["password_hash"]) or not _check(user, str(data["code"])):
        saas.login_failed(key)
        raise ApiError(400, "password या code ग़लत है")
    codes = totp.new_recovery_codes()
    with db.tx() as c:
        db.update(c, "users", user["id"], {"totp_recovery": json.dumps([totp.hash_recovery(x) for x in codes])})
    return ok({"recovery_codes": codes})


@require("admin")
async def admin_reset(request: Request, user: dict):
    """The user lost the phone AND the recovery codes: an admin of the same workspace switches 2FA off (they must set it up again)."""
    target = db.get("users", request.path_params["user_id"])
    if not target or target["workspace_id"] != user["workspace_id"]:
        raise ApiError(404, "user नहीं मिला")
    if target["id"] == user["id"]:
        raise ApiError(422, "अपना 2FA ऊपर के 'बंद करें' से हटाएँ")
    with db.tx() as c:
        db.update(c, "users", target["id"], {"totp_secret": None, "totp_pending": None, "totp_recovery": None, "totp_last": 0,
                                             "token_version": int(target.get("token_version") or 0) + 1})
        service.log(c, user["workspace_id"], "2fa.admin_reset", user_id=user["id"], detail={"target": target["id"]})
    return ok({"user": public_user(db.get("users", target["id"]))})


routes = [
    Route("/auth/2fa", status),
    Route("/auth/2fa/setup", setup, methods=["POST"]),
    Route("/auth/2fa/enable", enable, methods=["POST"]),
    Route("/auth/2fa/login", login_step, methods=["POST"]),
    Route("/auth/2fa/disable", disable, methods=["POST"]),
    Route("/auth/2fa/recovery", new_recovery, methods=["POST"]),
    Route("/users/{user_id}/2fa-reset", admin_reset, methods=["POST"]),
]
