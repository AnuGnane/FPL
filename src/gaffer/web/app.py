"""The local FastAPI application.

Bound to 127.0.0.1 by the CLI and unauthenticated by design: the loopback
interface *is* the security model (spec §2.1). Nothing here writes to FPL.

The SPA fallback is a 404 handler rather than a catch-all route so that it
cannot shadow a router registered after it, and it refuses ``/api/...`` and
``/assets/...`` itself: a typo in an API path must not return the HTML shell
with a 200 and have the frontend try to ``JSON.parse`` a document.
"""

from __future__ import annotations

import logging
from importlib.resources import files
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from gaffer.errors import GafferError

log = logging.getLogger("gaffer.web")

DEFAULT_PORT = 8927


def static_dir() -> Path:
    """The built frontend, located the same way the report assets are.

    ``importlib.resources`` rather than a repo-relative path so an installed
    wheel serves its own copy — see ``gaffer.assets``.
    """
    return Path(str(files("gaffer.web").joinpath("static")))


def create_app() -> FastAPI:
    app = FastAPI(title="gaffer", docs_url=None, redoc_url=None)

    @app.exception_handler(GafferError)
    async def _domain_error(_: Request, exc: GafferError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        # The traceback belongs in the terminal the user started `gaffer ui`
        # in, not in the browser.
        log.exception("unhandled error", exc_info=exc)
        return JSONResponse(status_code=500,
                            content={"detail": "internal error — see the "
                                               "terminal running `gaffer ui`"})

    @app.get("/api/ping")
    def ping() -> dict:
        return {"ok": True, "app": "gaffer"}

    assets = static_dir() / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.exception_handler(StarletteHTTPException)
    async def spa(request: Request, exc: StarletteHTTPException):
        path = request.url.path
        if (exc.status_code != 404 or path.startswith("/api/")
                or path.startswith("/assets/")):
            return JSONResponse(status_code=exc.status_code,
                                content={"detail": exc.detail})
        index = static_dir() / "index.html"
        if not index.exists():
            return JSONResponse(
                status_code=503,
                content={"detail": "frontend not built — run `npm install && "
                                   "npm run build` in frontend/"})
        return FileResponse(index)

    return app
