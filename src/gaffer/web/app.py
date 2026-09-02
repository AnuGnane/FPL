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
from gaffer.web.routers import (advice, assets, chips, components, confidence,
                                digest,
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


def generate_token() -> str:
    """A LAN token when the config has none. Printed once, stored nowhere.

    v12 W1 §2.8. Not written into config.toml: spec §8 forbids the app
    editing that file, and a token persisted by a tool the user did not ask to
    persist it is a surprise in a file that also holds an API key.
    """
    import secrets

    return secrets.token_urlsafe(16)


def create_app(*, token: str | None = None) -> FastAPI:
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
    app.include_router(assets.router)
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

    # Named ``static_assets`` rather than ``assets``: the router module
    # imported at the top of this file is called ``assets`` too, and a local
    # binding of that name would make ``include_router(assets.router)`` above
    # an UnboundLocalError.
    static_assets = static_dir() / "assets"
    if static_assets.is_dir():
        app.mount("/assets", StaticFiles(directory=static_assets),
                  name="assets")

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

    # v12 W1 §2.8 (specs/2026-09-01-gaffer-v12-program-design.md). `token`
    # is None for every loopback caller and every test, and the middleware is
    # not installed at all in that case — so the default app is byte-for-byte
    # the app that shipped.
    #
    # A middleware rather than a dependency on each write route: there are
    # ten-odd non-GET routes across nine routers, one of them in the protected
    # whatif module, so per-route would be a wide diff and an unauthorized one.
    #
    # 403 and not 401: a 401 invites the browser's own credential prompt for a
    # scheme this app does not implement, leaving the user a dialog with
    # nowhere to type the thing it is asking for.
    if token:
        @app.middleware("http")
        async def _require_token(request: Request, call_next):
            if request.method in ("GET", "HEAD", "OPTIONS"):
                return await call_next(request)
            import secrets

            # Compared as bytes. `compare_digest` on two `str` raises
            # TypeError unless both are ASCII-only, and a configured
            # `[web] token` with an accented character would turn every
            # write into a 500 instead of a 403 — the header is attacker-
            # controlled, so the encode is `latin-1`/`replace` rather than
            # a decode that could itself raise.
            #
            # The two encodings differ on purpose and the mismatch is the
            # contract: Starlette decodes header bytes as `latin-1`, so
            # re-encoding that way recovers the bytes exactly as they came off
            # the wire, while the configured token is a Python `str` this
            # process owns and `utf-8` is what a byte-for-byte-equal client
            # must have sent. So the wire encoding is *assumed* UTF-8: a
            # non-ASCII token typed into a client that sends it as anything
            # else is a refusal, not a match.
            sent = request.headers.get("X-Gaffer-Token", "") \
                .encode("latin-1", "replace")
            if not secrets.compare_digest(sent, token.encode("utf-8")):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "this gaffer is served to the network; "
                                       "writes need the X-Gaffer-Token header "
                                       "printed when `gaffer ui --lan` "
                                       "started"})
            return await call_next(request)

    return app
