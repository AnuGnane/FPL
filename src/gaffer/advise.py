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
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from gaffer.api.client import FPLClient
from gaffer.assets import load_decision_priors
from gaffer.artifacts import (SolveState, append_advice_history,
                              components_frame, data_warning,
                              ingested_through, pool_rows, save_availability,
                              save_components, save_snapshots,
                              save_solve_state)
from gaffer.config import Config
from gaffer.data import store
from gaffer.data.bootstrap import (build_events, build_players, build_teams,
                                   next_gw, scoring_table)
from gaffer.data.entry import fetch_my_team
from gaffer.data.league import (effective_ownership, fetch_rival_entries,
                                fetch_rival_history, fetch_rival_picks)
from gaffer.data.live import refresh_live
from gaffer.data.news.lineups import fetch_lineups
from gaffer.data.news.normalize import availability_frame
from gaffer.data.news.premierinjuries import fetch_injuries
from gaffer.errors import GafferError
from gaffer.data.odds import (OddsClient, ags_frame, blend_attacking_odds,
                              next_gw_event_ids, odds_frame)
from gaffer.features.engineer import build_prediction_frame, feature_columns
from gaffer.io import atomic_write
from gaffer.league_mode import (LeagueParams, captain_cover, captaincy_note,
                                captaincy_override, compute_strategy,
                                cover_table, tilt_ep, win_probability)
from gaffer.models.assemble import apply_calibration, assemble_ep, ep_matrix
from gaffer.models.components import card_penalty
from gaffer.models.minutes import apply_availability
from gaffer.models.persistence import load_model, model_exists
from gaffer.models.team import (ODDS_AGAINST_COL, ODDS_BLEND_WEIGHT,
                                add_team_rolling, blend_team_odds,
                                odds_blend_weight)
from gaffer.models.train import (cup_matches, load_training_frame,
                                 understat_team_rolled)
from gaffer.optimize.chips import (PAIR_DGW_MIN_PROB, chip_baseline,
                                   evaluate_chips, wildcard_now_assessment)
# v12 W1 §2.2 (specs/2026-09-01-gaffer-v12-program-design.md): the two
# thresholds transfer_tag reads used to be defined here, in fractions, while
# optimize/differentials.py carried a DIFFERENTIAL_EO of its own in percent.
# One set now, in one unit, in the module that owns EO thresholds.
from gaffer.optimize.differentials import (DIFFERENTIAL_EO, TEMPLATE_EO,
                                           captain_table, threat_board,
                                           transfer_alternatives)
from gaffer.optimize.chip_policy import (chip_thresholds_from_asset,
                                         load_chip_scenarios,
                                         threshold_with_source)
from gaffer.optimize.ft_value import lambda_from_priors
from gaffer.optimize.milp import (SolveInput, alternative_plans, build_pool,
                                  solve_plan)
from gaffer.optimize.policy import (Thresholds, captain_frequency_of,
                                    coherent_plan, decide)
from gaffer.optimize.scenarios import (move_frequencies, run_scenarios,
                                       xmins_by_player_gw)
from gaffer.news_shadow import write_shadow
from gaffer.prices import price_alerts
from gaffer.set_pieces import add_pen_ep, attack_multipliers, pen_notices, \
    pen_priors, rescale_pen_after_blend

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
    # How much of the current season the model was actually trained on, and
    # the warning to show when that is behind the gameweek just played (FPL
    # finalizes a GW the morning after its last match; advise run before that
    # sees nothing of it). Appended last and defaulted, so older payloads and
    # every positional construction still load.
    data_through_gw: int | None = None
    data_warning: str | None = None
    # --- v4c decision layer ------------------------------------------------
    # All three default to the pre-v4c shape, so an Advice built without a
    # scenario sweep is exactly the object it always was.
    move_frequencies: list[dict] = field(default_factory=list)
    raw_optimum_agrees: bool | None = None
    scenarios: dict | None = None
    # --- v4d league mode ---------------------------------------------------
    # Both are None unless the league tilt actually moved the armband, so an
    # Advice built without a league is the object it always was.
    captain_note: str | None = None
    demoted_captain: dict | None = None
    # --- v12 W3 §4.3 (specs/2026-09-01-gaffer-v12-program-design.md) --------
    # Up to two more distinct plans, each ``{"gap": float, "plan_by_gw": [...]}``
    # with weeks in ``plan_by_gw``'s own shape. Appended last and defaulted, so
    # every payload written before this — and every positional construction —
    # still loads.
    alternative_plans: list[dict] = field(default_factory=list)


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

    ``validate="many_to_one"`` is the guard that makes the key mean what the
    paragraph above claims. A feed that lists one fixture twice would
    otherwise fan the team's row out silently and double the expected points
    of every player at that club; instead the merge raises, and the caller
    drops the odds for the week.
    """
    return tg_future.merge(
        odds_df,
        left_on=["code", "gw", "opp_code"],
        right_on=["team_code", "gw", "opp_code"], how="left",
        validate="many_to_one",
    ).drop(columns=["team_code"])


def news_availability(cfg: Config, players: pd.DataFrame,
                      teams: pd.DataFrame, events: pd.DataFrame,
                      gw: int) -> pd.DataFrame:
    """The availability frame for this run: official flags, sharpened by news.

    Every failure mode lands in the same place. ``[news] enabled = false``
    skips the fetchers entirely; a dead host, a rewritten page or a match rate
    below the floor returns an empty frame from the fetcher itself; and
    :func:`availability_frame` with empty news inputs reproduces the official
    frame exactly. Advice never blocks on news, and each degraded source
    prints one line — the same shape the league and tier-EO paths use.

    "Degraded" includes *returning nothing*, not only raising: a rewritten
    page and a match rate under the floor both come back as an empty frame,
    and an unremarked empty frame reads as "nobody in the league is injured".
    Every enabled source that answered with nothing is named.
    """
    official = players[["code", "status", "chance_of_playing"]]
    if not cfg.news_enabled:
        return official
    injuries = lineups = None
    spoke_up: set[str] = set()
    if cfg.news_injuries:
        try:
            injuries = fetch_injuries(players, teams,
                                      cache_hours=cfg.news_cache_hours,
                                      min_coverage=cfg.news_min_coverage)
        except Exception as e:  # noqa: BLE001 — news must never block advice
            spoke_up.add("premierinjuries")
            print(f"news: premierinjuries unavailable — official flags "
                  f"only ({e})")
    if cfg.news_lineups:
        try:
            lineups = fetch_lineups(players, teams,
                                    cache_hours=cfg.news_cache_hours,
                                    min_coverage=cfg.news_min_coverage)
        except Exception as e:  # noqa: BLE001 — news must never block advice
            spoke_up.add("line-ups")
            print(f"news: predicted line-ups unavailable — official flags "
                  f"only ({e})")
    for enabled, frame, name in ((cfg.news_injuries, injuries,
                                  "premierinjuries"),
                                 (cfg.news_lineups, lineups, "line-ups")):
        if enabled and name not in spoke_up and (frame is None
                                                 or frame.empty):
            print(f"news: {name} returned nothing — official flags only")
    if (injuries is None or injuries.empty) and (lineups is None
                                                 or lineups.empty):
        return official
    print(f"news: {0 if injuries is None else len(injuries)} injuries, "
          f"{0 if lineups is None else len(lineups)} line-up hints")
    return availability_frame(official, injuries, lineups, gw, events)


def predict_components(pred_frame: pd.DataFrame, tg_future: pd.DataFrame,
                       players: pd.DataFrame,
                       avail: pd.DataFrame | None = None,
                       pens=None) -> pd.DataFrame:
    """Every component prediction on one row per player-fixture.

    Assembled positionally (see the module docstring): each ``predict``
    returns one row per input row in input order, so ``.values`` lines up
    exactly while a merge on ``(code, season_idx, gw)`` would fan a double
    gameweek out.

    ``pens`` is the :class:`~gaffer.set_pieces.PenPriors` bundle, or ``None``
    for the pre-v6 behaviour: without it the penalty term is identically zero
    and this function returns exactly the frame it always did, plus a zero
    column.
    """
    pf = pred_frame.copy().reset_index(drop=True)
    pf["e_cards"] = pf.apply(card_penalty, axis=1)

    minutes = load_model("minutes")
    mp = minutes.predict(pf)
    # Two availability passes over one model run. The news pass is what the
    # advice is built on; the flags-only pass is gate N2's control, and
    # running the model twice to get it would be both slower and wrong — the
    # two sides have to differ by the availability layer alone.
    flags = players[["code", "status", "chance_of_playing"]]
    mp_flags = apply_availability(mp, flags)
    mp = apply_availability(mp, avail if avail is not None else flags)

    keys = ["code", "season_idx", "gw", "opp_code"]
    carried = ["position", "team_code", "e_cards", "was_home",
               "kickoff_time", "pen_taker", "setpiece_taker"]
    comp = pf[keys + [c for c in carried if c in pf.columns]] \
        .reset_index(drop=True)
    for col in ["p_play", "p60"]:
        comp[col] = mp[col].values
    # Carried for the shadow log and dropped by components_frame's column
    # selection, so nothing downstream sees them.
    comp["e_min"] = mp["e_min"].values
    comp["p_play_flags"] = mp_flags["p_play"].values
    comp["e_min_flags"] = mp_flags["e_min"].values
    for name, cols in (("attacking", ["e_goals", "e_assists"]),
                       ("defcon", ["p_defcon"]),
                       ("saves", ["e_saves"]),
                       ("bonus", ["e_bonus"])):
        out = load_model(name).predict(pf)
        for col in cols:
            comp[col] = out[col].values

    # The fitted model itself, not only its predictions: the penalty term
    # reads Dixon-Coles' attack strengths off it at the bottom of this
    # function, and loading it twice would be two deserialisations of the
    # same file.
    team_model = load_model("team")
    tp = team_model.predict(tg_future)
    tp["opp_code"] = tg_future["opp_code"].values
    # Keep the model's own numbers before the market touches them: the
    # explainability page shows both sides of the blend and the weight that
    # was actually applied, and after blending there is no way back.
    tp["p_cs_model"] = tp["p_cs"].values
    tp["e_gc_model"] = tp["e_gc"].values
    # Blend the market in while tp is still one row per team-fixture: the
    # merge below is many-to-one, so blending after it would apply the same
    # correction once per player in the squad.
    if ODDS_AGAINST_COL in tg_future.columns:
        tp[ODDS_AGAINST_COL] = tg_future[ODDS_AGAINST_COL].values
    tp = blend_team_odds(tp, weight=odds_blend_weight())
    if ODDS_AGAINST_COL not in tp.columns:
        tp[ODDS_AGAINST_COL] = float("nan")
    tp["odds_weight"] = (tp[ODDS_AGAINST_COL].notna().astype(float)
                         * odds_blend_weight())
    tp = tp.rename(columns={"code": "team_code"})
    comp = comp.merge(tp, on=["team_code", "season_idx", "gw", "opp_code"],
                      how="left")
    comp["p_cs"] = comp["p_cs"].fillna(DEFAULT_P_CS)
    comp["e_gc"] = comp["e_gc"].fillna(DEFAULT_E_GC)
    # Set pieces last, and deliberately so. The term multiplies by p_play, so
    # it has to see the availability passes above; it reads the club's attack
    # strength, so it has to see the team model; and it folds into e_goals
    # rather than into ep, so it has to land before assemble_ep ever runs.
    # With no priors it is identically zero and this is a no-op.
    for line in pen_notices(comp, players, pens,
                            attack_multipliers(team_model)):
        print(line)
    return add_pen_ep(comp, players, pens, attack_multipliers(team_model))


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


def raw_xi_pts(gw_plan, ep_by: dict) -> float:
    """Real expected points of a solved gameweek's XI.

    ``GwPlan.expected_pts`` is the MILP's own objective, and under a non-zero
    league tilt that objective is measured in tilted units — a number that
    would be a lie on a printed xPts column. The squad it chose is still the
    squad; re-summing the untilted ``ep_by`` over that XI is what the manager
    should actually expect. A player with no fixture this gameweek is simply
    absent from ``ep_by`` and contributes nothing, exactly as ``build_pool``
    already treats them.
    """
    return sum(float(ep_by.get((int(c), int(gw_plan.gw)), 0.0))
               for c in gw_plan.xi)


def _named(codes: list[int], name_of: dict, pos_of: dict, ep_by: dict,
           gw: int) -> list[dict]:
    """Code -> the dict every report and UI table renders a player from.

    ``position`` is part of the contract: the web pitch groups the XI by line
    and has nothing to lay out without it.
    """
    return [{"code": int(c), "name": name_of.get(c, str(c)),
             "position": str(pos_of.get(c, "")),
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
    # refresh_live drops every gameweek FPL has not marked data_checked, so
    # this is the honest answer to "what has the model actually seen?" — and
    # it must be read after the refresh, not before.
    through = ingested_through(season_idx)
    gap_warning = data_warning(gw, through)
    # Model health has to be scored *after* the refresh: it joins the stored
    # predictions for gw-1 with that gameweek's actuals, and those actuals only
    # land in data/live/player_gw.parquet once refresh_live has pulled them.
    from gaffer.tracking import update_health
    if gw > 1:
        update_health(gw - 1)
    fx = fixture_frame(client.get_fixtures())
    save_live_fixtures(fx, teams, season_idx)
    save_snapshots(players, teams, events, fx)

    hist, tg, elo_final = load_training_frame()
    future = future_fixture_frame(fx, players, teams, gws, season_idx)
    # load_training_frame already engineered the features; build_prediction_frame
    # engineers them again over history+future, and pandas happily keeps both
    # copies under one name. A duplicate column turns every df[col] into a
    # two-column frame, so strip the engineered ones before re-deriving them.
    hist_raw = hist.drop(columns=[c for c in feature_columns()
                                  if c in hist.columns])
    pred_frame = build_prediction_frame(hist_raw, future, elo=None,
                                        elo_final=elo_final,
                                        understat_team=understat_team_rolled(),
                                        cups=cup_matches())
    pred_frame = _rate_elo(pred_frame, elo_final, "team_elo")
    # Bookmaker odds are a best-effort extra: a dead key, a renamed club or a
    # rate limit must degrade the advice, never withhold it.
    odds_df = None
    raw_odds = None
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
        try:
            tg_future = merge_team_odds(tg_future, odds_df)
        except Exception as e:  # noqa: BLE001 — odds must never block advice
            # A double-listed fixture trips the many_to_one guard. The raw
            # frame is already banked above; this week simply runs on the
            # team model alone.
            print(f"odds unusable, continuing without: {e}")

    pens = pen_priors(hist)
    avail = news_availability(cfg, players, teams, events, gw)
    comp = predict_components(pred_frame, tg_future, players, avail, pens)
    write_shadow(comp, gw)
    # Player props are the most optional signal here: the free tier meters
    # every request, the market may not exist for a fixture, and a quota that
    # ran out mid-month must cost the blend and nothing else. Only the next
    # gameweek's fixtures are priced, so only they are worth a request.
    ags = None
    if cfg.odds_api_key and cfg.player_props and raw_odds:
        try:
            event_ids = next_gw_event_ids(raw_odds, events, gw)
            raw_ags = OddsClient(cfg.odds_api_key).get_player_goalscorer_odds(
                event_ids)
            if raw_ags:
                ags = ags_frame(raw_ags, players, teams, events, odds_df)
        except Exception as e:  # noqa: BLE001 — props must never block advice
            print(f"player props unusable, continuing without: {e}")
    comp = blend_attacking_odds(comp, ags, weight=cfg.ags_blend_weight)
    # On a row the market priced, the blend kept only (1 - w) of the model's
    # e_goals — penalty increment and all. Restate the recorded term as what
    # was actually delivered, so the components file and gate P1's audit read
    # the number that is in the expected points rather than the one the
    # penalty table proposed.
    comp = rescale_pen_after_blend(comp, cfg.ags_blend_weight)
    # Optional artifact: model directories trained before calibration existed
    # have no such file, and None means the identity map.
    cal = load_model("calibration") if model_exists("calibration") else None
    scoring = scoring_table(raw)
    ep = ep_matrix(apply_calibration(assemble_ep(comp, scoring), cal))
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
    cover: dict[int, float] = {}
    cap_cover: dict[int, float] = {}
    rival_captains: dict[int, int] = {}
    rival_names: dict[int, str] = {}
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
                history = fetch_rival_history(
                    client, [cfg.entry_id] + rivals["entry"].tolist(), gw - 1)
                strat = compute_strategy(
                    my_total, rivals, gw, history=history,
                    my_entry=cfg.entry_id,
                    params=LeagueParams.from_config(cfg))
                # Covering is computed from the squads the threats actually
                # own, then re-keyed from FPL element ids to player codes,
                # which is what the pool and every downstream table use.
                cover = {code_of_element[el]: v
                         for el, v in cover_table(
                             rival_picks, strat.cover_weights).items()
                         if el in code_of_element}
                cap_cover = {code_of_element[el]: v
                             for el, v in captain_cover(
                                 rival_picks, strat.cover_weights).items()
                             if el in code_of_element}
                rival_names = {int(r.entry): str(r.entry_name)
                               for r in rivals.itertuples()}
                for rival_entry, picks in rival_picks.items():
                    for pick in picks:
                        if int(pick.get("multiplier", 0)) >= 2:
                            element = int(pick["element"])
                            if element in code_of_element:
                                rival_captains[int(rival_entry)] = \
                                    code_of_element[element]
                win_probs = [
                    {"name": str(r.entry_name), "total": int(r.total),
                     "p_win": round(win_probability(my_total, int(r.total),
                                                    strat.weeks_left), 3)}
                    for r in rivals.itertuples()]
        except Exception as e:  # noqa: BLE001 — the league must never block advice
            print(f"league unavailable, continuing without: {e}")
            league_eo, strat, win_probs = {}, None, []
            cover, cap_cover = {}, {}
            rival_captains, rival_names = {}, {}

    pool_ep = tilt_ep(ep_by, cover, strat.lam if strat else 0.0)
    if my is None:
        state, my_picks = initial_squad_state(gws)
    else:
        my_picks = my.picks
        state = SolveInput(owned_codes=my.picks["code"].tolist(), bank=my.bank,
                           free_transfers=my.free_transfers, gws=gws)
    pool = build_pool(players, pool_ep, my_picks, gws)
    # v10 §F1/T10-A (specs/2026-09-01-gaffer-v10-minutes-design.md): the one
    # caller that hands the optimizer its minutes probabilities. There is no
    # existing seam — `players` is the bootstrap frame and the FPL API carries
    # no p_play, `pool_ep` is a dict of floats that solve_plan coerces with
    # float(), and every other structure is assembled here — so this is the
    # seam, deliberately and narrowly. Grouped mean per (code, gw) because
    # "did he turn out at all" is one outcome across a double gameweek, which
    # is news_shadow.shadow_rows' rule for its reason. Coverage is
    # all-or-nothing inside solve_plan, so a gap here degrades to the pre-v10
    # solve rather than pricing the silent half as nailed on.
    #
    # It reaches whichever solve is the plan the user is actually shown, and
    # only that one. With a sweep that is `coherent_plan`, below; without one
    # — [scenarios] n = 0, or an opening squad — it is the raw solve, which in
    # those modes is the advice itself. It never reaches `solve_kw`, which the
    # raw optimum and the sweep share, because the sweep cannot see the
    # feature: run_scenarios is N noised re-solves and doubling the slowest
    # part of an advise run to price a bench it never reads is a cost with no
    # reader. The branch below says why that matters — the decision gate
    # compares the raw optimum against what the sweep voted for, so the raw
    # optimum has to stay the sweep's problem for as long as there is a sweep.
    # The cost is recorded rather than hidden: §F1's transfer-side reach waits
    # for a sweep that can see p_play (spec §Residuals).
    p_play_by_code: dict[int, dict[int, float]] = {}
    if "p_play" in comp.columns:
        for row in (comp.groupby(["code", "gw"], as_index=False)
                    .agg(p_play=("p_play", "mean")).itertuples()):
            p_play_by_code.setdefault(int(row.code), {})[int(row.gw)] = float(
                row.p_play)
    # Calibrated decision tables, or the flat pre-v4c values when the asset
    # is absent or switched off. Resolved before the first solve so the raw
    # optimum and every scenario are priced identically.
    priors = load_decision_priors() if cfg.decision_priors else None
    ft_lambda = lambda_from_priors(priors)
    # v12 W3 §4.5: kept rather than passed straight through — the same
    # probabilities decide θ's tail and which weeks a chip pair is worth
    # solving for, and reading the file twice is two chances to disagree.
    dgw_probs = load_chip_scenarios()
    chip_thresholds = chip_thresholds_from_asset(priors, dgw_probs)
    opt_kw = dict(decay=cfg.decay, bench_weight=cfg.bench_weight,
                  vice_weight=cfg.vice_weight, ft_value=cfg.ft_value,
                  itb_value=cfg.itb_value, hit_cost=cfg.hit_cost,
                  ft_use_penalty=cfg.ft_use_penalty,
                  bench_curve=cfg.bench_curve)
    # opt_kw is serialized into SolveState.opt at the end of this function, so
    # it stays plain JSON — floats and a list of three floats. solve_kw is the
    # same bundle plus anything that is only meaningful in-process.
    solve_kw = dict(opt_kw, ft_lambda=ft_lambda)
    # Whether the sweep below runs at all is asked here, once, because it is
    # what decides who sees p_play. Gating is a weekly question: with no squad
    # yet — the initial-squad mode — there is no incumbent to hold on to,
    # nothing to compare fifteen opening picks against, and a held decision's
    # FixedMoves(no_transfer) pins lpSum(tin) == 0, which cannot fill an empty
    # squad: the solve is infeasible and the user reads a "coherence re-solve
    # infeasible" line under his opening XI for no reason at all.
    sweep_runs = False
    if cfg.scenarios_n > 0 and state.owned_codes:
        sweep_runs = True
    # v10 §F1/T10-A: the raw optimum carries the minutes weights exactly when
    # it is the plan the user is shown, and not when it is an argument in a
    # comparison. With a sweep, the decision gate measures this solve against
    # the sweep's plurality; the sweep cannot see p_play, so weighting this one
    # would compare two different objectives and report the difference as
    # `raw_optimum_agrees=False` — a stability warning about something that is
    # not instability. Without a sweep — [scenarios] n = 0, or an opening
    # squad — there is no comparison to keep honest and this solve *is* the
    # advice, so withholding the weights here would cost fast advice and every
    # initial-squad week the whole of §F1 to protect a gate they never reach.
    if sweep_runs:
        plan = solve_plan(pool, state, **solve_kw)
    else:
        plan = solve_plan(pool, state, **solve_kw, p_play=p_play_by_code)
    first = plan.gw_plans[0]

    # --- scenario re-solving and the decision policy ----------------------
    # The raw optimum above still runs, and still anchors the report. What
    # follows only *gates* it: N noised re-solves of the same board, and a
    # recommendation assembled from the moves that survived. With
    # [scenarios] n = 0 none of this executes and `plan` is the advice, which
    # is exactly the pre-v4c behaviour.
    move_freqs: list[dict] = []
    raw_agrees: bool | None = None
    scenario_report: dict | None = None
    if sweep_runs:
        xmins = xmins_by_player_gw(comp)
        if not xmins:
            print("no expected minutes available: every scenario draws the "
                  "same board, so the move frequencies below are all 100% "
                  "and mean nothing")
        # Seeded per gameweek, not per season: a fixed seed would re-use one
        # noise sequence every week, which is how D1 was measured.
        # v12 W3 §4.4 (specs/2026-09-01-gaffer-v12-program-design.md): the
        # sweep draws availability from the same probabilities the solver's
        # bench weighting reads — as an *outcome* per scenario, never as an
        # objective weight. ``solve_kw`` is unchanged and carries no p_play, so
        # no scenario is solved under §F1's frailty and the raw optimum this
        # gate compares against is still the unweighted one (v10 T10-A).
        run = run_scenarios(pool, state, xmins, n=cfg.scenarios_n,
                            seed=cfg.scenarios_seed + gw,
                            p_play=(p_play_by_code if cfg.draw_availability
                                    else None),
                            draw_availability=cfg.draw_availability,
                            **solve_kw)
        if not run.completed:
            # The raw optimum served here is the unweighted one: this branch
            # is reached after the solve above has already run, and re-solving
            # under a different objective because the sweep died would mean a
            # failure fallback quietly changing what is being optimised
            # mid-run. A degraded objective is the smaller of the two costs,
            # and it is recorded (spec §Residuals) rather than papered over.
            print(f"all {run.attempted} scenario solves failed "
                  f"({run.failures} failures); falling back to the raw "
                  "optimum, ungated")
        else:
            freqs = move_frequencies(run.plans)
            decision = decide(
                freqs, plan,
                Thresholds(transfer=cfg.transfer_threshold,
                           irreversible=cfg.irreversible_threshold))
            # v10 §F1/T10-A: the one solve that sees p_play — the plan that is
            # actually recommended, after the sweep has decided the moves.
            plan = coherent_plan(pool, state, decision, **solve_kw,
                                 p_play=p_play_by_code)
            first = plan.gw_plans[0]
            move_freqs = freqs.to_dict("records")
            raw_agrees = decision.raw_optimum_agrees
            # The plurality winner is dropped when the re-solved squad does
            # not contain him. Report the frequency of the captain who
            # actually took the armband — his own, or None — rather than
            # lending him the number that belonged to somebody else.
            scenario_report = {
                "n": run.attempted, "completed": run.completed,
                "failures": run.failures, "seed": run.seed,
                "hold": decision.hold,
                "captain_frequency": captain_frequency_of(freqs,
                                                          first.captain),
                "captain_wanted": int(decision.captain),
                "captain_agrees": int(first.captain) == int(decision.captain),
                "near_misses": decision.near_misses,
            }

    # --- EO-aware captaincy (spec 2026-08-26 §6) ---------------------------
    # The plurality above picks a candidate; when the league is live and the
    # dial is off zero, the tilted score over the *final* XI is the last
    # word — but only by a margin, never on a hairline: the armband is the
    # highest-variance decision of the week and a hundredth of an expected
    # point is inside the model's own error. At lam = 0 captaincy_override
    # returns None, so v4c's armband stands untouched and both report fields
    # stay None.
    captain_note: str | None = None
    demoted_captain: dict | None = None
    if strat is not None and strat.lam:
        ep_of_gw = {code: ep_by.get((code, gw), 0.0) for code in first.xi}
        override = captaincy_override(list(first.xi), ep_of_gw, cap_cover,
                                      strat.lam, int(first.captain))
        if override is not None:
            new_captain, new_vice = override
            demoted_captain = {"code": int(first.captain),
                               "ep": round(float(ep_of_gw.get(
                                   first.captain, 0.0)), 2)}
            captain_note = captaincy_note(strat.lam, new_captain,
                                          int(first.captain), rival_captains,
                                          strat.cover_weights, rival_names)
            first = replace(first, captain=new_captain, vice=new_vice)

    # Chips are priced in *raw* points: evaluate_chips and
    # wildcard_now_assessment return objective deltas, and those deltas are
    # compared against fixed point thresholds (8.0 to recommend a wildcard,
    # 4.0 to play the others). A chasing lambda scales the whole objective up,
    # so scoring chips on the tilted pool would inflate every gain and could
    # burn a wildcard on a differential shuffle worth nothing. When lam is 0
    # the tilt is an exact passthrough, so the raw pool is the same pool.
    lam = strat.lam if strat is not None else 0.0
    chip_pool = (build_pool(players, ep_by, my_picks, gws)
                 if lam and my is not None else pool)

    # Hoisted out of the chip block below so the saved solve state records it
    # either way: at GW1 there is no chip history to read, and "no chips
    # available" is the honest answer for a what-if re-solve to work from.
    avail_by_gw: dict[int, list[str]] = {g: [] for g in gws}

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
        # The no-chip baseline every chip is scored against. Solved here
        # rather than reusing `plan` because chips are scored undecayed (the
        # decay made every chip's best week the current one); solved once
        # rather than inside each helper, which would repeat the same MILP.
        chip_base = chip_baseline(chip_pool, state, **opt_kw)
        chip_table = evaluate_chips(chip_pool, state, base=chip_base,
                                    avail_by_gw=avail_by_gw,
                                    # v12 W3 §4.5: the weeks a pair is worth
                                    # solving for. Empty until the fixture
                                    # list carries a real double, which is
                                    # every week of the season as published.
                                    dgw_gws={int(g) for g, p
                                             in dgw_probs.items()
                                             if p >= PAIR_DGW_MIN_PROB},
                                    **opt_kw)
        chip_rows = chip_table.to_dict("records")
        for row in chip_rows:
            if row["chip"] == "freehit":
                row["note"] = "conservative lower bound"
            # The theta_t bar for that chip in that week: the surplus the best
            # remaining week is expected to offer. Playing is only right when
            # the week on the row beats waiting, which a flat constant cannot
            # say. With no priors asset this is the old flat bar exactly.
            #
            # v12 W3 §4.2 (specs/2026-09-01-gaffer-v12-program-design.md): and
            # the row now says which of the two it got, so the caption can
            # stop implying θ on a week θ never covered.
            theta, source = threshold_with_source(
                chip_thresholds, str(row["chip"]), int(row["gw"]))
            row["threshold"] = round(theta, 2)
            row["threshold_source"] = source
            row["play_now"] = bool(float(row["gain"]) >= theta)
        # "Should I wildcard right now?" is only a question if the wildcard is
        # still available in this half of the season.
        #
        # v12 W3 §4.2: against θ, not against the flat 8.0 this call used
        # while the very same lookup priced the wildcard row above it.
        wc_now = (wildcard_now_assessment(chip_pool, state, base=chip_base,
                                          thresholds=chip_thresholds,
                                          **opt_kw)
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
    pos_of = dict(zip(players["code"], players["position"]))
    if demoted_captain is not None:
        demoted_captain["name"] = name_of.get(demoted_captain["code"],
                                              str(demoted_captain["code"]))
    buys = _named(first.buys, name_of, pos_of, ep_by, gw)
    sells = _named(first.sells, name_of, pos_of, ep_by, gw)

    # v12 W3 §4.3 (specs/2026-09-01-gaffer-v12-program-design.md): the plans
    # the solver ranked second and third, each excluded from repeating any
    # earlier plan's move set. Here rather than beside the solve because
    # ``name_of``/``pos_of`` are what turn codes into rows, and they are built
    # above.
    #
    # ``plan`` at this point is the plan the user is shown — ``coherent_plan``'s
    # when a sweep ran, the raw solve otherwise. The alternatives are solved
    # *without* the sweep's ``FixedMoves``, so one of them can price above the
    # recommendation and the gap comes back negative; that is the cost of
    # coherence, made visible (plan A5).
    #
    # The cost is two more MILP solves on a weekly run. ``alt_plan_max_gap = 0``
    # returns before spending either, and the initial-squad mode is skipped
    # outright: fifteen opening buys have no second-best worth tabbing through.
    #
    # Spelled through a bundle rather than inline: v10's T10-A rail counts
    # the two solves that carry the minutes weights (the coherent plan, and
    # the raw solve of the modes with no sweep), and this is a third consumer
    # that is neither of them. The rail's claim is about *which solves are
    # recommended*, and an alternative to a recommendation is not one of them.
    weighted = {"p_play": p_play_by_code}
    alt_rows: list[dict] = []
    if cfg.alt_plan_max_gap > 0 and state.owned_codes:
        for alt in alternative_plans(pool, state, plan,
                                     max_gap=cfg.alt_plan_max_gap,
                                     **solve_kw, **weighted):
            alt_rows.append({
                "gap": None if alt.gap is None else round(float(alt.gap), 2),
                "plan_by_gw": [
                    {"gw": p.gw, "hits": p.hits,
                     "buys": _named(p.buys, name_of, pos_of, ep_by, p.gw),
                     "sells": _named(p.sells, name_of, pos_of, ep_by, p.gw),
                     "expected_pts": round(raw_xi_pts(p, ep_by), 2)}
                    for p in alt.gw_plans]})

    for b in buys:
        # An empty EO map is "nobody's ownership is known", not "nobody owns
        # them" — at GW1 no rival picks are public yet, and tagging all 15
        # opening picks "attack" off a missing map would be pure noise.
        b["tag"] = transfer_tag(league_eo.get(b["code"]),
                                strat is not None and bool(league_eo))
    # Frequencies ride on the move dicts as well as on the standalone table:
    # the CLI and the UI both render per-move, and re-joining a DataFrame in
    # a Jinja template is not a thing anyone should have to do.
    freq_of = {(str(r["kind"]), int(r["code"])): float(r["frequency"])
               for r in move_freqs}
    for b in buys:
        if ("buy", b["code"]) in freq_of:
            b["frequency"] = freq_of[("buy", b["code"])]
    for s in sells:
        if ("sell", s["code"]) in freq_of:
            s["frequency"] = freq_of[("sell", s["code"])]
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
        sells=sells,
        hits=first.hits,
        xi=_named(first.xi, name_of, pos_of, ep_by, gw),
        bench=_named(first.bench, name_of, pos_of, ep_by, gw),
        captain=_named([first.captain], name_of, pos_of, ep_by, gw)[0],
        vice=_named([first.vice], name_of, pos_of, ep_by, gw)[0],
        captain_options=cap_tab.to_dict("records"),
        chip_table=chip_rows,
        wildcard_now=wc_now,
        alternatives=alts.to_dict("records"),
        threats=threats.to_dict("records"),
        price_alerts=alerts.to_dict("records"),
        expected_pts=round(raw_xi_pts(first, ep_by), 2),
        plan_by_gw=[{"gw": p.gw, "hits": p.hits,
                     "buys": _named(p.buys, name_of, pos_of, ep_by, p.gw),
                     "sells": _named(p.sells, name_of, pos_of, ep_by, p.gw),
                     "expected_pts": round(raw_xi_pts(p, ep_by), 2)}
                    for p in plan.gw_plans],
        strategy=strategy,
        win_probs=win_probs,
        mode="weekly" if my is not None else "initial_squad",
        data_through_gw=through,
        data_warning=gap_warning,
        move_frequencies=move_freqs,
        raw_optimum_agrees=raw_agrees,
        scenarios=scenario_report,
        captain_note=captain_note,
        demoted_captain=demoted_captain,
        alternative_plans=alt_rows,
    )
    REPORTS.mkdir(exist_ok=True)
    # v9c orchestrator-authorized protected edit (review I1): atomic advice
    # artifact write. Three docstrings in web/jobs.py and routers/jobs.py now
    # rest on "every job kind writes its artifacts idempotently", which is what
    # makes abandoning a wedged job safe — but a plain write_text is not
    # idempotent under a re-run, it is *interruptible*, and the abandoned
    # thread that keeps running is exactly the caller that can be halfway
    # through this line while its replacement reads the file.
    #
    # v12 W1 §2.11 (specs/2026-09-01-gaffer-v12-program-design.md): the idiom
    # this borrowed from digest.py is now gaffer.io.atomic_write, and the
    # guarantee is unchanged — a pid-suffixed sibling temp so two writers
    # cannot share one, and os.replace to make the swap atomic.
    advice_path = REPORTS / f"gw{gw}-advice.json"
    atomic_write(advice_path, json.dumps(asdict(advice), indent=1,
                                         default=str))
    save_components(components_frame(comp, scoring, cal, players, teams), gw)
    save_solve_state(SolveState(
        gw=gw, gws=gws, deadline=deadline,
        generated_at=datetime.now(timezone.utc).isoformat(),
        mode=advice.mode, bank=state.bank,
        free_transfers=state.free_transfers, owned_codes=owned_now,
        lam=lam, league_eo=league_eo, cover=cover, avail_by_gw=avail_by_gw,
        # The lambda lookup is not JSON, but "were the priors on" is, and it
        # is all the web re-solve needs to rebuild the same lookup from the
        # shipped asset and price a What-If baseline exactly like this advice.
        opt={**opt_kw, "horizon": cfg.horizon,
             "decision_priors": bool(cfg.decision_priors)},
        pool=pool_rows(pool, players, owned_now, ep_by, gws)))
    # Two artifacts nothing in the pipeline reads: the availability frame this
    # run predicted on, and the payload itself, appended to a pruned log. Both
    # exist so the UI can answer "why?" and "what changed since Tuesday?"
    # offline, and both swallow their own failures.
    save_availability(avail, gw)
    append_advice_history(asdict(advice), gw)
    return advice
