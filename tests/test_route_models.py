"""Holiday F-157: every ``/api/`` route declares its wire type.

v17a made ``schemas.py`` the one source ``npm run types`` reads, so a route
that hands back a bare dict is one the generated types cannot see: the
frontend has to guess its shape, and a rename on the Python side drifts
nothing. This rail asks each route either to name a ``response_model`` or to
return a ``Response`` (binary bodies, server-sent events), whose body is not
JSON the types could describe.

``ALLOWED`` is F-69's shape (``tests/test_noqa_reasons.py``): path to the
reason it cannot comply, and it can only shrink, since an entry whose route
has come to comply fails until it is struck.
"""
from __future__ import annotations

import inspect
import typing

from fastapi import APIRouter, FastAPI
from fastapi.responses import Response
from fastapi.routing import APIRoute, iter_route_contexts

from gaffer.web.app import create_app

# Value: why the route cannot name one model.
ALLOWED = {
    "/api/jobs/{job_id}": (
        "serves both runners: a v7 JobRunner id answers a JobRunView, any "
        "other id falls through to the v6 JobRegistry, whose as_dict() has "
        "result and submitted_at and no kind or line_count"),
}


def _returns_a_response(route: APIRoute) -> bool:
    try:
        hint = typing.get_type_hints(route.endpoint).get("return")
    except NameError:
        hint = inspect.signature(route.endpoint).return_annotation
    return inspect.isclass(hint) and issubclass(hint, Response)


def _undeclared(app: FastAPI) -> dict[str, list[str]]:
    """``path -> ["METHOD path function", ...]`` for routes with no wire type.

    Keyed by path, as ``ALLOWED`` is, with a list because one path can carry
    two methods (``GET`` and ``DELETE /api/jobs/current``).
    """
    out = {}
    # FastAPI 0.141 keeps an included router as one lazy entry in
    # ``app.routes``; ``iter_route_contexts`` is its public walk of the routes
    # inside, each with the path the app serves it at.
    for context in iter_route_contexts(app.routes):
        route, path = context.original_route, context.path or ""
        if not isinstance(route, APIRoute) or not path.startswith("/api/"):
            continue
        if route.response_model is not None or _returns_a_response(route):
            continue
        methods = ",".join(sorted(route.methods))
        out.setdefault(path, []).append(
            f"{methods} {path} {route.endpoint.__name__}")
    return out


def test_every_api_route_names_a_response_model_or_returns_a_response(
        tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stray = {path: lines for path, lines in _undeclared(create_app()).items()
             if path not in ALLOWED}
    assert stray == {}


def test_each_allowlisted_route_still_needs_its_entry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    undeclared = _undeclared(create_app())
    assert [path for path in ALLOWED if path not in undeclared] == []


def test_the_walk_sees_every_route_the_schema_serves(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = create_app()
    walked = {context.path for context in iter_route_contexts(app.routes)
              if isinstance(context.original_route, APIRoute)
              and context.original_route.include_in_schema}
    assert walked == set(app.openapi()["paths"])


def test_a_bare_dict_route_is_caught_and_a_typed_one_is_not():
    router = APIRouter(prefix="/api/tmp")

    @router.get("/bare")
    def bare():
        return {"x": 1}

    @router.get("/binary")
    def binary() -> Response:
        return Response(content=b"")

    @router.get("/typed", response_model=dict[str, int])
    def typed():
        return {"x": 1}

    app = FastAPI()
    app.include_router(router)
    assert _undeclared(app) == {"/api/tmp/bare": ["GET /api/tmp/bare bare"]}
