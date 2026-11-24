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


@require("editor")
async def guide(request: Request, user: dict):
    """The admin guide (adminguide.py): which job runs where, what every key / switch does, the test order. No secrets in it."""
    from .. import adminguide
    return ok(adminguide.data())


APP_FILES = {"windows": ("Vividora-Setup.exe", ".exe", "application/vnd.microsoft.portable-executable"),
             "android": ("Vividora.apk", ".apk", "application/vnd.android.package-archive")}
APP_MAX = 400 * 1024 * 1024


def _app_path(kind: str):
    from .. import storage
    return storage.abs_path(f"_apps/{APP_FILES[kind][0]}")


async def app_links(request: Request):
    """Public (the home page shows it before login): where the Windows / Android apps can be downloaded — a file the owner
    uploaded here (API & Keys → App की फ़ाइलें), else the link set in APP_WINDOWS_URL / APP_ANDROID_URL."""
    import os
    out = {}
    for kind, env in (("windows", "APP_WINDOWS_URL"), ("android", "APP_ANDROID_URL")):
        p = _app_path(kind)
        v = (os.getenv(env) or "").strip()
        out[kind] = f"/api/app-files/{kind}" if p.exists() else (v if v.startswith("https://") else "")
        out[kind + "_size"] = p.stat().st_size if p.exists() else 0
    return ok(out)


async def app_file_get(request: Request):
    from starlette.responses import FileResponse
    kind = request.path_params["kind"]
    if kind not in APP_FILES or not _app_path(kind).exists():
        raise ApiError(404, "यह app अभी यहाँ नहीं रखी गई")
    name, _, mime = APP_FILES[kind]
    return FileResponse(_app_path(kind), media_type=mime, filename=name)


@require("editor")
async def app_file_put(request: Request, user: dict):
    """The owner uploads the built installer / APK (raw body) so visitors can download it from this site."""
    if not _operator(user):
        raise ApiError(403, "सिर्फ़ server के मालिक (admin) app की फ़ाइल रख सकते हैं")
    kind = request.path_params["kind"]
    if kind not in APP_FILES:
        raise ApiError(404, "windows या android")
    name = str(request.query_params.get("filename") or "").lower()
    if not name.endswith(APP_FILES[kind][1]):
        raise ApiError(422, f"{APP_FILES[kind][1]} फ़ाइल चाहिए")
    dst = _app_path(kind)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    size = 0
    magic = b""
    with open(tmp, "wb") as f:
        async for chunk in request.stream():
            size += len(chunk)
            if size > APP_MAX:
                f.close()
                tmp.unlink(missing_ok=True)
                raise ApiError(413, "फ़ाइल बहुत बड़ी है (400 MB तक)")
            if len(magic) < 4:
                magic += chunk[:4 - len(magic)]
            f.write(chunk)
    ok_magic = magic[:2] == b"MZ" if kind == "windows" else magic[:2] == b"PK"      # a real .exe / a real .apk (zip)
    if size < 100_000 or not ok_magic:
        tmp.unlink(missing_ok=True)
        raise ApiError(422, "यह सही app फ़ाइल नहीं लगती")
    tmp.replace(dst)
    with db.tx() as c:
        service.log(c, user["workspace_id"], "app_file.put", user_id=user["id"], detail={"kind": kind, "size": size})
    return ok({"kind": kind, "size": size, "url": f"/api/app-files/{kind}"})


@require("editor")
async def app_file_delete(request: Request, user: dict):
    if not _operator(user):
        raise ApiError(403, "सिर्फ़ admin")
    kind = request.path_params["kind"]
    if kind in APP_FILES:
        _app_path(kind).unlink(missing_ok=True)
    return ok({"kind": kind})


routes = [Route("/providers/guide", guide), Route("/app-links", app_links), Route("/app-files/{kind}", app_file_get), Route("/app-files/{kind}", app_file_put, methods=["PUT"]),
          Route("/app-files/{kind}", app_file_delete, methods=["DELETE"]),
          
    Route("/spend", spend_summary),
    Route("/providers", list_providers),
    Route("/providers/{env}", put_provider, methods=["PUT"]),
    Route("/providers/{env}", delete_provider, methods=["DELETE"]),
]
