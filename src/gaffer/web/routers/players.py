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
from gaffer.config import load_config
from gaffer.data.field import latest_field_eo
from gaffer.errors import GafferError
from gaffer.uncertainty import band_for, shipped_table, xmins_by_player_gw
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


def _last4() -> dict[int, list[int]]:
    """``{code: [points]}`` for the last four finished gameweeks."""
    from gaffer.data import store

    if not store.exists("live/player_gw.parquet"):
        return {}
    frame = store.load("live/player_gw.parquet")
    if frame.empty:
        return {}
    frame = frame.sort_values("gw")
    out: dict[int, list[int]] = {}
    for code, rows in frame.groupby("code"):
        out[int(code)] = [int(p) for p in rows["total_points"].tail(4)]
    return out


def _xmins_first_gw(gw: int) -> dict[int, float]:
    """``{code: expected minutes}`` for the horizon's first gameweek.

    Pure display, so an absent or unreadable components parquet is an empty
    map rather than an exception: the explorer must render on a clone that has
    solved but never banked a breakdown, and a player list with no bands on it
    is a correct degraded page.
    """
    try:
        comp = load_components(gw)
    except Exception as exc:  # noqa: BLE001 — a band is never worth a 500
        print(f"players explorer: no component breakdown for bands ({exc})")
        return {}
    try:
        return {code: xm for (code, g), xm in
                xmins_by_player_gw(comp).items() if int(g) == int(gw)}
    except Exception as exc:  # noqa: BLE001
        print(f"players explorer: component breakdown unusable ({exc})")
        return {}


FIELD_HIGH = 40.0
FIELD_LOW = 15.0
"""Effective-ownership percent that counts as the field being *on* a player,
and the level below which it is not.

Two thresholds rather than one so the middle of the distribution — the third
of the game that is neither a template pick nor a punt — carries no label at
all. Labelling everything is how a classification stops meaning anything."""


def field_class(owned: bool, eo: float | None) -> str | None:
    """Where this player puts you against the field.

    * ``shield`` — you own him and so does the field: he cannot cost you rank.
    * ``sword`` — you own him and the field does not: every point is a gain.
    * ``threat`` — the field owns him and you do not: his good week is your
      bad one.

    The fourth quadrant (nobody owns him) is not a position, it is the rest of
    the game, and it gets no label.
    """
    if eo is None:
        return None
    if owned:
        if eo >= FIELD_HIGH:
            return "shield"
        return "sword" if eo <= FIELD_LOW else None
    return "threat" if eo >= FIELD_HIGH else None


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
    last4 = _last4()
    # A4: the band has to bracket the number on the screen, and the number on
    # the screen is the pool's ep_raw — not the components frame's ep. So the
    # frame supplies only xMins and the band is computed on ep_next.
    xmins = _xmins_first_gw(first_gw)
    noise = shipped_table()
    # Pure display: an unreadable log is a missing column, never a 500. The
    # explorer must render on a clone that has never run a scrape.
    #
    # v12 W1 §2.3: seasoned. This call was bare for two cycles and v10b
    # recorded it as a residual — `element` is season-scoped, so after a
    # rollover the largest gameweek in the log is last season's and every row
    # on this page would have carried a different footballer's ownership.
    # `load_config` can raise on a clone with no config.toml, which is why it
    # is inside the try with the read.
    try:
        field_eo = latest_field_eo(season=load_config().current_season)
    except Exception:  # noqa: BLE001
        field_eo = {}

    rows = []
    for r in snapshot.itertuples():
        code = int(r.code)
        if code not in ep_horizon:
            continue                       # not a candidate this week
        status = str(r.status)
        # Resolved once per row rather than three times, now that three fields
        # read out of it.
        me = field_eo.get(int(r.element)) or {}
        band = band_for(round(ep_next.get(code, 0.0), 2), xmins.get(code),
                        table=noise)
        rows.append(PlayerRow(
            code=code, element=int(r.element), name=str(r.name),
            position=str(r.position), team_code=int(r.team_code),
            team_name=str(team_name.get(int(r.team_code), "")),
            price=round(int(r.now_cost) / 10, 1),
            ep_next=round(ep_next.get(code, 0.0), 2),
            ep_horizon=round(float(ep_horizon[code]), 2),
            ownership=float(r.selected_by_percent or 0.0),
            league_eo=float(state.league_eo.get(code, 0.0)),
            field_eo=_opt_float(me.get("eo")),
            # v11 §F2 (plan A2). ``latest_field_eo`` has always returned the
            # error and the sample size beside the figure and this row has
            # always dropped them. ``.get``, never ``.get(k, 0.0)``: a standard
            # error of zero is a claim of perfect precision from a sample of a
            # few hundred entries.
            field_se=_opt_float(me.get("se")),
            field_n=_opt_int(me.get("n")),
            field_class=field_class(code in owned,
                                    _opt_float(me.get("eo"))),
            available=status not in UNAVAILABLE_STATUS,
            status=status, news=str(r.news or ""),
            chance_of_playing=_opt_float(r.chance_of_playing),
            penalties_order=_opt_int(r.penalties_order),
            free_kicks_order=_opt_int(r.direct_freekicks_order),
            corners_order=_opt_int(
                r.corners_and_indirect_freekicks_order),
            in_squad=code in owned,
            last4=last4.get(code, []),
            ep_lo=None if band is None else band.ep_lo,
            ep_hi=None if band is None else band.ep_hi,
            p_haul=None if band is None else band.p_haul,
            p_blank=None if band is None else band.p_blank))

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


def _cell(row, col: str):
    """One component cell as a float, or ``None`` when it is not really there.

    Two ways a column goes missing, and both end here. A frame banked before
    the column existed carries no attribute at all — ``itertuples`` simply has
    no such field. A frame put through ``save_components`` after the column was
    added carries it as all-NaN. Neither is a number, and neither is worth a
    500 over: ``routers/components.py`` already defaults its way past exactly
    this, and an explain panel is no more entitled to a crash than a breakdown.
    """
    value = getattr(row, col, None)
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(out) else out


def _cell_or(row, col: str, default: float) -> float:
    value = _cell(row, col)
    return default if value is None else value


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
        # A term whose every column is absent is dropped rather than printed
        # as 0.00: "Saves: 0.00" is a claim about a goalkeeper the frame never
        # made. A term with *some* columns present keeps the ones it has and
        # treats the rest as the zero they contributed to ``ep``.
        components = []
        for label, cols in COMPONENT_LABELS:
            cells = [_cell(row, c) for c in cols]
            if all(cell is None for cell in cells):
                continue
            components.append(Component(
                label=label,
                points=round(sum(c for c in cells if c is not None), 2)))

        p_play = _cell(row, "p_play")
        fixtures.append(FixtureExplain(
            gw=int(row.gw), opponent=str(row.opp_name),
            home=bool(row.was_home),
            kickoff_time=None if pd.isna(row.kickoff_time)
            else str(row.kickoff_time),
            components=components,
            # p_play stays None when it is missing: the schema asks for that
            # explicitly, because 0.0 there reads as "expected not to play".
            # p60 can now say "unknown" too — v11's fix-round widened it on
            # `MinutesOutput` — but this payload's fallback is left where it
            # was: the explain modal's `_cell_or` reads every one of its
            # numbers this way, and moving one of them alone is a change to a
            # shipped view that no rail in this cycle asked for. Recorded.
            minutes=MinutesOutput(
                p_play=None if p_play is None else round(p_play, 3),
                p60=round(_cell_or(row, "p60", 0.0), 3)),
            # A frame with no calibration column was not calibrated, and 0.0
            # is precisely what "no adjustment" means here.
            calibration_delta=round(_cell_or(row, "cal_delta", 0.0), 2),
            odds=OddsInfluence(
                # Likewise a weight of 0: a frame banked before the odds blend
                # existed gave the odds no weight. The blended figures then
                # fall back to the model's own, which is what a zero-weight
                # blend evaluates to anyway.
                weight=round(_cell_or(row, "odds_weight", 0.0), 2),
                e_goals_against=_opt_float(
                    getattr(row, "odds_e_goals_against", None)),
                p_cs_model=round(_cell_or(row, "p_cs_model", 0.0), 3),
                p_cs_blended=round(
                    _cell_or(row, "p_cs", _cell_or(row, "p_cs_model", 0.0)), 3),
                e_gc_model=round(_cell_or(row, "e_gc_model", 0.0), 3),
                e_gc_blended=round(
                    _cell_or(row, "e_gc", _cell_or(row, "e_gc_model", 0.0)), 3)),
            ep=round(_cell_or(row, "ep", 0.0), 2)))

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
