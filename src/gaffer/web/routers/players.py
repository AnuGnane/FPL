"""Player browser and the "why 6.8?" explainability endpoint.

Both read only what ``advise`` persisted: the candidate pool from the solve
state, the per-fixture breakdown from the components parquet, and the
bootstrap snapshots. No model is loaded and no request is made.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

import pandas as pd
from fastapi import APIRouter, Query

from gaffer.artifacts import (latest_gw, load_components, load_snapshot,
                              load_solve_state)
from gaffer.config import serving_config
from gaffer.data.field import field_eo_trend, latest_field_eo
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


def _trend_table(gw: int | None, season: str) -> dict[int, dict]:
    """v12 §3.3's trend, or an empty map. Display, so it never raises."""
    try:
        return field_eo_trend(season, gw)
    except Exception as exc:  # noqa: BLE001 — a column is not worth a 500
        print(f"players: field EO trend unreadable ({exc})")
        return {}


def _trend_fields(trend: dict[int, dict], element: int) -> dict:
    """The two additive fields for one element.

    ``None`` on both whenever there is no trend, rather than falling back to
    ``eo_last``: the row already carries ``field_eo``, and repeating it under
    a name that says "deadline" would make a projection out of a measurement.
    """
    cell = trend.get(int(element)) or {}
    if not cell.get("trend_available"):
        return {"field_eo_deadline": None, "field_eo_delta": None}
    return {"field_eo_deadline": cell["deadline_eo"],
            "field_eo_delta": cell["delta"]}


def set_piece_orders(team_of: Mapping[int, int] | None = None
                     ) -> dict[str, dict[int, int | None]]:
    """``{kind: {code: served order}}`` — every order the file decides.

    v12 W4 §5.4, club-aware by the 2026-09-03 ruling, and the same rule the
    EP hook applies in ``set_pieces.pen_table``: a club's queue is exactly
    what the file lists for that club, so a listed code takes the file's rank
    and an *unlisted teammate* is served ``None`` — no kind of taker — however
    FPL has him ordered. Without that, one line naming a new taker leaves the
    incumbent at FPL's order 1 and the panel shows two number ones.

    ``team_of`` is ``{code: team_code}``, read from the snapshot the caller is
    already serving; the club never comes from the table header, which is a
    comment for the reader. Pass nothing and no club is identified, so only
    the codes the file names appear — which is what a caller with no snapshot
    in hand (the degradation rail) should see.

    **Only ``penalties`` reaches expected points.** The other two kinds change
    the number this endpoint serves and nothing else: there is no free-kick or
    corner term in the model, and this function does not invent one.
    """
    from gaffer.data.set_piece_overrides import (SET_PIECE_KINDS,
                                                 load_set_piece_overrides)

    out: dict[str, dict[int, int | None]] = {k: {} for k in SET_PIECE_KINDS}
    for tables in load_set_piece_overrides().values():
        for kind, order in tables.items():
            for code, rank in order.items():
                # Keep-first on a code two clubs both name, matching
                # ``penalty_order_overrides`` so the badge and the EP term
                # cannot disagree about a mid-window transfer typed twice.
                out[kind].setdefault(int(code), int(rank))
    # A row whose code or club is not a number is skipped rather than coerced:
    # `int(NaN)` raises, and a snapshot with one club missing would take the
    # whole endpoint down over a display fact. A row with no club identifies
    # none, so it can neither define a queue nor be demoted from one.
    clubs_of = {int(code): int(team) for code, team in (team_of or {}).items()
                if pd.notna(code) and pd.notna(team)}
    if clubs_of:
        for served in out.values():
            clubs = {clubs_of[c] for c in served if c in clubs_of}
            for code, team in clubs_of.items():
                if team in clubs and code not in served:
                    served[code] = None
    return out


def _manual_from_orders(orders: dict[str, dict[int, int | None]]
                        ) -> dict[int, list[str]]:
    """``{code: [kinds whose served order came from the file]}``.

    Includes the demoted: a teammate served ``None`` because the file left him
    out has an order that came from the file just as much as the man it
    named, and a blank with no badge reads as "FPL has nothing to say", which
    is the opposite of what happened. Kinds are sorted so the badge does not
    reshuffle between reloads.
    """
    out: dict[int, list[str]] = {}
    for kind, served in orders.items():
        for code in served:
            out.setdefault(int(code), []).append(str(kind))
    return {code: sorted(kinds) for code, kinds in sorted(out.items())}


def _served_set_pieces(orders: dict[str, dict[int, int | None]], code: int,
                       me) -> dict[str, int | None]:
    """The explain panel's three orders: the file's where it has a word.

    Keyed by the panel's own names (``free_kicks``) rather than FPL's column
    names, and reading the same ``orders`` map the table row reads, so the
    modal and the row that opened it cannot disagree.
    """
    pairs = (("penalties", "penalties", "penalties_order"),
             ("free_kicks", "direct_free_kicks", "direct_freekicks_order"),
             ("corners", "corners", "corners_and_indirect_freekicks_order"))
    return {shown: (orders[kind][code] if code in orders[kind]
                    else _opt_int(me[column]))
            for shown, kind, column in pairs}


def set_piece_manual(team_of: Mapping[int, int] | None = None
                     ) -> dict[int, list[str]]:
    """``{code: [kinds the user overrode]}`` — the badge, and nothing else.

    A display fact. It never enters an expected point: only ``penalties``
    reaches EP at all (through ``set_pieces.pen_table``'s hook), and this map
    exists so a user who corrected a corner taker can see that his correction
    took.

    An empty list in the file names nobody and therefore marks nobody — it
    identifies no club either, so it demotes nobody: it records that you
    checked and found nobody, and the badge says "this row is your
    correction", which a row nobody was named for is not.
    """
    return _manual_from_orders(set_piece_orders(team_of))


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
    # `serving_config` rather than `load_config`: this is a per-row serve path
    # and it is exactly the seam that reader exists for — cached, so the
    # explorer does not re-read a TOML file per request, and never raising, so
    # a clone with no config.toml still renders. The cost is that a
    # `current_season` edit needs a restart to reach this page, which is the
    # documented trade and is what `/api/health`'s uncached read is for.
    #
    # v12 W2 §3.3: the season is a local rather than an inline read, because
    # two calls now need it and two inline reads are two answers that can
    # disagree. An unreadable config leaves it empty, which no banked row
    # matches — the same empty map the bare `except` below produced.
    try:
        season = str(serving_config().current_season)
    except Exception:  # noqa: BLE001
        season = ""
    try:
        field_eo = latest_field_eo(season=season)
    except Exception:  # noqa: BLE001
        field_eo = {}
    # v12 W2 §3.3 (specs/2026-09-01-gaffer-v12-program-design.md, plan A5).
    #
    # `None` rather than `first_gw`: the upcoming gameweek is the one whose
    # picks are not public yet, so it is routinely *absent* from the EO log
    # and keying to it would blank the column on precisely the days the page
    # is read most. `None` means "the newest gameweek the log actually has",
    # and `deadline_eo` projects that newest sample one gameweek forward by
    # construction (A4) — which is this page's upcoming week.
    trend = _trend_table(None, season)
    # v12 W4 §5.4. Once per request, not once per row: the file is small but
    # it is a disk read, and a hundred players is a hundred reads. The rows
    # then take a dict lookup each.
    #
    # Club-aware by the 2026-09-03 ruling, which needs `{code: team_code}` —
    # so the snapshot the endpoint is already serving supplies the clubs, and
    # the badge is derived from the same orders it marks rather than computed
    # a second way. That is the whole point: the badge marks a served order
    # that came from the file, so the two cannot drift apart.
    orders = set_piece_orders(dict(zip(snapshot["code"],
                                       snapshot["team_code"])))
    manual = _manual_from_orders(orders)
    pens, kicks, corners = (orders["penalties"], orders["direct_free_kicks"],
                            orders["corners"])

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
            **_trend_fields(trend, int(r.element)),
            field_class=field_class(code in owned,
                                    _opt_float(me.get("eo"))),
            available=status not in UNAVAILABLE_STATUS,
            status=status, news=str(r.news or ""),
            chance_of_playing=_opt_float(r.chance_of_playing),
            # The file's word where it has one, FPL's otherwise. `in` rather
            # than `.get(code)`: a demoted teammate is served `None`, and
            # `None` here means "the file cleared him", not "the file is
            # silent" — which is exactly the distinction a default would eat.
            penalties_order=(pens[code] if code in pens
                             else _opt_int(r.penalties_order)),
            free_kicks_order=(kicks[code] if code in kicks
                              else _opt_int(r.direct_freekicks_order)),
            corners_order=(corners[code] if code in corners
                           else _opt_int(
                               r.corners_and_indirect_freekicks_order)),
            set_piece_manual=manual.get(code, []),
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
    # The whole snapshot, not just his row: the club rule needs his teammates
    # to know whether the file spoke about his club at all.
    orders = set_piece_orders(dict(zip(snapshot["code"],
                                       snapshot["team_code"])))
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
        # v12 W4 §5.4. The same orders the table serves, from the same
        # loader: a modal that disagreed with the row that opened it would be
        # a worse bug than the one the override fixes.
        set_pieces=_served_set_pieces(orders, code, me),
        set_pieces_manual=_manual_from_orders(orders).get(code, []))
