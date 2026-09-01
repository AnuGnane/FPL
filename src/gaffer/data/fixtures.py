"""How many times each team plays, per gameweek — doubles and blanks.

This tree has never counted fixtures. The matrix router appends one cell per
fixture and the ticker prices one row per fixture, so a team playing twice in
a gameweek quietly becomes two cells and two rows and nothing anywhere notices
it is a double. v10b §F2a is that missing count, and two consumers need it —
the ``refresh-data`` writer and the outlook endpoint — so it lives here rather
than private to either.

**Pure.** No I/O, no config, no ``gaffer.web`` import. ``fixtures_all.parquet``
carries ``home_id``/``away_id`` and no team code at all; every consumer joins
through ``teams.parquet`` already, so the id→code map is an argument and
``None`` keys the output on ids — which is what the unit tests use.

**Absence has two different meanings here and telling them apart is the whole
design (plan A8).** A gameweek with no rows is not a league-wide blank, it is
a gameweek nobody has published; only gameweeks *present* in the frame are
considered. And the season's team set is the union of every team appearing
anywhere in the frame, not a hardcoded twenty — a pre-season file and a
February file have different unions and the constant would be right in exactly
one of them.
"""

from __future__ import annotations

import pandas as pd

DOUBLE = 2
"""Fixtures in one gameweek that make a gameweek a *double* for a team.

A three-fixture gameweek is a double too, which is why the test is ``>=``: the
chip layer's question is "more than the usual one", not "exactly two"."""


def _teams_and_gws(fixtures: pd.DataFrame
                   ) -> tuple[pd.DataFrame, set[int]] | None:
    """The frame narrowed to usable rows, and the season's team set."""
    needed = {"gw", "home_id", "away_id"}
    if fixtures is None or not needed.issubset(set(fixtures.columns)):
        return None
    frame = fixtures[["gw", "home_id", "away_id"]].copy()
    for col in ("gw", "home_id", "away_id"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna()
    if frame.empty:
        return None
    teams = ({int(t) for t in frame["home_id"]}
             | {int(t) for t in frame["away_id"]})
    return frame, teams


def fixtures_per_team_per_gw(fixtures: pd.DataFrame,
                             code_of: dict[int, int] | None = None
                             ) -> dict[int, dict[int, int]]:
    """``{gw: {team_code: n_fixtures}}``. Every team that appears, and no others.

    A team with no fixture in a published gameweek is a **zero**, not a missing
    key: a missing key would make every consumer write ``.get(team, ?)`` and
    pick its own answer for what the ``?`` is.

    ``code_of`` maps team ids to codes. An id the map does not know is dropped
    rather than passed through — half-mapped output, some codes and some raw
    ids in one dict, is the quiet way a team gets counted twice under two
    names.
    """
    parsed = _teams_and_gws(fixtures)
    if parsed is None:
        return {}
    frame, team_ids = parsed

    def key(team_id: int) -> int | None:
        return int(team_id) if code_of is None else code_of.get(int(team_id))

    keyed = {t: key(t) for t in team_ids}
    known = {t: k for t, k in keyed.items() if k is not None}

    out: dict[int, dict[int, int]] = {}
    for gw in sorted({int(g) for g in frame["gw"]}):
        week = frame[frame["gw"].astype(int) == gw]
        counts = {k: 0 for k in known.values()}
        for side in ("home_id", "away_id"):
            for team_id in week[side]:
                k = known.get(int(team_id))
                if k is not None:
                    counts[k] += 1
        out[gw] = counts
    return out


def season_outlook(fixtures: pd.DataFrame,
                   code_of: dict[int, int] | None = None,
                   from_gw: int | None = None) -> list[dict]:
    """One row per *published* gameweek: its doubles, its blanks, its counts.

    Sorted by gameweek, and each team list sorted too. An endpoint whose
    ordering depends on a dict's insertion order is an endpoint whose output
    changes when pandas changes.

    ``fixtures`` counts the published **matches** in the week, off the frame's
    own rows rather than by halving the per-team total. Halving assumes every
    fixture contributes two sides to ``counts``, and ``code_of`` breaks that
    assumption by design: an id it does not know is dropped, so a week with one
    unmappable club reported one fewer match than it has. The doubles and
    blanks stay keyed on what could be mapped — those are claims about named
    clubs — but the match count is a fact about the fixture list.
    """
    counts = fixtures_per_team_per_gw(fixtures, code_of)
    parsed = _teams_and_gws(fixtures)
    published = {}
    if parsed is not None:
        gw_column = parsed[0]["gw"].astype(int)
        published = {int(g): int(n) for g, n in gw_column.value_counts().items()}
    weeks = []
    for gw in sorted(counts):
        if from_gw is not None and gw < int(from_gw):
            continue
        week = counts[gw]
        weeks.append({
            "gw": gw,
            "fixtures": published.get(gw, sum(week.values()) // 2),
            "doubles": sorted(t for t, n in week.items() if n >= DOUBLE),
            "blanks": sorted(t for t, n in week.items() if n == 0),
            "counts": dict(sorted(week.items())),
        })
    return weeks
