"""How hard a fixture is, rated once for everyone (v18d §2).

The rating used to live inside ``web/routers/meta.ticker``, and the two core
callers that need it — the ladder's step reasons and the identity decorator's
fixture tint — reached into the web layer to call the route handler. That is
backwards: the core must not import the web layer, and a rating is not a
route. So the arithmetic lives here and the route is a shape adapter over it.

There is still exactly one answer to "how hard is this fixture". A second
copy beside the first would be a second answer drawn on the same page in the
same colour scale — a disagreement nobody could see.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from gaffer.artifacts import load_snapshot
from gaffer.data import store
from gaffer.data.elo import compute_elo, expected_score
from gaffer.data.odds import poisson_win_prob

# Plain dataclasses, not the web schemas (v18d §2): the core owns this and
# must not import ``web``. The field names are the schemas' own, so the route
# converts field for field.

@dataclass(frozen=True)
class FixtureCell:
    gw: int
    opponent: str
    home: bool
    difficulty: float


@dataclass(frozen=True)
class TeamDifficulty:
    code: int
    name: str
    short_name: str
    cells: list[FixtureCell] = field(default_factory=list)
    mean_difficulty: float = 0.0


@dataclass(frozen=True)
class FixtureDifficulty:
    gws: list[int] = field(default_factory=list)
    source: str = "elo"
    teams: list[TeamDifficulty] = field(default_factory=list)


def _odds_lookup() -> dict[tuple[int, int, int], tuple[float, float]]:
    """``(team, gw, opp)`` -> ``(goals for, against)`` from banked odds."""
    odds_dir = store.DATA_DIR / "live" / "odds"
    if not odds_dir.is_dir():
        return {}
    out: dict[tuple[int, int, int], tuple[float, float]] = {}
    for path in sorted(odds_dir.glob("gw*.parquet")):
        frame = pd.read_parquet(path)
        for row in frame.itertuples():
            out[(int(row.team_code), int(row.gw), int(row.opp_code))] = (
                float(row.odds_e_goals_for), float(row.odds_e_goals_against))
    return out


def rate_fixtures(weeks: int = 8) -> FixtureDifficulty:
    """Every team's next ``weeks`` unfinished gameweeks, rated 0 (easy) to 1.

    Odds where they are banked, Elo everywhere else; ``source`` says which
    reached the table at all.
    """
    teams = load_snapshot("live/teams.parquet")
    fixtures = load_snapshot("live/fixtures_all.parquet")
    code_of = dict(zip(teams["team_id"], teams["code"]))
    short_of = dict(zip(teams["code"], teams["short_name"]))

    upcoming = fixtures[~fixtures["finished"].astype(bool)].copy()
    gws = sorted(int(g) for g in upcoming["gw"].dropna().unique())[:weeks]
    upcoming = upcoming[upcoming["gw"].isin(gws)]

    odds = _odds_lookup()
    elo_final: dict[int, float] = {}
    if store.exists("live/fixtures.parquet"):
        finished = store.load("live/fixtures.parquet")
        if not finished.empty:
            elo_final = compute_elo(finished).attrs["final"]

    used_odds = False
    cells: dict[int, list[FixtureCell]] = {int(c): [] for c in teams["code"]}
    for fx in upcoming.sort_values("gw").itertuples():
        home_code = code_of.get(int(fx.home_id))
        away_code = code_of.get(int(fx.away_id))
        if home_code is None or away_code is None:
            continue
        # Rate the fixture once from the home side: home advantage belongs to
        # the fixture, not to each half of it, so the away side takes the
        # complement rather than a second call that would hand *both* teams
        # the boost.
        home_elo_win = expected_score(elo_final.get(home_code, 1500.0),
                                      elo_final.get(away_code, 1500.0),
                                      home=True)
        for own, other, home, elo_win in (
                (home_code, away_code, True, home_elo_win),
                (away_code, home_code, False, 1.0 - home_elo_win)):
            priced = odds.get((own, int(fx.gw), other))
            if priced is not None:
                used_odds = True
                win = poisson_win_prob(priced[0], priced[1])
            else:
                win = elo_win
            cells[own].append(FixtureCell(
                gw=int(fx.gw), opponent=str(short_of.get(other, "")),
                home=home, difficulty=round(min(max(1.0 - win, 0.0), 1.0), 3)))

    rows = []
    for team in teams.itertuples():
        mine = cells[int(team.code)]
        mean = round(sum(c.difficulty for c in mine) / len(mine), 3) if mine \
            else 0.0
        rows.append(TeamDifficulty(code=int(team.code), name=str(team.name),
                                   short_name=str(team.short_name),
                                   cells=mine, mean_difficulty=mean))
    rows.sort(key=lambda t: t.mean_difficulty)
    return FixtureDifficulty(gws=gws, source="odds" if used_odds else "elo",
                             teams=rows)


def difficulty_by_team(gws: list[int]) -> dict[tuple[int, int], float]:
    """``{(team_code, gw): difficulty}`` for the gameweeks in ``gws``.

    :func:`rate_fixtures` is *called*, not reimplemented: one rating, not two.
    Since v18d §2 this is the one home the ticker route, the identity
    decorator, ``advise`` and ``ladder`` all call, which is what keeps the
    chip's tint and the table's cell the same number. ``weeks=2`` rather than
    1 because the rating slices the first *n* unfinished gameweeks and a
    mid-week reload can find the advice gameweek second in that window.

    Every failure is an empty map, which means every chip renders without its
    tint and with everything else intact.
    """
    try:
        table = rate_fixtures(weeks=2)
    except Exception as exc:  # noqa: BLE001 — a tint is never fatal
        print(f"difficulty: no fixture difficulty available ({exc})")
        return {}
    wanted = {int(g) for g in gws}
    return {(int(team.code), int(cell.gw)): float(cell.difficulty)
            for team in table.teams for cell in team.cells
            if int(cell.gw) in wanted}
