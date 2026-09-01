"""GET /api/fixtures/matrix — the classic grid, priced by the trained model.

The ticker in ``meta.py`` answers a different question (win probability from
odds or Elo, one number). This one reads the fitted Dixon-Coles heads directly
so an attacker's fixture and a defender's fixture are scored separately, which
is the whole reason the matrix exists.

Cold-clone safe by construction: no team model, no snapshots, or a team head
without ``attack_`` (a plain ``TeamModel``) all return the same empty payload.
"""

from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter, Query

from gaffer.data import store
from gaffer.models import persistence
from gaffer.data.fixtures import season_outlook
from gaffer.web.schemas import (FixtureMatrix, FixtureOutlook, MatrixCell,
                                MatrixTeam, OutlookTeam, OutlookWeek)

router = APIRouter(prefix="/api", tags=["fixtures"])

EMPTY = FixtureMatrix(gws=[], teams=[], source="none")


WINSOR_Q = 0.05
"""Trim fraction at each tail before the min-max. Roughly one club of twenty."""


def _normalise(values: dict[int, float]) -> dict[int, float]:
    """Min-max to [0, 1] over the winsorised range; degenerate spread is 0.5.

    The plain min-max this replaced made the grid a monochrome smear. The
    optimiser floors a team parameter at exp(-3), and one relegation-bound club
    sitting on that floor owned an end of the scale on its own: every team
    anyone was actually choosing between crowded into the top half, so the
    colour said nothing about the difference between a good fixture and a
    middling one.

    Clamping the ends at the 5th and 95th percentile first spends the range on
    the middle of the league instead. Outliers do not disappear — they clamp to
    0 or 1, which is what they mean anyway.

    The percentiles round *inward* to a real observation. Interpolating, the
    default, puts the 5th percentile of twenty teams between the lowest and the
    second lowest — so a single value far enough out still drags the bound most
    of the way down to itself, which is the whole problem again.

    A NaN parameter — a club the fit could not place — scores 0.5, the same as
    a league with no spread at all. Left alone it arrives in the JSON body as a
    bare ``NaN``, which no JSON parser accepts: one unfittable club took the
    whole matrix down rather than one cell.
    """
    if not values:
        return {}
    series = pd.Series(list(values.values()), dtype=float)
    lo = series.quantile(WINSOR_Q, interpolation="higher")
    hi = series.quantile(1 - WINSOR_Q, interpolation="lower")
    if not hi > lo:
        # Too few teams, or too tight a cluster, for the percentiles to
        # separate: fall back to the full range before giving up on it.
        lo, hi = series.min(), series.max()
    if not hi > lo:
        return {code: 0.5 for code in values}
    return {code: (0.5 if v != v
                   else min(max((v - lo) / (hi - lo), 0.0), 1.0))
            for code, v in values.items()}


def _team_model():
    if not persistence.model_exists("team"):
        return None
    model = persistence.load_model("team")
    attack = getattr(model, "attack_", None)
    defence = getattr(model, "defence_", None)
    # A plain TeamModel is the alternative head and has neither: the same
    # getattr seam set_pieces.attack_multipliers uses.
    if not attack or not defence:
        return None
    return model


@router.get("/fixtures/matrix", response_model=FixtureMatrix)
def matrix(from_: int | None = Query(None, alias="from"),
           n: int = Query(6, ge=1, le=20)) -> FixtureMatrix:
    if not (store.exists("live/teams.parquet")
            and store.exists("live/fixtures_all.parquet")):
        return EMPTY
    model = _team_model()
    if model is None:
        return EMPTY

    teams = store.load("live/teams.parquet")
    fixtures = store.load("live/fixtures_all.parquet")
    code_of = {int(t): int(c) for t, c in zip(teams["team_id"], teams["code"])}
    short_of = {int(c): str(s)
                for c, s in zip(teams["code"], teams["short_name"])}

    upcoming = fixtures[~fixtures["finished"].astype(bool)].copy()
    gws = sorted(int(g) for g in upcoming["gw"].dropna().unique())
    if from_ is not None:
        gws = [g for g in gws if g >= int(from_)]
    gws = gws[:n]
    if not gws:
        return EMPTY
    upcoming = upcoming[upcoming["gw"].isin(gws)]

    # exp() of the log parameters first, so the normalisation runs on the
    # strengths the model actually multiplies rather than on their logs.
    # A bigger defence parameter means the club concedes more, so its negation
    # is "how mean is this defence" — the axis an attacker's fixture is hard on.
    #
    # Restricted to the codes the current teams table lists. A trained model
    # keeps parameters for clubs that have since been relegated, and a code
    # nobody in this league can face has no business setting an end of the
    # scale for the twenty who can.
    live_codes = {int(c) for c in teams["code"]}
    attack_strength = _normalise(
        {int(c): math.exp(float(v)) for c, v in model.attack_.items()
         if int(c) in live_codes})
    defence_strength = _normalise(
        {int(c): -math.exp(float(v)) for c, v in model.defence_.items()
         if int(c) in live_codes})
    # Named for the cell field each one fills, not for the dict it is read out
    # of. Every score runs easy-to-hard, 0 green and 1 rust: a cell's *attack*
    # score is how mean the opponent's defence is, so a leaky opponent scores
    # low and it is defence_strength that backs it. They are both 0.5, but a
    # reader who trusts the names should be able to.
    fallback_attack = 0.5
    fallback_defence = 0.5

    cells: dict[int, list[MatrixCell]] = {int(c): [] for c in teams["code"]}
    for fx in upcoming.sort_values("gw").itertuples():
        home = code_of.get(int(fx.home_id))
        away = code_of.get(int(fx.away_id))
        if home is None or away is None:
            continue
        for own, opp, at_home in ((home, away, True), (away, home, False)):
            if own not in cells:
                continue
            cells[own].append(MatrixCell(
                gw=int(fx.gw), opponent=short_of.get(opp, ""), home=at_home,
                attack=round(defence_strength.get(opp, fallback_attack), 3),
                defence=round(attack_strength.get(opp, fallback_defence), 3)))

    rows = []
    for team in teams.itertuples():
        mine = cells[int(team.code)]
        rows.append(MatrixTeam(
            code=int(team.code), name=str(team.name),
            short_name=str(team.short_name), cells=mine,
            mean_attack=round(
                sum(c.attack for c in mine) / len(mine), 3) if mine else 0.0,
            mean_defence=round(
                sum(c.defence for c in mine) / len(mine), 3) if mine else 0.0))
    rows.sort(key=lambda t: t.mean_attack)
    return FixtureMatrix(gws=gws, teams=rows, source="dixon_coles")


@router.get("/fixtures/outlook", response_model=FixtureOutlook)
def outlook(from_: int | None = Query(None, alias="from")) -> FixtureOutlook:
    """Doubles and blanks in the season ahead (v10b §F2a).

    Read-only over the published fixture list — this reports what FPL has
    scheduled and projects nothing. Today that means thirty-eight ordinary
    gameweeks and an honest empty state, which is the case this endpoint is
    written for rather than the case it tolerates.

    The two files degrade **independently**: without the fixture list there is
    nothing to say and the payload says so; without the teams snapshot the
    counts are still true and only the short names are missing, so the answer
    is kept and ``teams_known`` records what happened. Every failure is a 200
    with a ``note``.
    """
    if not store.exists("live/fixtures_all.parquet"):
        return FixtureOutlook(
            note="No fixture list on disk yet — run the refresh-data job.")
    try:
        fixtures = store.load("live/fixtures_all.parquet")
    except Exception as exc:  # noqa: BLE001 — a planning card never 500s
        return FixtureOutlook(note=f"Fixture list unreadable ({exc}).")

    code_of: dict[int, int] | None = None
    short_of: dict[int, str] = {}
    note: str | None = None
    try:
        teams = store.load("live/teams.parquet")
        code_of = {int(t): int(c)
                   for t, c in zip(teams["team_id"], teams["code"])}
        short_of = {int(c): str(s)
                    for c, s in zip(teams["code"], teams["short_name"])}
    except Exception:  # noqa: BLE001
        note = ("No teams snapshot — the counts are the published fixture "
                "list's own, but the clubs are named by team id.")

    # Default: the season *ahead*. A chip cannot be spent on a gameweek that
    # has been played, so the planner's question starts at the first
    # unfinished week. An explicit ``from`` overrides it.
    start = int(from_) if from_ is not None else _first_unfinished(fixtures)
    weeks = season_outlook(fixtures, code_of, start)

    rows = [
        OutlookWeek(
            gw=w["gw"], fixtures=w["fixtures"],
            doubles=[OutlookTeam(code=c, short_name=short_of.get(c))
                     for c in w["doubles"]],
            blanks=[OutlookTeam(code=c, short_name=short_of.get(c))
                    for c in w["blanks"]])
        for w in weeks]
    has_doubles = any(r.doubles for r in rows)
    has_blanks = any(r.blanks for r in rows)
    if note is None and rows and not (has_doubles or has_blanks):
        note = ("No doubles or blanks are scheduled yet — rearrangements "
                "usually start appearing around the cup rounds.")
    return FixtureOutlook(from_gw=start, weeks=rows, has_doubles=has_doubles,
                          has_blanks=has_blanks,
                          teams_known=code_of is not None, note=note)


def _first_unfinished(fixtures: pd.DataFrame) -> int | None:
    """The earliest gameweek with an unplayed fixture, or None.

    ``None`` rather than 1 when the column is missing or every match is done:
    the honest answer to "which gameweek does the season ahead start in" on a
    frame that cannot say is "we do not know", and ``season_outlook`` reads it
    as "no slice".
    """
    try:
        if "finished" not in fixtures.columns:
            return None
        left = fixtures[~fixtures["finished"].astype(bool)]
        gws = pd.to_numeric(left["gw"], errors="coerce").dropna()
        return int(gws.min()) if not gws.empty else None
    except Exception:  # noqa: BLE001
        return None
