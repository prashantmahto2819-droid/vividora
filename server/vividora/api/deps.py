"""Request helpers: JSON bodies, auth, roles, errors."""

from __future__ import annotations

import json
from functools import wraps
from typing import Any

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

from .. import db
from ..security import ROLE_RANK, read_token, worker_token_ok


class ApiError(HTTPException):
    def __init__(self, status: int, message: str, **extra: Any):
        super().__init__(status_code=status, detail=message)
        self.extra = extra


def ok(data: Any = None, status: int = 200) -> JSONResponse:
    return JSONResponse(data if data is not None else {"ok": True}, status_code=status)


_MAX_BODY = 2 * 1024 * 1024  # 2 MB — generous for any JSON API payload


async def body(request: Request) -> dict:
    cl = int(request.headers.get("content-length", "0"))
    if cl > _MAX_BODY:
        raise ApiError(413, f"request body बहुत बड़ा है (max {_MAX_BODY // (1024 * 1024)} MB)")
    try:
        raw = await request.body()
        if len(raw) > _MAX_BODY:
            raise ApiError(413, f"request body बहुत बड़ा है (max {_MAX_BODY // (1024 * 1024)} MB)")
        data = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        raise ApiError(400, "invalid JSON")
    if not isinstance(data, dict):
        raise ApiError(400, "JSON object expected")
    return data


def need(data: dict, *keys: str) -> None:
    missing = [k for k in keys if data.get(k) in (None, "")]
    if missing:
        raise ApiError(422, f"missing: {', '.join(missing)}")


def _bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get("vividora_token")


def current_user(request: Request) -> dict:
    tok = _bearer(request)
    data = read_token(tok, kind="access") if tok else None
    if not data:
        raise ApiError(401, "login required")
    user = db.get("users", data["sub"])
    if not user or not user["active"]:
        raise ApiError(401, "account disabled")
    if int(data.get("tv", 0)) != int(user.get("token_version") or 0):
        raise ApiError(401, "session खत्म — फिर login करें")
    return user


def client_ip(request: Request) -> str:
    # behind the Cloudflare tunnel the real address is in CF-Connecting-IP
    return (request.headers.get("cf-connecting-ip") or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
            or (request.client.host if request.client else "?"))


def rate_limit(request: Request, bucket: str, per_minute: int, burst: int | None = None) -> None:
    """Per-IP token bucket; raises 429 in Hindi. Always on (cheap, in-memory)."""
    from .. import saas
    if not saas.rate_ok(f"{bucket}:{client_ip(request)}", per_minute, burst):
        raise ApiError(429, "बहुत जल्दी-जल्दी कोशिश — एक मिनट रुककर फिर करें")


def require(role: str = "viewer"):
    """Decorator: the handler receives `user` as a keyword argument."""

    def deco(fn):
        @wraps(fn)
        async def wrapper(request: Request, *a, **kw):
            user = current_user(request)
            if ROLE_RANK[user["role"]] < ROLE_RANK[role]:
                raise ApiError(403, f"{role} की अनुमति चाहिए")
            from .. import saas
            saas.set_workspace(user["workspace_id"])  # AI credits are counted against this workspace
            try:
                return await fn(request, *a, user=user, **kw)
            except saas.QuotaError as e:
                raise ApiError(402, str(e), quota=e.code)
            finally:
                saas.set_workspace(None)

        return wrapper

    return deco


def require_worker(fn):
    @wraps(fn)
    async def wrapper(request: Request, *a, **kw):
        tok = request.headers.get("x-worker-token") or _bearer(request)
        if not worker_token_ok(tok):
            raise ApiError(401, "worker token invalid")
        return await fn(request, *a, **kw)

    return wrapper


def own_project(request: Request, user: dict) -> dict:
    p = db.get("projects", request.path_params["project_id"])
    if not p or p["workspace_id"] != user["workspace_id"]:
        raise ApiError(404, "project not found")
    return p


async def error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    payload = {"error": exc.detail}
    if isinstance(exc, ApiError) and exc.extra:
        payload.update(exc.extra)
    return JSONResponse(payload, status_code=exc.status_code)
