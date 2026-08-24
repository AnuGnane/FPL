"""Player browser and the "why 6.8?" explainability endpoint.

Both read only what ``advise`` persisted: the candidate pool from the solve
state, the per-fixture breakdown from the components parquet, and the
bootstrap snapshots. No model is loaded and no request is made.
"""

from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter, Query

from gaffer.artifacts import (latest_gw, load_components, load_snapshot,
                              load_solve_state)
from gaffer.errors import GafferError
from gaffer.web.schemas import (Component, FixtureExplain, MinutesOutput,
                                NextFixture, OddsInfluence, PlayerExplain,
                                PlayerRow)

router = APIRouter(prefix="/api/players", tags=["players"])

UNAVAILABLE_STATUS = {"i", "s", "u", "n", "d"}
"""Injured / suspended / unavailable / not in squad / doubtful.

The same set ``models.minutes.apply_availability`` damps minutes for, so the
badge in the browser and the number in the EP agree about who is flagged; the
``news`` and ``chance_of_playing`` fields carry how bad it is.
"""

SORTS = {"ep_next": ("ep_next", False), "ep_horizon": ("ep_horizon", False),
         "price": ("price", False), "ownership": ("ownership", False),
         "league_eo": ("league_eo", False), "name": ("name", True)}


def _opt_int(value) -> int | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return int(value)


def _opt_float(value) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return round(float(value), 4)


def _state():
    gw = latest_gw()
    if gw is None:
        raise GafferError("no candidate pool yet — run `gaffer advise` first")
    return load_solve_state(gw)


@router.get("", response_model=list[PlayerRow])
def players(position: str | None = None, team: int | None = None,
            search: str | None = None,
            sort: str = Query("ep_next", pattern="|".join(SORTS))
            ) -> list[PlayerRow]:
    state = _state()
    snapshot = load_snapshot("live/players.parquet")
    teams = load_snapshot("live/teams.parquet")
    team_name = dict(zip(teams["code"], teams["name"]))
    pool = state.pool
    first_gw = state.gws[0]
    ep_next = {int(r.code): float(r.ep_raw) for r in pool.itertuples()
               if int(r.gw) == first_gw}
    ep_horizon = pool.groupby("code")["ep_raw"].sum().to_dict()
    owned = {int(c) for c in state.owned_codes}

    rows = []
    for r in snapshot.itertuples():
        code = int(r.code)
        if code not in ep_horizon:
            continue                       # not a candidate this week
        status = str(r.status)
        rows.append(PlayerRow(
            code=code, element=int(r.element), name=str(r.name),
            position=str(r.position), team_code=int(r.team_code),
            team_name=str(team_name.get(int(r.team_code), "")),
            price=round(int(r.now_cost) / 10, 1),
            ep_next=round(ep_next.get(code, 0.0), 2),
            ep_horizon=round(float(ep_horizon[code]), 2),
            ownership=float(r.selected_by_percent or 0.0),
            league_eo=float(state.league_eo.get(code, 0.0)),
            available=status not in UNAVAILABLE_STATUS,
            status=status, news=str(r.news or ""),
            chance_of_playing=_opt_float(r.chance_of_playing),
            penalties_order=_opt_int(r.penalties_order),
            free_kicks_order=_opt_int(r.direct_freekicks_order),
            corners_order=_opt_int(
                r.corners_and_indirect_freekicks_order),
            in_squad=code in owned))

    if position:
        rows = [row for row in rows if row.position == position.upper()]
    if team is not None:
        rows = [row for row in rows if row.team_code == team]
    if search:
        needle = search.lower()
        rows = [row for row in rows if needle in row.name.lower()]
    key, ascending = SORTS.get(sort, SORTS["ep_next"])
    rows.sort(key=lambda row: getattr(row, key), reverse=not ascending)
    return rows


COMPONENT_LABELS = [
    ("Minutes", ["ep_minutes"]),
    ("Attacking", ["ep_goals", "ep_assists"]),
    ("Clean sheet", ["ep_cs"]),
    ("Goals conceded", ["ep_gc"]),
    ("Saves", ["ep_saves"]),
    ("Defensive contribution", ["ep_defcon"]),
    ("Bonus", ["ep_bonus"]),
    ("Cards", ["ep_cards"]),
    ("Penalty saves", ["ep_pensave"]),
]


@router.get("/{code}/explain", response_model=PlayerExplain)
def explain(code: int) -> PlayerExplain:
    state = _state()
    comp = load_components(state.gw)
    mine = comp[comp["code"] == code]
    if mine.empty:
        raise GafferError(
            f"no component breakdown for player {code} — they were outside "
            f"this week's candidate pool")

    fixtures = []
    for row in mine.sort_values("gw").itertuples():
        fixtures.append(FixtureExplain(
            gw=int(row.gw), opponent=str(row.opp_name),
            home=bool(row.was_home),
            kickoff_time=None if pd.isna(row.kickoff_time)
            else str(row.kickoff_time),
            components=[Component(label=label,
                                  points=round(sum(float(getattr(row, c))
                                                   for c in cols), 2))
                        for label, cols in COMPONENT_LABELS],
            minutes=MinutesOutput(p_play=round(float(row.p_play), 3),
                                  p60=round(float(row.p60), 3)),
            calibration_delta=round(float(row.cal_delta), 2),
            odds=OddsInfluence(
                weight=round(float(row.odds_weight), 2),
                e_goals_against=_opt_float(row.odds_e_goals_against),
                p_cs_model=round(float(row.p_cs_model), 3),
                p_cs_blended=round(float(row.p_cs), 3),
                e_gc_model=round(float(row.e_gc_model), 3),
                e_gc_blended=round(float(row.e_gc), 3)),
            ep=round(float(row.ep), 2)))

    snapshot = load_snapshot("live/players.parquet")
    rows = snapshot[snapshot["code"] == code]
    if rows.empty:
        raise GafferError(f"player {code} not in the saved snapshot — run "
                          "`gaffer advise`")
    me = rows.iloc[0]
    teams = load_snapshot("live/teams.parquet")
    team_name = dict(zip(teams["code"], teams["name"]))
    id_to_code = dict(zip(teams["team_id"], teams["code"]))
    all_fixtures = load_snapshot("live/fixtures_all.parquet")
    upcoming = all_fixtures[(all_fixtures["gw"] >= state.gw)
                            & ~all_fixtures["finished"]].sort_values("gw")
    next_three = []
    for fx in upcoming.itertuples():
        for side, opp, home in ((fx.home_id, fx.away_id, True),
                                (fx.away_id, fx.home_id, False)):
            if int(side) != int(me["team_id"]):
                continue
            next_three.append(NextFixture(
                gw=int(fx.gw),
                opponent=str(team_name.get(id_to_code.get(int(opp)), "")),
                home=home))
        if len(next_three) >= 3:
            break

    first_gw = state.gws[0]
    ep_next = float(mine[mine["gw"] == first_gw]["ep"].sum())
    return PlayerExplain(
        code=code, name=str(me["name"]), position=str(me["position"]),
        team_name=str(team_name.get(int(me["team_code"]), "")),
        ep_next=round(ep_next, 2), fixtures=fixtures,
        next_fixtures=next_three[:3],
        set_pieces={"penalties": _opt_int(me["penalties_order"]),
                    "free_kicks": _opt_int(me["direct_freekicks_order"]),
                    "corners": _opt_int(
                        me["corners_and_indirect_freekicks_order"])})
