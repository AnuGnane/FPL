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

from fastapi import APIRouter, Query

from gaffer.data import store
from gaffer.models import persistence
from gaffer.web.schemas import FixtureMatrix, MatrixCell, MatrixTeam

router = APIRouter(prefix="/api", tags=["fixtures"])

EMPTY = FixtureMatrix(gws=[], teams=[], source="none")


def _normalise(values: dict[int, float]) -> dict[int, float]:
    """Min-max to [0, 1]; a degenerate spread is 0.5 for everyone."""
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if not hi > lo:
        return {code: 0.5 for code in values}
    return {code: (v - lo) / (hi - lo) for code, v in values.items()}


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
    attack_strength = _normalise(
        {int(c): math.exp(float(v)) for c, v in model.attack_.items()})
    defence_strength = _normalise(
        {int(c): -math.exp(float(v)) for c, v in model.defence_.items()})
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
                attack=round(defence_strength.get(opp, fallback_defence), 3),
                defence=round(attack_strength.get(opp, fallback_attack), 3)))

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
