"""Every ``/api/`` path the frontend fetches is one the server serves (holiday F-116).

ROADMAP candidate 7, F-102's rail read the other way: ``tests/test_guide_routes.py``
holds every served path to GUIDE §5, this holds every path the client asks
for to ``create_app().openapi()``. The rail reads ``frontend/src/`` as text and
starts no vitest; it lives in ``tests/`` because the served side needs
``create_app()``.

A literal starts at a quote or backtick, so an import such as
``"../api/client"`` is not a path. Comments are cut first, because their prose
says ``/api/plan`` for the route ``/api/plan/{gw}``. A template's ``${gw}`` and
OpenAPI's ``{gw}`` both normalise to ``{param}``. A literal ending in ``/`` (such
as ``/api/news/``, which the client completes at run time) is matched as a
prefix of a served path. Membership only, no count: the route total is pinned
in the v11 file alone (the meta-rail, ``tests/test_v12_w1_degradation.py``).
"""

from __future__ import annotations

import re
from pathlib import Path

from gaffer.web.app import create_app

SOURCES = [Path("frontend/src") / part for part in ("api", "hubs", "kit")]

_LITERAL = re.compile(r"(?<=['\"`])/api(?:/(?:[A-Za-z0-9_-]+|\$\{[^}]*\}))*/?")
# `:` before `//` is a URL's scheme, not a comment.
_COMMENT = re.compile(r"/\*.*?\*/|(?<![:\w'\"`])//[^\n]*", re.S)


def _served() -> set[str]:
    return {re.sub(r"\{[^}]+\}", "{param}", path).rstrip("/")
            for path in create_app().openapi()["paths"]}


def _client_paths(text: str) -> set[str]:
    return {re.sub(r"\$\{[^}]*\}", "{param}", match.group(0))
            for match in _LITERAL.finditer(_COMMENT.sub("", text))}


def _unserved(text: str, name: str, served: set[str]) -> list[str]:
    return [f"{name}: {path}" for path in sorted(_client_paths(text))
            if path.rstrip("/") not in served
            and not (path.endswith("/")
                     and any(s.startswith(path) for s in served))]


def _sources() -> list[Path]:
    return sorted(f for root in SOURCES for f in root.rglob("*")
                  if f.suffix in (".ts", ".tsx") and ".test." not in f.name)


def test_the_walk_finds_the_frontends_api_paths():
    found = set().union(*(_client_paths(f.read_text()) for f in _sources()))
    assert len(found) >= 40, sorted(found)
    assert "/api/plan/{param}" in found, sorted(found)


def test_every_api_path_the_frontend_fetches_is_served():
    served = _served()
    assert [miss for f in _sources()
            for miss in _unserved(f.read_text(), str(f), served)] == []


def test_a_fetch_of_an_unserved_path_fails_the_rail_naming_it():
    text = "const a = fetchJson(`/api/nowhere/${id}`)\n// `/api/elsewhere`\n"
    assert _unserved(text, "x.ts", _served()) == ["x.ts: /api/nowhere/{param}"]
