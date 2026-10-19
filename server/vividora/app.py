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
from .api import auth, library, projects, publish, uploads, workers
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


def create_app() -> Starlette:
    logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings.media_root.mkdir(parents=True, exist_ok=True)
    db.init()
    ensure_admin()

    api_routes = [Route("/health", health), *auth.routes, *projects.routes, *uploads.routes, *workers.routes, *library.routes, *publish.routes]
    routes = [Mount("/api", routes=api_routes), *publish.public_routes]
    if (settings.web_dist / "assets").exists():
        routes.append(Mount("/assets", StaticFiles(directory=settings.web_dist / "assets"), name="assets"))
        for extra in ("manifest.webmanifest", "sw.js", "icon.svg", "icon-192.png", "icon-512.png"):
            if (settings.web_dist / extra).exists():
                routes.append(Route(f"/{extra}", (lambda p: (lambda r: FileResponse(p)))(settings.web_dist / extra)))
    routes.append(Route("/{path:path}", spa))

    middleware = []
    if settings.cors_origins:
        middleware.append(Middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                                     allow_methods=["*"], allow_headers=["*"], allow_credentials=True))
    app = Starlette(routes=routes, middleware=middleware,
                    exception_handlers={HTTPException: error_handler})
    log.info("Vividora %s · media=%s · db=%s", __version__, settings.media_root, settings.database_path)
    return app


app = create_app()
