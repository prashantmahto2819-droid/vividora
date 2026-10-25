"""The Vividora web server: JSON API under /api plus the dashboard (built web/)."""

from __future__ import annotations

import logging

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import __version__, db
from .api import analytics, auth, channels, command_api, library, overview, plan, projects, publish, radar_api, schedule_api, storage_api, thumbnails, uploads, workers
from .api import dub_api
from .api.deps import error_handler
from .bootstrap import ensure_admin
from .config import settings

log = logging.getLogger("vividora")


async def health(request: Request):
    """Enhanced health endpoint with optional system stats.
    GET /api/health          → basic {ok, version}
    GET /api/health?full=1   → adds memory, cpu, disk, jobs, workers (requires worker token or auth)
    """
    if request.query_params.get("full"):
        # full stats: check auth (worker token or logged-in user)
        token = request.headers.get("x-worker-token") or ""
        auth_ok = token == settings.worker_token
        if not auth_ok:
            # also accept a valid session cookie / bearer token
            from .api.deps import current_user
            try:
                auth_ok = current_user(request) is not None
            except Exception:  # noqa: BLE001
                pass
        if auth_ok:
            from . import sysguard
            snap = sysguard.system_snapshot()
            return JSONResponse({"ok": True, "version": __version__, "system": snap})
    return JSONResponse({"ok": True, "version": __version__})


async def spa(request: Request):
    index = settings.web_dist / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"ok": True, "message": "Vividora API चालू है। dashboard build नहीं मिला (web-dist)."})


def _trend_templates_tick() -> None:
    """Channels with brand.trendtpl.auto = true refresh their thumbnail-trend research once a day at `hour`."""
    from datetime import datetime
    from .engine import radar, trendtpl
    from .engine.schedule import _tz
    loc = datetime.now(_tz("Asia/Kolkata"))
    today = loc.strftime("%Y-%m-%d")
    for ch in db.rows(db.conn().execute("SELECT * FROM channels")):
        st = ch.get("settings") or {}
        if not trendtpl.due(st, loc.hour, today):
            continue
        try:
            trendtpl.collect(ch["workspace_id"], radar.settings_of(st).get("queries") or [])
        except Exception as e:  # noqa: BLE001
            log.warning("trend templates %s: %s", ch.get("id"), e)
        with db.tx() as c:
            db.update(c, "channels", ch["id"], {"settings": {**st, "trendtpl": {**(st.get("trendtpl") or {}), "last": today}}})


async def _scheduler():
    """Hourly housekeeping: requeue stale jobs, archive old approved projects."""
    import asyncio
    from . import archive, queue
    from starlette.concurrency import run_in_threadpool
    await asyncio.sleep(60)
    while True:
        try:
            with db.tx() as c:
                queue.requeue_stale(c)
            # WAL checkpoint: prevent unbounded WAL file growth on long-running servers
            try:
                db.conn().execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:  # noqa: BLE001
                pass
            await run_in_threadpool(archive.sweep)
            from . import radar_job
            await run_in_threadpool(radar_job.tick)
            from . import retention_job  # YouTube retention/CTR cache: daily for recent videos (≥ 6 h apart)
            await run_in_threadpool(retention_job.tick)
            from . import backup  # one SQLite backup per day (DATA_ROOT/backups, pushed to the archive remote)
            if backup.due():
                await run_in_threadpool(backup.run)
            await run_in_threadpool(_trend_templates_tick)  # optional scheduled thumbnail-trend research
            # ---- sysguard: periodic resource check ----
            from . import sysguard
            mem = sysguard._mem_info()
            if mem["available_gb"] < sysguard.WARN_FREE_GB:
                log.warning("⚠ RAM: %.1f GB free / %.1f GB total (%.0f%% used)",
                            mem["available_gb"], mem["total_gb"], mem["percent_used"])
            if not sysguard.disk_ok():
                log.warning("⚠ Disk space low on media_root")
        except Exception as e:  # noqa: BLE001
            log.warning("scheduler: %s", e)
        await asyncio.sleep(3600)


async def _autopilot_watchdog():
    """Every minute: resume autopilot steps lost to a restart, wake stalled steps, tell the owner
    when no worker can take a waiting job (autopilot_flow.kick)."""
    import asyncio
    from starlette.concurrency import run_in_threadpool
    from . import autopilot_flow
    await asyncio.sleep(5)
    while True:
        try:
            await run_in_threadpool(autopilot_flow.kick)
        except Exception as e:  # noqa: BLE001
            log.warning("autopilot watchdog: %s", e)
        await asyncio.sleep(60)


def create_app() -> Starlette:
    logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings.media_root.mkdir(parents=True, exist_ok=True)
    from .security import default_secrets_in_use
    weak = default_secrets_in_use()
    if weak and settings.saas_mode:
        raise SystemExit(f"SAAS_MODE=1 के साथ default/छोटे {', '.join(weak)} नहीं चल सकते — .env में 32+ अक्षर के random values डालें "
                         "(python3 -c \"import secrets;print(secrets.token_urlsafe(48))\")")
    if weak:
        log.warning("⚠ %s default/कमज़ोर है — public करने से पहले .env में बदलें", ", ".join(weak))
    db.init()
    ensure_admin()
    from .bootstrap import ensure_starter
    ensure_starter()

    api_routes = [Route("/health", health), *auth.routes, *projects.routes, *uploads.routes, *workers.routes, *library.routes, *publish.routes, *plan.routes, *analytics.routes, *channels.routes, *storage_api.routes, *schedule_api.routes, *radar_api.routes,
                  *thumbnails.routes, *overview.routes, *command_api.routes]
    api_routes += dub_api.routes  # AI voice-over / dubbing
    from .api import pro_api
    api_routes += pro_api.routes  # pro editing: text-based cuts, scenes, colour match, music fit
    from .api import compress_api
    api_routes += compress_api.routes  # standalone video compressor
    from .api import themes_api
    api_routes += themes_api.routes  # one-click themes
    from .api import saas_api
    api_routes += saas_api.routes  # plans / usage / Razorpay / admin (inert without SAAS_MODE)
    from .api import templates_api
    api_routes += templates_api.routes  # template studio, ad templates, trend research
    from .api import chars_api
    api_routes += chars_api.routes  # Character Studio (2D rigs, scenes, storyboards → explainer)
    from .api import chars3d_api
    api_routes += chars3d_api.routes  # 3D Studio: procedural characters, scenes, lip-sync, explainers
    from .api import copilot_api
    api_routes += copilot_api.routes  # Channel Copilot: hook scores, weekly audit, comment drafts
    from .api import ytshorts_api
    api_routes += ytshorts_api.routes  # YouTube → Shorts/Reels converter
    from .api import scriptgen_api
    api_routes += scriptgen_api.routes  # AI Script Generator
    routes = [Mount("/api", routes=api_routes), *publish.public_routes]
    if (settings.web_dist / "assets").exists():
        routes.append(Mount("/assets", StaticFiles(directory=settings.web_dist / "assets"), name="assets"))
        for extra in ("manifest.webmanifest", "sw.js", "icon.svg", "icon-192.png", "icon-512.png"):
            if (settings.web_dist / extra).exists():
                routes.append(Route(f"/{extra}", (lambda p: (lambda r: FileResponse(p)))(settings.web_dist / extra)))
    routes.append(Route("/{path:path}", spa))

    class _SecurityHeaders:
        """Production security headers + cache policy.

        Security (every response):
          X-Content-Type-Options: nosniff          — prevent MIME-sniffing attacks
          X-Frame-Options: DENY                    — block clickjacking
          Referrer-Policy: strict-origin-when-cross-origin  — limit Referer leakage
          Permissions-Policy: camera=(), microphone=(), geolocation=()  — disable unused browser APIs

        Cache (non-API only):
          /assets/*  → immutable, 1 year (filenames contain content hashes from the build)
          everything else (index.html, manifest, sw.js) → no-cache (304 when unchanged)
          /api/ and /pub/ → untouched (backend sets its own headers)
        """
        _SEC_HEADERS = [
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"strict-origin-when-cross-origin"),
            (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
        ]

        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                return await self.app(scope, receive, send)

            path = scope.get("path", "")
            is_api = path.startswith("/api/") or path.startswith("/pub/")
            is_hashed = path.startswith("/assets/")

            async def send2(msg):
                if msg["type"] == "http.response.start":
                    hs = list(msg.get("headers", []))
                    # security headers on every response
                    present = {k.lower() for k, _ in hs}
                    for k, v in self._SEC_HEADERS:
                        if k not in present:
                            hs.append((k, v))
                    # cache policy on non-API routes
                    if not is_api:
                        hs = [(k, v) for k, v in hs if k.lower() != b"cache-control"]
                        if is_hashed:
                            hs.append((b"cache-control", b"public, max-age=31536000, immutable"))
                        else:
                            hs.append((b"cache-control", b"no-cache"))
                    msg = {**msg, "headers": hs}
                await send(msg)
            return await self.app(scope, receive, send2)

    class _RateLimit:
        """Per-IP token buckets for the abuse-prone routes (auth, uploads, hooks). Always on, in-memory."""
        BUCKETS = (("/api/auth/", 60, 90), ("/api/uploads", 600, 900), ("/api/library", 300, 400), ("/api/hooks/", 120, 120))

        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                path = scope.get("path", "")
                for prefix, per_min, burst in self.BUCKETS:
                    if path.startswith(prefix):
                        from . import saas
                        hdrs = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
                        ip = hdrs.get("cf-connecting-ip") or (hdrs.get("x-forwarded-for") or "").split(",")[0].strip() \
                            or (scope.get("client") or ("?",))[0]
                        if not saas.rate_ok(f"mw:{prefix}:{ip}", per_min, burst):
                            resp = JSONResponse({"error": "बहुत जल्दी-जल्दी request — एक मिनट रुकें"}, status_code=429)
                            return await resp(scope, receive, send)
                        break
            return await self.app(scope, receive, send)

    middleware = [Middleware(_SecurityHeaders), Middleware(_RateLimit)]
    if settings.cors_origins:
        middleware.append(Middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                                     allow_methods=["*"], allow_headers=["*"], allow_credentials=True))
    import asyncio
    import contextlib

    @contextlib.asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(_scheduler())
        wd = asyncio.create_task(_autopilot_watchdog())
        yield
        task.cancel()
        wd.cancel()

    async def server_error(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all: unhandled exceptions → clean JSON 500, no stack trace leak in production."""
        log.exception("unhandled error: %s %s", request.method, request.url.path)
        detail = str(exc) if settings.debug else "internal server error"
        return JSONResponse({"error": detail}, status_code=500)

    app = Starlette(routes=routes, middleware=middleware, lifespan=lifespan,
                    exception_handlers={HTTPException: error_handler, Exception: server_error})
    log.info("Vividora %s · media=%s · db=%s", __version__, settings.media_root, settings.database_path)
    return app


app = create_app()
