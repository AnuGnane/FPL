"""FPL-Core-Insights: per-match detail, published cup fixtures, club Elo.

``cups.py`` (v8a) already reads this repository for one thing — the *dates*
league clubs played cup ties on — and deliberately leaves everything else on
the floor. This module takes the rest: per-player per-match defensive and
positional detail, the whole published fixture list including ties that have
not been played yet, and the Elo the archive carries per club and per match.

Three facts about the archive shape everything here, all measured 2026-09-02
and recorded in the W4 plan's Appendix A.

**There are two folder layouts, not one.** 2025-2026 and 2026-2027 publish
``data/<season>/By Gameweek/GW<n>/<table>.csv``; 2024-2025 publishes
``data/<season>/<table>/GW<n>/<table>.csv`` and hides its ``teams.csv`` a
folder deeper. So paths are **enumerated from the recursive git tree**, keyed
on basename and season folder, rather than built from a template. A template
would have to be edited every time the publisher reorganises; this does not.

**``By Gameweek`` already contains every tournament.** GW2 of 2026-27 holds
``prem`` and ``efl-cup`` rows in one file. Walking ``By Tournament`` as well
would count a cup tie twice, so it is never walked — which is also why this
module does not replace ``cups.py``: that one reads ``By Tournament``
``matches.csv`` for seasons this one may not cover, and the two parquets are
independent.

**There is no ClubElo file.** Elo is a column on ``teams.csv`` and a pair of
columns on every fixture row. ``elo.parquet`` is derived from both, and for a
season the publisher has not yet filled in — 2026-27, today — it is
legitimately empty. An empty Elo table is a fact about the archive, not a
failure of this collector, and the health line says which.

# v12 W4 §5.1 (specs/2026-09-01-gaffer-v12-program-design.md)
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pandas as pd

from gaffer.data.cups import (CUPS_RAW_BASE, CUPS_TREE_URL, _cached_get,
                              _http, repo_season)

__all__ = ["CI_CACHE", "SEASON_TABLES", "ci_paths_from_tree", "repo_season"]

CI_CACHE = Path("data/raw/core_insights")
"""Where fetched CSVs are cached. Same contract as ``cups.CUPS_CACHE``: a file
on disk is never re-fetched, so a killed run costs only what it had not
reached. A *finished* gameweek's files never change; an unfinished one's do,
which is why :func:`download_core_insights` takes ``refresh_gws``."""

SEASON_TABLES = ("players", "teams", "fixtures", "playermatchstats")
"""The keys every bundle answers, present or absent. ``players`` and ``teams``
are one path or ``None``; ``fixtures`` and ``playermatchstats`` are
``{gw: path}`` and may be empty."""

_GW_RE = re.compile(r"^GW(\d+)$")


def _gw_of(part: str) -> int | None:
    """``"GW10"`` -> ``10``; anything else -> ``None``."""
    hit = _GW_RE.match(part)
    return int(hit.group(1)) if hit else None


def _empty_bundle() -> dict:
    return {"players": None, "teams": None, "fixtures": {},
            "playermatchstats": {}}


def ci_paths_from_tree(tree: dict, seasons: list[str]) -> dict[str, dict]:
    """``{fpl season: bundle}`` from one recursive git-trees payload.

    Layout-agnostic by construction: a path is claimed by what its *basename*
    is and which season folder it sits under, never by how deep it is. That is
    what lets 2024-2025's ``playermatchstats/GW1/playermatchstats.csv`` and
    2025-2026's ``By Gameweek/GW1/playermatchstats.csv`` land in the same slot
    with no branch.

    ``By Tournament`` is skipped outright (see the module docstring), and a
    gameweek that publishes both ``fixtures.csv`` and ``matches.csv`` resolves
    to ``fixtures.csv`` — they are the same bytes in the live archive, and
    picking one deterministically beats depending on the order the tree
    happened to list them in.

    ``players.csv`` and ``teams.csv`` are **the shallowest one wins**, not the
    first one seen. The archive publishes both at the season root *and* inside
    every ``By Gameweek/GW<n>`` folder, and git lists ``By Gameweek`` before
    ``players.csv``, so "first seen" would key an entire season off GW1's
    snapshot — an element map missing every player who signed after August.

    An empty or unreachable tree yields one empty bundle per requested season
    rather than raising: a collector that dies because GitHub is down is a
    collector that gets uninstalled.
    """
    folders = {repo_season(s): s for s in seasons}
    out: dict[str, dict] = {s: _empty_bundle() for s in seasons}
    depth: dict[tuple[str, str], int] = {}
    # ``matches.csv`` is only ever taken where no ``fixtures.csv`` shares the
    # folder, so the two passes cannot race: fixtures are claimed first.
    fallbacks: list[tuple[str, int, str]] = []
    for node in (tree or {}).get("tree", []):
        path = str(node.get("path") or "")
        parts = path.split("/")
        if len(parts) < 3 or parts[0] != "data":
            continue
        season = folders.get(parts[1])
        if season is None or "By Tournament" in parts:
            continue
        name = parts[-1]
        bundle = out[season]
        if name in ("players.csv", "teams.csv"):
            key = name[:-4]
            if depth.get((season, key), 1 << 30) > len(parts):
                bundle[key] = path
                depth[(season, key)] = len(parts)
            continue
        gw = _gw_of(parts[-2]) if len(parts) >= 3 else None
        if gw is None:
            continue
        if name == "playermatchstats.csv":
            bundle["playermatchstats"][gw] = path
        elif name == "fixtures.csv":
            bundle["fixtures"][gw] = path
        elif name == "matches.csv":
            fallbacks.append((season, gw, path))
    for season, gw, path in fallbacks:
        out[season]["fixtures"].setdefault(gw, path)
    return out


def fetch_tree(client: httpx.Client | None = None) -> dict:
    """The repository's recursive git tree, or ``{}`` when it is unreachable.

    One request answers what would otherwise be a listing per season per
    table. ``{}`` is the documented degradation and every caller treats it as
    "the archive published nothing", never as an error.
    """
    http = _http(client)
    try:
        return http.get(CUPS_TREE_URL).json()
    except (httpx.HTTPError, ValueError) as exc:
        print(f"core-insights: tree listing unavailable ({exc})")
        return {}


def fetch_csv(path: str, http: httpx.Client,
              cache_dir: Path | str = CI_CACHE) -> str | None:
    """One archive path -> its text, cached forever under ``cache_dir``.

    ``None`` with a printed line on a 404 or a dead connection: a run spanning
    three seasons and a hundred gameweeks must not die on one missing folder.
    """
    return _cached_get(http, f"{CUPS_RAW_BASE}/{path}", Path(cache_dir) / path)
