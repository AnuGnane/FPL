"""Team identity and the week's fixture, joined onto an advice payload.

The pitch needs three things the advice artifact does not carry: which club a
player belongs to, which shirt to draw for that club, and who he plays this
week. All three are already on disk — ``players.parquet`` knows every player's
``team_code``, ``teams.parquet`` turns that into a short name, and
``fixtures_all.parquet`` holds the week's games — and none of them is a number
the model produced. So nothing here computes: this module is three joins and a
lookup.

It resolves at **serve time** rather than at solve time, and that is a
constraint rather than a preference. ``gaffer.advise`` writes the payload's
player entries and is a protected file, so the fields cannot be added where
the payload is built. Serving is where ``routers/advice.py`` already backfills
``position`` onto payloads written before positions existed
(``with_positions``), for the same reason, and the same two benefits follow:
every advice file already on disk gains the fields without a re-solve, and the
artifact's own bytes never change.

**Nothing here raises.** This Week rendered its advice without any of these
fields yesterday; a decoration that can 500 the page it decorates is worse
than no decoration. Every read is wrapped, every failure prints, and the
worst case is the payload handed back exactly as it arrived.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from gaffer.data import store

PLAYER_KEYS = ("xi", "bench", "buys", "sells", "captain", "vice")
"""The advice keys holding player dicts.

Deliberately the same tuple ``routers/advice.PLAYER_KEYS`` walks, and
deliberately wider than the pitch needs: enriching ``buys`` and ``sells``
costs one dict lookup each on a payload of about twenty entries, and it is
what lets v9b put a shirt beside a transfer without editing this function
(plan A3).
"""

NEW_FIELDS = ("team_short", "team_code", "next_fixture")
"""What this module adds, and the complete list of it. Anything already on an
entry is left exactly as it was."""


def _teams() -> tuple[dict[int, str], dict[int, int]]:
    """``({team_code: short_name}, {team_id: team_code})``, or two empty maps.

    Both directions come off one file read because both are needed on every
    call: the first names a club, the second turns a fixture's ``home_id``
    into the code the shirt endpoint and the identity field speak.
    """
    try:
        teams = store.load("live/teams.parquet")
        return ({int(c): str(s)
                 for c, s in zip(teams["code"], teams["short_name"])},
                {int(i): int(c)
                 for i, c in zip(teams["team_id"], teams["code"])})
    except Exception as exc:  # noqa: BLE001 — identity is never fatal
        print(f"identity: teams snapshot unreadable ({exc})")
        return {}, {}


def _player_teams() -> dict[int, int]:
    """``{player_code: team_code}``, or an empty map.

    A missing ``team_code`` column is the case G2 names explicitly: a bootstrap
    from an older cache must produce nulls and a printed line, not a
    ``KeyError`` on the way out of a page.
    """
    try:
        players = store.load("live/players.parquet")
        if "team_code" not in players.columns:
            raise KeyError("players snapshot has no team_code column")
        pairs = players[["code", "team_code"]].dropna()
        return {int(c): int(t)
                for c, t in zip(pairs["code"], pairs["team_code"])}
    except Exception as exc:  # noqa: BLE001
        print(f"identity: player snapshot unreadable ({exc})")
        return {}


def _fixture_by_team(gw: int, code_of: dict[int, int],
                     short_of: dict[int, str]) -> dict[int, dict]:
    """``{team_code: {opponent_short, home, kickoff_utc}}`` for one gameweek.

    The first **unfinished** fixture per team, by kickoff. Unfinished because a
    team that has already played this week has no next fixture in it, and
    first-by-kickoff because a double gameweek keeps only its opener this
    cycle (spec D2) and "the opener" has to mean the same thing on every
    reload.

    ``kickoff_utc`` is the banked string passed through unparsed. FPL
    publishes fixtures with a null kickoff while the date is TBC, and a chip
    reading "MUN (H) TBC" is true where an invented time would not be.
    Formatting belongs to the client, which knows the reader's timezone.
    """
    out: dict[int, dict] = {}
    try:
        if not store.exists("live/fixtures_all.parquet"):
            raise FileNotFoundError("data/live/fixtures_all.parquet")
        fixtures = store.load("live/fixtures_all.parquet")
        week = fixtures[(fixtures["gw"] == int(gw))
                        & (~fixtures["finished"].astype(bool))]
        week = week.sort_values("kickoff_time", na_position="last")
    except Exception as exc:  # noqa: BLE001
        print(f"identity: fixtures unreadable, no next-fixture chips ({exc})")
        return {}
    for fx in week.itertuples():
        home = code_of.get(int(fx.home_id))
        away = code_of.get(int(fx.away_id))
        if home is None or away is None:
            continue
        kickoff = getattr(fx, "kickoff_time", None)
        kickoff = None if kickoff is None or pd.isna(kickoff) else str(kickoff)
        for own, other, is_home in ((home, away, True), (away, home, False)):
            # setdefault, not assignment: the frame is sorted by kickoff, so
            # the first row a team appears in is its opener.
            out.setdefault(own, {"opponent_short": short_of.get(other),
                                 "home": is_home, "kickoff_utc": kickoff})
    return out


def _difficulty_by_team(gws: list[int]) -> dict[tuple[int, int], float]:
    """``{(team_code, gw): difficulty}`` from the ticker's own rating.

    The ticker is *called*, not reimplemented (plan A4). Its odds lookup, its
    Elo fallback, its rate-the-fixture-once-from-the-home-side rule and its
    clamp are sixty lines inside ``routers/meta.ticker``, and a second copy
    beside them would be a second answer to "how hard is this fixture" drawn
    on the same page in the same colour scale — a disagreement nobody could
    see. ``weeks=2`` rather than 1 because ``ticker`` slices the first *n*
    unfinished gameweeks and a mid-week reload can find the advice gameweek
    second in that window.

    Every failure is an empty map, which means every chip renders without its
    tint and with everything else intact.
    """
    from gaffer.web.routers import meta

    try:
        table = meta.ticker(weeks=2)
    except Exception as exc:  # noqa: BLE001 — a tint is never fatal
        print(f"identity: no fixture difficulty available ({exc})")
        return {}
    wanted = {int(g) for g in gws}
    return {(int(team.code), int(cell.gw)): float(cell.difficulty)
            for team in table.teams for cell in team.cells
            if int(cell.gw) in wanted}


def with_identity(payload: dict, gw: int) -> dict:
    """Return ``payload`` with ``team_short``/``team_code``/``next_fixture``.

    Additive and non-mutating: the caller's dict is the one ``load_advice``
    returned, and a route that enriched it in place would leak the decoration
    into anything holding a reference. Pre-existing keys on every entry are
    passed through untouched, which is what makes the G2 byte-identity rail
    hold.

    ``gw`` is the advice gameweek, supplied by the caller rather than read off
    the payload: the router already knows it, and a payload whose ``gw`` field
    is missing should still get its shirts.
    """
    try:
        short_of, code_of = _teams()
        team_of = _player_teams()
        fixtures = _fixture_by_team(int(gw), code_of, short_of)
        difficulty = _difficulty_by_team([int(gw)])
    except Exception as exc:  # noqa: BLE001 — the whole join is decoration
        print(f"identity: not applied ({exc})")
        return payload

    def decorate(entry: Any) -> Any:
        if not isinstance(entry, dict) or "code" not in entry:
            return entry
        try:
            code = int(entry["code"])
        except (TypeError, ValueError):
            return entry
        team_code = team_of.get(code)
        fixture = None
        if team_code is not None and team_code in fixtures:
            fixture = dict(fixtures[team_code])
            fixture["difficulty"] = difficulty.get((team_code, int(gw)))
        return {**entry,
                "team_short": short_of.get(team_code)
                if team_code is not None else None,
                "team_code": team_code,
                "next_fixture": fixture}

    out = dict(payload)
    for key in PLAYER_KEYS:
        value = out.get(key)
        if isinstance(value, list):
            out[key] = [decorate(e) for e in value]
        elif isinstance(value, dict):
            out[key] = decorate(value)
    return out
