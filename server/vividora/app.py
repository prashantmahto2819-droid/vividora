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
            await run_in_threadpool(archive.sweep)
            from . import radar_job
            await run_in_threadpool(radar_job.tick)
            from . import retention_job  # YouTube retention/CTR cache: daily for recent videos (≥ 6 h apart)
            await run_in_threadpool(retention_job.tick)
            await run_in_threadpool(_trend_templates_tick)  # optional scheduled thumbnail-trend research
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
    from .api import templates_api
    api_routes += templates_api.routes  # template studio, ad templates, trend research
    routes = [Mount("/api", routes=api_routes), *publish.public_routes]
    if (settings.web_dist / "assets").exists():
        routes.append(Mount("/assets", StaticFiles(directory=settings.web_dist / "assets"), name="assets"))
        for extra in ("manifest.webmanifest", "sw.js", "icon.svg", "icon-192.png", "icon-512.png"):
            if (settings.web_dist / extra).exists():
                routes.append(Route(f"/{extra}", (lambda p: (lambda r: FileResponse(p)))(settings.web_dist / extra)))
    routes.append(Route("/{path:path}", spa))

    class _Revalidate:
        """App files (JS/CSS/HTML) must never be reused from the browser cache after an update:
        "no-cache" makes the browser ask every time (a cheap 304 when nothing changed)."""
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            path = scope.get("path", "") if scope["type"] == "http" else ""
            if not path or path.startswith("/api/") or path.startswith("/pub/"):
                return await self.app(scope, receive, send)

            async def send2(msg):
                if msg["type"] == "http.response.start":
                    hs = [(k, v) for k, v in msg.get("headers", []) if k.lower() != b"cache-control"]
                    hs.append((b"cache-control", b"no-cache"))
                    msg = {**msg, "headers": hs}
                await send(msg)
            return await self.app(scope, receive, send2)

    middleware = [Middleware(_Revalidate)]
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

    app = Starlette(routes=routes, middleware=middleware, lifespan=lifespan,
                    exception_handlers={HTTPException: error_handler})
    log.info("Vividora %s · media=%s · db=%s", __version__, settings.media_root, settings.database_path)
    return app


app = create_app()
