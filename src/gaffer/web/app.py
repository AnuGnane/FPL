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
from gaffer.web.job_kinds import JOB_KINDS
from gaffer.web.jobs import JobRegistry, JobRunner
from gaffer.web.routers import (advice, chips, components, confidence, digest,
                                drafts, fixtures, jobs, journal, league,
                                league_sim, live, meta, misses, news,
                                overrides, plan,
                                players, prices, quality, review, sensitivity,
                                watchlist, whatif)

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
    app.state.jobs = JobRegistry()
    app.state.job_runner = JobRunner(JOB_KINDS)

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

    app.include_router(advice.router)
    app.include_router(chips.router)
    app.include_router(components.router)
    app.include_router(digest.router)
    app.include_router(confidence.router)
    app.include_router(drafts.router)
    app.include_router(fixtures.router)
    app.include_router(jobs.router)
    app.include_router(journal.router)
    app.include_router(news.router)
    app.include_router(overrides.router)
    app.include_router(plan.router)
    app.include_router(league.router)
    app.include_router(league_sim.router)
    app.include_router(live.router)
    app.include_router(meta.router)
    app.include_router(misses.router)
    app.include_router(players.router)
    app.include_router(prices.router)
    app.include_router(quality.router)
    app.include_router(review.router)
    app.include_router(sensitivity.router)
    app.include_router(watchlist.router)
    app.include_router(whatif.router)

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
        # Must revalidate on every load: without this browsers apply
        # heuristic freshness and keep serving an index.html that points at
        # hashed asset filenames a rebuild has already deleted. ETag and
        # Last-Modified come from FileResponse, so the revalidation is a 304.
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app
