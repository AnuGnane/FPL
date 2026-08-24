"""Weekly advice: everything from a cold start to a JSON payload.

This is the one place the whole pipeline is wired end to end — refresh the
live season, build the upcoming-fixture rows, predict every component,
assemble expected points, solve the plan, and annotate it with chips,
differentials and price alerts.

Two joins in here deserve their attention, because both are wrong in the
obvious way:

* component predictions are stitched **positionally**, not merged. Every
  model's ``predict`` returns one row per input row in input order, and
  ``(code, season_idx, gw)`` is *not* unique in a double gameweek — merging
  on it fans a player's two fixtures out into four rows and doubles their
  expected points.
* the team model genuinely is many-to-one (one team-fixture serves every
  player in that team's squad), so that one *is* a merge — on
  ``(team_code, season_idx, gw, opp_code)``, with ``opp_code`` in the key so
  a double gameweek's two fixtures stay distinct.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from gaffer.api.client import FPLClient
from gaffer.config import Config
from gaffer.data import store
from gaffer.data.bootstrap import (build_events, build_players, build_teams,
                                   next_gw, scoring_table)
from gaffer.data.entry import fetch_my_team
from gaffer.data.league import (effective_ownership, fetch_rival_entries,
                                fetch_rival_picks)
from gaffer.data.live import refresh_live
from gaffer.errors import GafferError
from gaffer.data.odds import OddsClient, odds_frame
from gaffer.features.engineer import build_prediction_frame, feature_columns
from gaffer.league_mode import compute_strategy, tilt_ep, win_probability
from gaffer.models.assemble import apply_calibration, assemble_ep, ep_matrix
from gaffer.models.components import card_penalty
from gaffer.models.minutes import apply_availability
from gaffer.models.persistence import load_model, model_exists
from gaffer.models.team import (ODDS_AGAINST_COL, add_team_rolling,
                                blend_team_odds)
from gaffer.models.train import load_training_frame
from gaffer.optimize.chips import evaluate_chips, wildcard_now_assessment
from gaffer.optimize.differentials import (captain_table, threat_board,
                                           transfer_alternatives)
from gaffer.optimize.milp import SolveInput, build_pool, solve_plan
from gaffer.prices import price_alerts

REPORTS = Path("reports")
MODEL_NAMES = ["minutes", "team", "attacking", "defcon", "saves", "bonus"]

CHIPS = ["wildcard", "freehit", "bboost", "3xc"]
FIRST_HALF_LAST_GW = 19
"""Last gameweek of the first chip half — the GW1 set expires after it."""

LAST_GW = 38

# Fallbacks for a team-fixture the team model could not score (a promoted
# side with no rolling history, say): roughly a league-average clean sheet
# rate and goals conceded, so the row still produces a finite EP.
DEFAULT_P_CS = 0.25
DEFAULT_E_GC = 1.4

TEAM_BASE_COLS = ["season_idx", "gw", "kickoff_time", "code", "opp_code",
                  "home", "gf", "ga", "cs"]


@dataclass
class Advice:
    gw: int
    deadline: str
    buys: list[dict]
    sells: list[dict]
    hits: int
    xi: list[dict]
    bench: list[dict]
    captain: dict
    vice: dict
    captain_options: list[dict]
    chip_table: list[dict]
    wildcard_now: dict | None
    alternatives: list[dict]
    threats: list[dict]
    price_alerts: list[dict]
    expected_pts: float
    plan_by_gw: list[dict] = field(default_factory=list)
    # League strategy is optional: no league configured, an API failure or a
    # league with no rivals all leave these empty, and the advice is then the
    # plain points-max advice v1 produced.
    strategy: dict | None = None
    win_probs: list = field(default_factory=list)
    # "weekly" (a squad exists, transfers are the decision) or
    # "initial_squad" (GW1: there is no squad yet, so the 15 buys *are* the
    # advice). Appended last and defaulted so payloads written before it —
    # and every positional construction — still load.
    mode: str = "weekly"


INITIAL_BUDGET = 1000
"""GW1 budget in 0.1m units: 100.0m, all of it in the bank."""

INITIAL_FREE_TRANSFERS = 15
"""Building the first squad is 15 transfers and no hits."""


def initial_squad_state(gws: list[int]) -> tuple[SolveInput, pd.DataFrame]:
    """The GW1 solve state: nothing owned, full budget, transfers free.

    Returns the ``SolveInput`` and the empty picks frame ``build_pool`` needs
    (it reads only ``code`` and ``sell``, so an empty two-column frame leaves
    the owned set empty and prices every player at ``now_cost``). Same shape
    the backtest uses for its own first build.
    """
    return (SolveInput(owned_codes=[], bank=INITIAL_BUDGET,
                       free_transfers=INITIAL_FREE_TRANSFERS, gws=gws),
            pd.DataFrame(columns=["code", "sell"]))


SETPIECE_ORDER_COLS = ["penalties_order", "direct_freekicks_order",
                       "corners_and_indirect_freekicks_order"]


def future_fixture_frame(fixtures: pd.DataFrame, players: pd.DataFrame,
                         teams: pd.DataFrame, gws: list[int],
                         season_idx: int) -> pd.DataFrame:
    """One row per player per upcoming fixture in ``gws``.

    fixtures: [gw, home_id, away_id, kickoff_time] (team ids). A double
    gameweek therefore yields two rows for the same player, which is exactly
    what the downstream sum over fixtures needs.
    """
    code_of = dict(zip(teams["team_id"], teams["code"]))
    fx = fixtures[fixtures["gw"].isin(gws)]
    rows = []
    for m in fx.itertuples():
        for side, opp, home in ((m.home_id, m.away_id, True),
                                (m.away_id, m.home_id, False)):
            side_players = players[players["team_id"] == side]
            for p in side_players.itertuples():
                rows.append({"code": p.code, "element": p.element,
                             "name": p.name, "position": p.position,
                             "team_code": p.team_code,
                             "opp_code": code_of[opp], "was_home": home,
                             "gw": m.gw, "season_idx": season_idx,
                             "kickoff_time": m.kickoff_time,
                             # Set-piece orders live only on the players
                             # frame; carry them so add_setpiece can derive
                             # pen_taker/setpiece_taker for future rows.
                             **{f: getattr(p, f, float("nan"))
                                for f in SETPIECE_ORDER_COLS}})
    return pd.DataFrame(rows)


def chips_available_for(chips_by_gw: dict[int, str], gw: int) -> list[str]:
    """Chips still playable in ``gw``, given what has been used.

    2026/27 gives two of every chip: one set expires after GW19, a fresh set
    arrives for GW20. So a chip is spent only if it was used in the *same*
    half as the gameweek being planned.
    """
    same_half = (gw <= FIRST_HALF_LAST_GW)
    used = {name for g, name in chips_by_gw.items()
            if (g <= FIRST_HALF_LAST_GW) == same_half}
    return [c for c in CHIPS if c not in used]


def fixture_frame(raw_fixtures: list[dict]) -> pd.DataFrame:
    """API ``/fixtures/`` payload -> [gw, home_id, away_id, kickoff_time,
    home_goals, away_goals, finished]. Rows with no ``event`` (unscheduled
    postponements) are dropped: they belong to no gameweek."""
    rows = [{"gw": f["event"], "home_id": f["team_h"], "away_id": f["team_a"],
             "kickoff_time": f.get("kickoff_time"),
             "home_goals": f.get("team_h_score"),
             "away_goals": f.get("team_a_score"),
             "finished": bool(f.get("finished"))}
            for f in raw_fixtures if f.get("event") is not None]
    return pd.DataFrame(rows)


def save_live_fixtures(fx: pd.DataFrame, teams: pd.DataFrame,
                       season_idx: int) -> pd.DataFrame:
    """Finished fixtures in the canonical history schema, for Elo and the
    team model. Only finished matches: an unplayed row has no result and
    would poison both."""
    code_of = dict(zip(teams["team_id"], teams["code"]))
    done = fx[fx["finished"]].copy()
    out = pd.DataFrame({
        "season_idx": season_idx,
        "gw": done["gw"].astype(int),
        "kickoff_time": done["kickoff_time"],
        "home_code": done["home_id"].map(code_of),
        "away_code": done["away_id"].map(code_of),
        "home_goals": done["home_goals"].astype("Int64").astype(int),
        "away_goals": done["away_goals"].astype("Int64").astype(int),
    })
    store.save(out, "live/fixtures.parquet")
    return out


def _rate_elo(df: pd.DataFrame, elo_final: dict, own_col: str,
              opp_col: str = "opp_elo") -> pd.DataFrame:
    """Rate future rows at the latest Elo. There is no pre-match rating for a
    match that has not happened, so the newest one is the best estimate."""
    df[own_col] = df["team_code"].map(elo_final) if "team_code" in df.columns \
        else df["code"].map(elo_final)
    df[opp_col] = df["opp_code"].map(elo_final)
    df["elo_diff"] = df[own_col] - df[opp_col]
    return df


def build_team_future(tg: pd.DataFrame, future: pd.DataFrame, gws: list[int],
                      season_idx: int, elo_final: dict) -> pd.DataFrame:
    """Team-fixture rows for the horizon, with rolling form from history.

    The rolling features have to be computed over history *and* future
    together — a team's GW+2 form window has to see the GW+1 row ahead of it
    (as NaN, skipped) to line the windows up the way training did. Existing
    rolling columns are dropped from ``tg`` first: recomputing them on a
    frame that already has them would leave duplicate column names, and
    ``df[cols]`` then hands the model a two-column block per feature.
    """
    hist = tg[[c for c in TEAM_BASE_COLS if c in tg.columns]].copy()
    hist["_future"] = False
    fut = (future[["team_code", "opp_code", "was_home", "gw", "season_idx",
                   "kickoff_time"]]
           .drop_duplicates(subset=["team_code", "gw", "opp_code"])
           .rename(columns={"team_code": "code"}))
    fut["home"] = fut["was_home"].astype(float)
    fut = fut.drop(columns=["was_home"])
    fut["_future"] = True
    combined = add_team_rolling(pd.concat([hist, fut], ignore_index=True))
    out = combined[combined["_future"] & combined["gw"].isin(gws)
                   & (combined["season_idx"] == season_idx)].copy()
    out = out.drop(columns=["_future"]).reset_index(drop=True)
    out["team_elo_own"] = out["code"].map(elo_final)
    out["opp_elo"] = out["opp_code"].map(elo_final)
    out["elo_diff"] = out["team_elo_own"] - out["opp_elo"]
    return out


def merge_team_odds(tg_future: pd.DataFrame,
                    odds_df: pd.DataFrame) -> pd.DataFrame:
    """Attach bookmaker odds to the team-future frame, keyed by fixture.

    ``build_team_future`` names the team column ``code``; ``odds_frame`` uses
    ``team_code``. The key is the *fixture* — ``(team, gw, opponent)`` — not
    just ``(team, gw)``: a double gameweek gives a team two rows under one
    ``gw``, so a team-and-gw key fans each of them out into two. Keying by
    opponent keeps the per-fixture prices where they belong.

    Fixtures the feed did not cover land as NaN, which ``blend_team_odds``
    reads as "keep the model's own output".
    """
    return tg_future.merge(
        odds_df,
        left_on=["code", "gw", "opp_code"],
        right_on=["team_code", "gw", "opp_code"], how="left",
    ).drop(columns=["team_code"])


def predict_components(pred_frame: pd.DataFrame, tg_future: pd.DataFrame,
                       players: pd.DataFrame) -> pd.DataFrame:
    """Every component prediction on one row per player-fixture.

    Assembled positionally (see the module docstring): each ``predict``
    returns one row per input row in input order, so ``.values`` lines up
    exactly while a merge on ``(code, season_idx, gw)`` would fan a double
    gameweek out.
    """
    pf = pred_frame.copy().reset_index(drop=True)
    pf["e_cards"] = pf.apply(card_penalty, axis=1)

    minutes = load_model("minutes")
    mp = minutes.predict(pf)
    mp = apply_availability(
        mp, players[["code", "status", "chance_of_playing"]])

    keys = ["code", "season_idx", "gw", "opp_code"]
    comp = pf[keys + ["position", "team_code", "e_cards"]].reset_index(drop=True)
    for col in ["p_play", "p60", "e_min"]:
        comp[col] = mp[col].values
    for name, cols in (("attacking", ["e_goals", "e_assists"]),
                       ("defcon", ["p_defcon"]),
                       ("saves", ["e_saves"]),
                       ("bonus", ["e_bonus"])):
        out = load_model(name).predict(pf)
        for col in cols:
            comp[col] = out[col].values

    tp = load_model("team").predict(tg_future)
    tp["opp_code"] = tg_future["opp_code"].values
    # Blend the market in while tp is still one row per team-fixture: the
    # merge below is many-to-one, so blending after it would apply the same
    # correction once per player in the squad.
    if ODDS_AGAINST_COL in tg_future.columns:
        tp[ODDS_AGAINST_COL] = tg_future[ODDS_AGAINST_COL].values
    tp = blend_team_odds(tp).drop(columns=[ODDS_AGAINST_COL], errors="ignore")
    tp = tp.rename(columns={"code": "team_code"})
    comp = comp.merge(tp, on=["team_code", "season_idx", "gw", "opp_code"],
                      how="left")
    comp["p_cs"] = comp["p_cs"].fillna(DEFAULT_P_CS)
    comp["e_gc"] = comp["e_gc"].fillna(DEFAULT_E_GC)
    return comp


DIFFERENTIAL_EO = 0.3
"""Below this league-EO fraction a buy is an attacking punt on the field."""

TEMPLATE_EO = 0.7
"""At or above it, buying is covering a player the league already owns."""


def transfer_tag(eo_pct: float | None, has_strategy: bool) -> str:
    """Label a buy ``attack`` / ``cover`` / "" by how owned it is in the league.

    ``eo_pct`` is effective ownership in *percent* (captaincy can push it past
    100), and a player nobody owns is simply absent from the EO map. Without a
    strategy there is no league to be different from, so nothing is tagged.
    """
    if not has_strategy:
        return ""
    eo = (eo_pct or 0.0) / 100.0
    if eo < DIFFERENTIAL_EO:
        return "attack"
    return "cover" if eo >= TEMPLATE_EO else ""


def _named(codes: list[int], name_of: dict, ep_by: dict, gw: int) -> list[dict]:
    return [{"code": int(c), "name": name_of.get(c, str(c)),
             "ep": round(float(ep_by.get((c, gw), 0.0)), 2)} for c in codes]


def run_advise(cfg: Config, client: FPLClient | None = None) -> Advice:
    """The whole weekly pipeline, from live refresh to ``reports/``."""
    missing = [n for n in MODEL_NAMES if not model_exists(n)]
    if missing:
        raise SystemExit(
            f"Model '{missing[0]}' missing — run `gaffer train` first.")

    client = client or FPLClient()
    raw = client.get_bootstrap()
    players = build_players(raw)
    teams = build_teams(raw)
    events = build_events(raw)
    gw = next_gw(raw)
    deadline = str(events.loc[events["gw"] == gw, "deadline_time"].iloc[0])
    gws = list(range(gw, min(gw + cfg.horizon, LAST_GW + 1)))
    season_idx = len(cfg.train_seasons)

    refresh_live(client, cfg.current_season, season_idx)
    # Model health has to be scored *after* the refresh: it joins the stored
    # predictions for gw-1 with that gameweek's actuals, and those actuals only
    # land in data/live/player_gw.parquet once refresh_live has pulled them.
    from gaffer.tracking import update_health
    if gw > 1:
        update_health(gw - 1)
    fx = fixture_frame(client.get_fixtures())
    save_live_fixtures(fx, teams, season_idx)

    hist, tg, elo_final = load_training_frame()
    future = future_fixture_frame(fx, players, teams, gws, season_idx)
    # load_training_frame already engineered the features; build_prediction_frame
    # engineers them again over history+future, and pandas happily keeps both
    # copies under one name. A duplicate column turns every df[col] into a
    # two-column frame, so strip the engineered ones before re-deriving them.
    hist_raw = hist.drop(columns=[c for c in feature_columns()
                                  if c in hist.columns])
    pred_frame = build_prediction_frame(hist_raw, future, elo=None,
                                        elo_final=elo_final)
    pred_frame = _rate_elo(pred_frame, elo_final, "team_elo")
    # Bookmaker odds are a best-effort extra: a dead key, a renamed club or a
    # rate limit must degrade the advice, never withhold it.
    odds_df = None
    if cfg.odds_api_key:
        try:
            raw_odds = OddsClient(cfg.odds_api_key).get_epl_odds()
            if raw_odds:
                odds_df = odds_frame(raw_odds, teams, events)
        except Exception as e:  # noqa: BLE001 — odds must never block advice
            print(f"odds unavailable, continuing without: {e}")
    tg_future = build_team_future(tg, future, gws, season_idx, elo_final)
    if odds_df is not None and not odds_df.empty:
        # Banked every week on purpose. Bookmakers price only upcoming
        # fixtures, so no historical row can ever be backfilled from the API;
        # snapshotting each gameweek is the only way a future model could be
        # trained on odds as a feature rather than blended with them after the
        # fact. Nothing reads these yet.
        store.save(odds_df, f"live/odds/gw{gw}.parquet")
        tg_future = merge_team_odds(tg_future, odds_df)

    comp = predict_components(pred_frame, tg_future, players)
    # Optional artifact: model directories trained before calibration existed
    # have no such file, and None means the identity map.
    cal = load_model("calibration") if model_exists("calibration") else None
    ep = ep_matrix(apply_calibration(assemble_ep(comp, scoring_table(raw)),
                                     cal))
    ep_named = ep.merge(players[["code", "name", "position"]], on="code",
                        how="left")
    store.save(ep_named[ep_named["gw"] == gw], f"live/predictions/gw{gw}.parquet")

    # GW1 has no completed gameweek to read a squad from, so fetch_my_team
    # refuses. That is not a failure: it is the initial-squad case, and the
    # MILP builds one from scratch as happily as it transfers.
    try:
        my = fetch_my_team(client, cfg.entry_id, gw, players)
    except GafferError as e:
        print(f"{e}")
        my = None
    ep_by = {(int(r.code), int(r.gw)): float(r.ep) for r in ep.itertuples()}

    # The league has to be read *before* the pool is built. The rank-aware
    # tilt decides which players are even worth considering — a chaser's
    # differential is often outside the top-N by raw EP — so applying it after
    # build_pool would leave the tilt with nothing new to pick from.
    #
    # Every failure mode lands in the same place: no league configured, a dead
    # endpoint, a league with no rivals yet. All of them leave strategy None
    # and league_eo empty, lam is then 0.0, and tilt_ep is an exact
    # passthrough — the solve is bit-identical to the v1 points-max one.
    league_eo: dict[int, float] = {}
    strat = None
    win_probs: list[dict] = []
    if cfg.league_id:
        try:
            rivals = fetch_rival_entries(client, cfg.league_id, cfg.entry_id)
            if not rivals.empty:
                rival_picks = fetch_rival_picks(
                    client, rivals["entry"].tolist(), gw - 1)
                eo_by_element = effective_ownership(rival_picks)
                code_of_element = dict(zip(players["element"], players["code"]))
                league_eo = {code_of_element[el]: v
                             for el, v in eo_by_element.items()
                             if el in code_of_element}
                entry = client.get_entry(cfg.entry_id)
                my_total = int(entry.get("summary_overall_points") or 0)
                strat = compute_strategy(my_total, rivals, gw)
                win_probs = [
                    {"name": str(r.entry_name), "total": int(r.total),
                     "p_win": round(win_probability(my_total, int(r.total),
                                                    strat.weeks_left), 3)}
                    for r in rivals.itertuples()]
        except Exception as e:  # noqa: BLE001 — the league must never block advice
            print(f"league unavailable, continuing without: {e}")
            league_eo, strat, win_probs = {}, None, []

    pool_ep = tilt_ep(ep_by, league_eo, strat.lam if strat else 0.0)
    if my is None:
        state, my_picks = initial_squad_state(gws)
    else:
        my_picks = my.picks
        state = SolveInput(owned_codes=my.picks["code"].tolist(), bank=my.bank,
                           free_transfers=my.free_transfers, gws=gws)
    pool = build_pool(players, pool_ep, my_picks, gws)
    opt_kw = dict(decay=cfg.decay, bench_weight=cfg.bench_weight,
                  vice_weight=cfg.vice_weight, ft_value=cfg.ft_value,
                  itb_value=cfg.itb_value, hit_cost=cfg.hit_cost)
    plan = solve_plan(pool, state, **opt_kw)
    first = plan.gw_plans[0]

    # Chips are a weekly question only. At GW1 nothing has been played, no
    # chip history exists to read, and playing one on the squad you are still
    # assembling is not a decision worth costing — so skip the whole block.
    chip_rows: list[dict] = []
    wc_now = None
    if my is not None:
        chip_names = chips_available_for(my.chips_by_gw, gw)
        # Availability is per gameweek, not per horizon: a horizon reaching
        # past GW19 gets the fresh second-half set from GW20 on, whatever was
        # spent in the first half (and vice versa).
        avail_by_gw = {g: chips_available_for(my.chips_by_gw, g) for g in gws}
        # `plan` is the no-chip baseline every chip is scored against; pass it
        # in rather than letting each helper re-solve the same MILP.
        chip_table = evaluate_chips(pool, state, base=plan,
                                    avail_by_gw=avail_by_gw, **opt_kw)
        chip_rows = chip_table.to_dict("records")
        for row in chip_rows:
            if row["chip"] == "freehit":
                row["note"] = "conservative lower bound"
        # "Should I wildcard right now?" is only a question if the wildcard is
        # still available in this half of the season.
        wc_now = (wildcard_now_assessment(pool, state, base=plan, **opt_kw)
                  if "wildcard" in chip_names else None)

    ep_gw1 = ep_named[ep_named["gw"] == gw]
    cap_tab = captain_table(ep_gw1, first.xi, league_eo)
    if first.buys:
        alts = transfer_alternatives(ep_gw1, first.buys[0], league_eo)
        alts = alts[~alts["code"].isin(first.squad)]
    else:
        alts = pd.DataFrame(columns=["code", "name", "ep", "p_haul",
                                     "league_eo"])
    threats = threat_board(ep_gw1, first.squad, league_eo)

    owned_now = [] if my is None else my.picks["code"].tolist()
    watch = set(first.buys + first.sells + owned_now)
    alerts = price_alerts(players, list(watch))

    name_of = dict(zip(players["code"], players["name"]))
    buys = _named(first.buys, name_of, ep_by, gw)
    for b in buys:
        # An empty EO map is "nobody's ownership is known", not "nobody owns
        # them" — at GW1 no rival picks are public yet, and tagging all 15
        # opening picks "attack" off a missing map would be pure noise.
        b["tag"] = transfer_tag(league_eo.get(b["code"]),
                                strat is not None and bool(league_eo))
    strategy = None
    if strat is not None:
        strategy = asdict(strat)
        # A dead-level league gives sign * 0.0 == -0.0, which reads as a typo
        # in the report. It is zero either way.
        strategy["lam"] = abs(strategy["lam"]) if strategy["lam"] == 0 \
            else strategy["lam"]
    advice = Advice(
        gw=gw,
        deadline=deadline,
        buys=buys,
        sells=_named(first.sells, name_of, ep_by, gw),
        hits=first.hits,
        xi=_named(first.xi, name_of, ep_by, gw),
        bench=_named(first.bench, name_of, ep_by, gw),
        captain=_named([first.captain], name_of, ep_by, gw)[0],
        vice=_named([first.vice], name_of, ep_by, gw)[0],
        captain_options=cap_tab.to_dict("records"),
        chip_table=chip_rows,
        wildcard_now=wc_now,
        alternatives=alts.to_dict("records"),
        threats=threats.to_dict("records"),
        price_alerts=alerts.to_dict("records"),
        expected_pts=round(float(first.expected_pts), 2),
        plan_by_gw=[{"gw": p.gw, "hits": p.hits,
                     "buys": _named(p.buys, name_of, ep_by, p.gw),
                     "sells": _named(p.sells, name_of, ep_by, p.gw),
                     "expected_pts": round(float(p.expected_pts), 2)}
                    for p in plan.gw_plans],
        strategy=strategy,
        win_probs=win_probs,
        mode="weekly" if my is not None else "initial_squad",
    )
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / f"gw{gw}-advice.json").write_text(
        json.dumps(asdict(advice), indent=1, default=str))
    return advice
