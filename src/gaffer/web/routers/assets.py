"""``GET /api/assets/{shirt,photo}/{code}`` — kit and faces, cached locally.

The frontend speaks only to this backend: every byte on the page arrives via
``/api/*`` or the bundled static directory, and the pitch keeps that posture
rather than hotlinking fifteen images from premierleague.com on every load
(spec D1). So the browser asks this router, this router asks the official CDN
**once**, the bytes land under ``data/live/assets/``, and every request after
that is a disk read.

Three states, in order, and the order is the contract:

1. a **hit** reads the banked file and constructs no HTTP client at all;
2. a **miss** fetches once, banks through a temp file, and serves;
3. **any failure** serves a bundled SVG with a short max-age and writes
   nothing.

The third clause is the one worth defending. A silhouette written into the
cache directory would be indistinguishable from a real shirt on every later
request, so one evening without a network would cost the pitch its kit until
somebody found the directory and deleted it by hand. Failures are served, not
stored.

This is not a proxy. It fetches only for codes the banked bootstrap already
contains — a team code out of ``teams.parquet`` or a player code out of
``players.parquet`` — and the route declares both as ``int``, so nothing a
caller types ever reaches a filesystem path. A clone with no snapshot has an
empty allowlist and answers 404 to everything, which is correct: a machine
with no data should be drawing silhouettes.

Licensing: player and kit imagery is Premier League property. A local
single-user cache for personal display is the same use the official site
makes of it. ``data/`` is untracked, the cache is never staged, and nothing
here redistributes anything.
"""

from __future__ import annotations

import os
from importlib.resources import files
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Query, Response

from gaffer.data import store

router = APIRouter(prefix="/api/assets", tags=["assets"])

SHIRT_BASE = "https://fantasy.premierleague.com/dist/img/shirts/standard"
PHOTO_BASE = ("https://resources.premierleague.com/premierleague/photos/"
              "players/110x140")
"""The two CDN roots, verified by curl on 2026-08-31 (spec D1).

Module constants rather than config keys, deliberately: a new config field
would break the field-count pin inside ``tests/test_v8f_degradation.py``,
which this cycle protects, and the only caller who wanted a knob was a gate
that has a better way to test the same thing (plan A7). Tests monkeypatch
these; the live gate unplugs the network.
"""

CACHE_REL = "live/assets"

TIMEOUT = 5.0
"""Seconds. Short on purpose: this call sits inside a page load, and a CDN
that is thinking about it is, for the reader's purposes, down."""

HIT_CACHE = "public, max-age=604800, immutable"
"""A week, immutable. A shirt for a team code does not change mid-season, and
the browser asking again every load would defeat the point of banking."""

MISS_CACHE = "public, max-age=60"
"""A minute, and no ``immutable``. The fallback means "we could not reach the
CDN just now", which is a sentence with a short shelf life."""

FALLBACKS = {"shirt": "shirt_fallback.svg", "photo": "player_fallback.svg"}


def _cache_dir() -> Path:
    """``data/live/assets``, resolved at call time.

    ``store.DATA_DIR`` is read here rather than bound at import so a test that
    redirects the data root redirects the cache with it.
    """
    return store.DATA_DIR / CACHE_REL


def _fetch(url: str) -> bytes:
    """One GET, with a timeout. The only outbound call in this module.

    A named module-level function rather than an inline ``httpx.get`` so that
    a test can replace it and *count* the calls — the cache-hit rail is an
    assertion about how many times this ran, and that is not observable
    through a client constructed inside a handler.
    """
    response = httpx.get(url, timeout=TIMEOUT, follow_redirects=True)
    response.raise_for_status()
    return response.content


def _bank(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` through a temp file and ``os.replace``.

    The store's idiom, for the store's reason: a process killed mid-write
    would otherwise leave a truncated image that every later request serves as
    a valid hit. Separately named so a test can make the write fail without
    making the fetch fail.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _fallback(kind: str) -> Response:
    """The bundled SVG, served and never stored (module docstring, clause 3).

    Read through ``importlib.resources`` rather than a repo-relative path so
    an installed wheel serves its own copy — ``gaffer.assets``'s idiom.
    """
    svg = files("gaffer.assets").joinpath(FALLBACKS[kind]).read_bytes()
    return Response(content=svg, media_type="image/svg+xml",
                    headers={"Cache-Control": MISS_CACHE})


def _allowed_codes(rel: str, column: str) -> set[int]:
    """The banked bootstrap's codes, or an empty set. Never raises.

    An empty set refuses every request, which is the correct behaviour on a
    clone that has never run ``gaffer advise``: with no data there is no
    allowlist, and without an allowlist this would be an open proxy.
    """
    try:
        if not store.exists(rel):
            return set()
        frame = store.load(rel)
        return {int(c) for c in frame[column].dropna()}
    except Exception as exc:  # noqa: BLE001 — a bad snapshot allows nothing
        print(f"asset allowlist unreadable ({rel}): {exc}")
        return set()


def _serve(kind: str, cache_name: str, url: str, media_type: str) -> Response:
    """Hit, else fetch-and-bank, else fall back. The whole contract."""
    path = _cache_dir() / cache_name
    try:
        if path.is_file():
            return Response(content=path.read_bytes(), media_type=media_type,
                            headers={"Cache-Control": HIT_CACHE})
    except OSError as exc:
        # A banked file we cannot read is a miss, not an error: fall through
        # and try the CDN rather than serving a silhouette for a file that is
        # sitting right there.
        print(f"asset cache unreadable ({cache_name}): {exc}")
    try:
        data = _fetch(url)
    except Exception as exc:  # noqa: BLE001 — a page never 500s over an image
        print(f"asset fetch failed ({url}): {exc}")
        return _fallback(kind)
    if not data:
        # A 200 with no body. Banking it would cache the emptiness.
        print(f"asset fetch returned no bytes ({url})")
        return _fallback(kind)
    try:
        _bank(path, data)
    except Exception as exc:  # noqa: BLE001
        # The bytes are already in hand: a read-only disk costs the cache,
        # not the shirt, and the next load simply fetches again.
        print(f"asset not cached ({cache_name}): {exc}")
    return Response(content=data, media_type=media_type,
                    headers={"Cache-Control": HIT_CACHE})


@router.get("/shirt/{team_code}")
def shirt(team_code: int,
          keeper: bool = Query(False,
                               description="the goalkeeper's variant")
          ) -> Response:
    """One team's kit. ``team_code`` is ``teams[].code`` in the bootstrap.

    The keeper wears a different shirt and is therefore a different file and a
    different URL: a cached outfield shirt must never answer a request for the
    goalkeeper's, or the pitch draws the wrong kit on the one player whose
    kit is always different.
    """
    if team_code not in _allowed_codes("live/teams.parquet", "code"):
        raise HTTPException(status_code=404,
                            detail=f"team {team_code} is not in the banked "
                                   f"bootstrap")
    suffix = "_1" if keeper else ""
    return _serve("shirt", f"shirt_{team_code}{suffix}.webp",
                  f"{SHIRT_BASE}/shirt_{team_code}{suffix}-66.webp",
                  "image/webp")


@router.get("/photo/{player_code}")
def photo(player_code: int) -> Response:
    """One player's face. ``player_code`` is ``elements[].code``.

    Not drawn on the pitch this cycle (spec §3) — the endpoint ships now so
    the cache warms behind the v9b identity rollout, and so the fallback path
    has been exercised for a season before anything depends on it.
    """
    if player_code not in _allowed_codes("live/players.parquet", "code"):
        raise HTTPException(status_code=404,
                            detail=f"player {player_code} is not in the "
                                   f"banked bootstrap")
    return _serve("photo", f"photo_{player_code}.png",
                  f"{PHOTO_BASE}/p{player_code}.png", "image/png")
