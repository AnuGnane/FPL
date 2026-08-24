"""Season replay: what would the tool have scored, week by week.

The harness re-runs the whole pipeline over a finished season. At each
gameweek it retrains on data strictly before that gameweek, predicts every
component, solves for the squad, then scores the resulting XI against what
actually happened. Nothing downstream of the deadline is ever visible to the
model. Two separate mechanisms enforce that:

* ``load_training_frame(max_season_idx, max_gw)`` truncates the *training*
  frame, so the fitted models never saw the gameweek they predict;
* the *feature rows* for the current gameweek are leakage-safe by
  construction — :func:`gaffer.features.engineer.add_player_rolling` shifts
  every rolling window one match back — but the rows for the **later**
  gameweeks of a receding horizon are not, because their shifted windows sit
  on matches played after the decision deadline. :func:`horizon_feature_rows`
  therefore re-engineers them the way the live advisor does: history
  truncated strictly before the decision gameweek, plus the known fixture
  list (opponent, home, kickoff) for the rest of the horizon with every
  outcome column blanked.

Two joins repeat the lessons the weekly advisor learned the hard way:
component predictions are stitched **positionally** (``predict`` returns one
row per input row in input order, and ``(code, gw)`` is not unique in a
double gameweek), and double-gameweek actuals are aggregated per code before
scoring while the expected-points side is collapsed by ``ep_matrix``.

v1 simplifications — all of them conservative, i.e. they understate what the
tool would really have scored:

* **No chips by default.** Pass ``chips=True`` to let the replay play a
  wildcard, free hit, bench boost or triple captain when the chip module
  values one above its threshold; without it the replay forgoes every points
  spike a chip would have bought.
* **Captain -> vice fallback only.** The real game's fallback chain is
  modelled one step deep; a blanking captain *and* vice scores nothing extra.
* **Simplified autosubs.** Bench players are taken in order and the first
  swap that keeps the formation legal is accepted; the real engine's
  ordering subtleties are not reproduced.
* **Static prices.** Each gameweek uses that gameweek's actual ``value`` as
  both buy and sell price. There is no price rise to profit from and no
  50%-of-profit sell-price rule — a team that rises in value in reality is
  flat here, so the replay has less money to spend than a real manager.
* **Models retrained every 4 gameweeks**, not weekly, so predictions are on
  average two gameweeks staler than a live run's.
* **Myopic by default** (``horizon=1``): the MILP maximises this week only,
  with no free-transfer planning value and no fixture-swing anticipation.
  Pass ``horizon=N`` for a receding-horizon replay — plan N weeks, execute
  the first, re-plan next week — which is what the weekly advisor does.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

import pandas as pd

from gaffer.advise import chips_available_for
from gaffer.assets import load_bootstrap_sample
from gaffer.config import load_config
from gaffer.data import store
from gaffer.data.bootstrap import scoring_table
from gaffer.features.engineer import (ROLL_STATS, build_prediction_frame,
                                      feature_columns)
from gaffer.models.assemble import apply_calibration, assemble_ep, ep_matrix
from gaffer.models.train import (DEFAULT_E_GC, DEFAULT_P_CS,  # noqa: F401
                                 load_training_frame,
                                 predict_components_simple, train_all)
from gaffer.optimize.chips import (CHIP_PLAY_THRESHOLD,
                                   WILDCARD_RECOMMEND_THRESHOLD,
                                   evaluate_chips)
from gaffer.optimize.milp import SolveInput, build_pool, solve_plan

XI_BOUNDS = {"GKP": (1, 1), "DEF": (3, 5), "MID": (2, 5), "FWD": (1, 3)}

LAST_GW = 38
STARTING_BUDGET = 1000
"""100.0m in the API's 0.1m units."""

MAX_FREE_TRANSFERS = 5

# Team-level clean sheet / goals conceded are held at league-average
# constants in the backtest rather than run through the team model (see
# DEFAULT_P_CS / DEFAULT_E_GC, re-exported above from models.train). It keeps
# the replay to one model refit per window and removes a source of
# per-gameweek variance that is not what this harness measures.

# Scoring rules for the replay. The live rules come from the API; a replay
# must run offline, so it reads the same payload shape from the bundled
# package asset (gaffer.assets), which works from an installed wheel too.


def _formation_legal(positions: list[str]) -> bool:
    c = Counter(positions)
    return (len(positions) == 11
            and all(lo <= c.get(p, 0) <= hi
                    for p, (lo, hi) in XI_BOUNDS.items()))


def score_gw(actuals: pd.DataFrame, xi: list[int], bench: list[int],
             captain: int, vice: int, hits: int, captain_mult: int = 2,
             bench_boost: bool = False) -> int:
    """Actual FPL points for one gameweek's team.

    ``actuals``: [code, total_points, minutes, position], one row per player
    (double gameweeks already aggregated). Codes missing from the frame are
    treated as 0 points / 0 minutes, which is what a player who did not
    feature at all scored.

    ``captain_mult`` is the armband multiplier: the captain (or the vice, if
    the captain did not feature) adds ``(captain_mult - 1)`` extra copies of
    their score, so the default 2 is the ordinary double and 3 is the triple
    captain chip.

    ``bench_boost`` scores all fifteen. Autosubs are skipped entirely under
    the chip, as in the real game — every bench player is already on the
    pitch, so there is nobody left to substitute in.
    """
    pts_of = dict(zip(actuals["code"], actuals["total_points"]))
    mins_of = dict(zip(actuals["code"], actuals["minutes"]))
    pos_of = dict(zip(actuals["code"], actuals["position"]))

    def played(code) -> bool:
        return float(mins_of.get(code, 0) or 0) > 0

    xi = list(xi)
    if not bench_boost:
        on_pitch = set(xi)
        for i, starter in enumerate(xi):
            if played(starter):
                continue
            for sub in bench:
                if sub in on_pitch or not played(sub):
                    continue
                trial = list(xi)
                trial[i] = sub
                if _formation_legal([str(pos_of.get(c, "MID")) for c in trial]):
                    on_pitch.discard(starter)
                    on_pitch.add(sub)
                    xi = trial
                    break

    scorers = list(xi) + (list(bench) if bench_boost else [])
    total = sum(float(pts_of.get(c, 0) or 0) for c in scorers)
    extra = captain_mult - 1
    if played(captain):
        total += extra * float(pts_of.get(captain, 0) or 0)
    elif played(vice):
        total += extra * float(pts_of.get(vice, 0) or 0)
    return int(round(total - 4 * hits))


def _pick_chip(table: pd.DataFrame, gw: int) -> str:
    """Best chip worth playing *this* gameweek, or "" for none.

    ``table`` is :func:`gaffer.optimize.chips.evaluate_chips` output — one
    row per (chip, horizon gameweek). Rows for later gameweeks are dropped:
    the replay only ever executes the current week, and a chip that looks
    best in three weeks' time is a decision for three weeks' time, taken
    again then with better information.
    """
    if table is None or table.empty:
        return ""
    now = table[table["gw"] == gw]
    best, best_gain = "", None
    for r in now.itertuples():
        floor = (WILDCARD_RECOMMEND_THRESHOLD if r.chip == "wildcard"
                 else CHIP_PLAY_THRESHOLD)
        gain = float(r.gain)
        if gain >= floor and (best_gain is None or gain > best_gain):
            best, best_gain = str(r.chip), gain
    return best


def _players_frame(season_rows: pd.DataFrame, gw: int) -> pd.DataFrame:
    """Pool input: every player seen this season up to ``gw``, one row each,
    priced at their most recent ``value``.

    It has to be the whole season-to-date universe, not just the players with
    a fixture in ``gw``. A blank gameweek leaves four or five clubs with no
    rows at all, and a pool built from ``gw`` alone would make the players
    already owned from those clubs disappear — forcing the MILP to replace
    them with no sale proceeds, which is both wrong and frequently
    infeasible. Blanking players belong in the pool at ``ep`` 0 (``ep_matrix``
    simply has no row for them), exactly as the real game treats them.
    """
    p = (season_rows[season_rows["gw"] <= gw]
         .sort_values(["gw", "kickoff_time"])
         .drop_duplicates("code", keep="last")
         [["code", "position", "team_code", "name", "value", "element"]].copy())
    return p.rename(columns={"value": "now_cost"}).reset_index(drop=True)


def elo_as_of(season_rows: pd.DataFrame, gw: int) -> dict:
    """Latest leakage-free Elo per team at the ``gw`` deadline.

    ``team_elo`` on a stored row is ``elo_pre`` — the rating *before* that
    match — so a team playing in ``gw`` carries exactly the rating a manager
    would have seen at the deadline. A team blanking in ``gw`` falls back to
    its most recent earlier row, which is one match stale but still contains
    nothing from after the deadline.
    """
    if "team_elo" not in season_rows.columns:
        return {}
    prior = season_rows[season_rows["gw"] <= gw].dropna(subset=["team_elo"])
    if prior.empty:
        return {}
    last = (prior.sort_values("gw").drop_duplicates("team_code", keep="last"))
    return dict(zip(last["team_code"], last["team_elo"]))


def horizon_feature_rows(hist_raw: pd.DataFrame, gw: int, gws: list[int],
                         season_idx: int, elo_at: dict) -> pd.DataFrame:
    """Feature rows for ``gws[1:]`` as they could be built at the ``gw``
    deadline.

    ``hist_raw`` is the *unengineered* player-match frame (the training frame
    with :func:`feature_columns` stripped, the same shape ``advise`` feeds
    ``build_prediction_frame``). History is truncated to matches strictly
    before ``gw``; the later-gameweek rows are reduced to what was genuinely
    known then — identity, opponent, home, kickoff — with every outcome
    column in ``ROLL_STATS`` blanked so no unplayed result can reach a
    rolling window. Elo comes from ``elo_at`` rather than the row's own
    stored ``elo_pre``, which for a future gameweek already reflects results
    from after the deadline.
    """
    season = hist_raw[hist_raw["season_idx"] == season_idx]
    future = season[season["gw"].isin(gws[1:])].copy()
    future = future.drop(columns=[c for c in ROLL_STATS
                                  if c in future.columns])
    prior = hist_raw[(hist_raw["season_idx"] < season_idx)
                     | ((hist_raw["season_idx"] == season_idx)
                        & (hist_raw["gw"] < gw))]
    out = build_prediction_frame(prior, future, elo=None, elo_final=elo_at)
    if elo_at and {"team_code", "opp_code"} <= set(out.columns):
        out["team_elo"] = out["team_code"].map(elo_at)
        out["opp_elo"] = out["opp_code"].map(elo_at)
        out["elo_diff"] = out["team_elo"] - out["opp_elo"]
    return out


def _actuals_frame(rows: pd.DataFrame) -> pd.DataFrame:
    """Per-code actual points and minutes, double gameweeks summed."""
    return (rows.groupby("code", as_index=False)
            .agg(total_points=("total_points", "sum"),
                 minutes=("minutes", "sum"),
                 position=("position", "first")))


def run_backtest(season: str = "2025-26", start_gw: int = 5,
                 retrain_every: int = 4, horizon: int = 1,
                 chips: bool = False) -> dict:
    """Replay ``season`` from ``start_gw`` to GW38 following the tool.

    ``horizon`` turns the replay into a receding-horizon plan: each week the
    MILP optimises over ``[gw, ..., gw + horizon - 1]`` (clipped at GW38),
    but only the first gameweek's plan is executed — squad, bank and free
    transfers all come from ``plan.gw_plans[0]``, and the later gameweek
    plans are thrown away and re-planned next week with fresh information.
    ``horizon=1`` is the old myopic behaviour.

    Planning ahead is leakage-free, but not for free: the later gameweeks'
    feature rows are re-engineered every week by :func:`horizon_feature_rows`
    from history truncated at that week's deadline plus the fixture list,
    which was genuinely known then. Reading them out of the stored frame
    instead would put results that had not been played yet into a GW+1 row's
    shifted rolling window. The *actuals* scored each week remain those of
    the current gameweek alone.

    ``chips`` turns on chip play. Each week, after the ordinary solve, the
    still-available chips (two sets a season, the first expiring after GW19)
    are valued against that solve and the best one clearing its threshold is
    played — at most one per week, never in the opening squad-build week,
    which is already a wildcard in all but name.

    Returns {"season", "from_gw", "total", "per_gw", "log", "chips_played"}
    and writes the per-gameweek log to ``data/live/backtest_log.parquet``.
    """
    cfg = load_config()
    season_idx = cfg.train_seasons.index(season)
    opt_kw = dict(decay=cfg.decay, bench_weight=cfg.bench_weight,
                  vice_weight=cfg.vice_weight, ft_value=cfg.ft_value,
                  itb_value=cfg.itb_value, hit_cost=cfg.hit_cost)
    scoring = scoring_table(load_bootstrap_sample())

    full, _, _ = load_training_frame()
    season_rows = full[full["season_idx"] == season_idx]
    # Unengineered copy for horizon_feature_rows. load_training_frame already
    # engineered the features and build_prediction_frame engineers them
    # again; pandas would happily keep both copies under one name and every
    # df[col] would then hand the model a two-column block. Same strip
    # advise.py does before build_prediction_frame.
    hist_raw = full.drop(columns=[c for c in feature_columns()
                                  if c in full.columns])

    models: dict = {}
    squad: list[int] = []
    bank = STARTING_BUDGET
    free_transfers = 1
    sell_of: dict[int, int] = {}
    pos_of: dict[int, str] = {}
    played_by_gw: dict[int, str] = {}
    log: list[dict] = []
    total = 0

    for gw in range(start_gw, LAST_GW + 1):
        rows = season_rows[season_rows["gw"] == gw]
        if rows.empty:
            continue
        if not models or (gw - start_gw) % retrain_every == 0:
            df, tg, _ = load_training_frame(max_season_idx=season_idx,
                                            max_gw=gw)
            models = train_all(df, tg, save=False)

        # Plan over the horizon, execute the first week only. Blank
        # gameweeks inside the horizon simply have no rows here: build_pool
        # fills the missing (code, gw) keys with ep 0.0, which is how the
        # MILP already treats a player with no fixture.
        gws = list(range(gw, min(gw + horizon - 1, LAST_GW) + 1))
        # The current gameweek's stored rows are already leakage-safe; the
        # later ones are rebuilt from history truncated at this deadline.
        # With horizon=1 there is nothing to rebuild and this is exactly the
        # old single-gameweek slice.
        horizon_rows = rows
        if len(gws) > 1:
            later = horizon_feature_rows(hist_raw, gw, gws, season_idx,
                                         elo_as_of(season_rows, gw))
            horizon_rows = (pd.concat([rows, later], ignore_index=True)
                            .reindex(columns=list(rows.columns)))

        comp = predict_components_simple(models, horizon_rows)
        ep = ep_matrix(apply_calibration(assemble_ep(comp, scoring),
                                         models.get("calibration")))
        ep_by = {(int(r.code), int(r.gw)): float(r.ep) for r in ep.itertuples()}
        players = _players_frame(season_rows, gw)
        pos_of.update(dict(zip(players["code"], players["position"])))
        name_of = dict(zip(players["code"], players["name"]))

        if not squad:
            picks = pd.DataFrame(columns=["code", "sell"])
            state = SolveInput(owned_codes=[], bank=STARTING_BUDGET,
                               free_transfers=15, gws=gws)
        else:
            # sell price = this gameweek's value (see module docstring)
            price_now = dict(zip(players["code"], players["now_cost"]))
            for c in squad:
                sell_of[c] = int(price_now.get(c, sell_of.get(c, 0)))
            picks = pd.DataFrame({"code": squad,
                                  "sell": [sell_of[c] for c in squad]})
            state = SolveInput(owned_codes=list(squad), bank=bank,
                               free_transfers=free_transfers, gws=gws)

        pool = build_pool(players, ep_by, picks, gws)
        # gw_plans[1:] are discarded: next week re-plans from scratch.
        base = solve_plan(pool, state, **opt_kw)
        plan = base.gw_plans[0]
        cost_of = dict(zip(pool["code"], pool["cost"]))
        pool_sell = dict(zip(pool["code"], pool["sell"]))

        # --- chips -------------------------------------------------------
        # Valued against the plan we would otherwise have played, then
        # applied. Everything the chip changes about *this* week is folded
        # into (plan, captain_mult, bench_boost); the free hit alone also
        # suspends the week's transfers, because its squad is borrowed.
        #
        # ``base`` is deliberately not reused here: chips are scored in an
        # undecayed frame, so they need their own baseline (evaluate_chips
        # solves one when it is not given one).
        chip, captain_mult, bench_boost, keep_squad = "", 2, False, False
        if chips and squad:
            avail = chips_available_for(played_by_gw, gw)
            if avail:
                chip = _pick_chip(
                    evaluate_chips(pool, state, avail, **opt_kw), gw)
        if chip == "wildcard":
            # Unlimited transfers, no hits (the MILP enforces both from
            # wildcard_gw); the new squad is permanent.
            plan = solve_plan(pool, replace(state, wildcard_gw=gw),
                              **opt_kw).gw_plans[0]
        elif chip == "3xc":
            captain_mult = 3
        elif chip == "bboost":
            bench_boost = True
        elif chip == "freehit":
            # One week of a squad conjured out of the whole sell value of
            # the real one; free_transfers=15 only means "nothing here is a
            # hit". Afterwards the real squad and bank come straight back,
            # untouched, so this week's ordinary plan is never executed.
            budget = bank + sum(int(pool_sell.get(c, sell_of.get(c, 0)))
                                for c in squad)
            fh_state = SolveInput(owned_codes=[], bank=budget,
                                  free_transfers=15, gws=[gw],
                                  locked_out=list(state.locked_out))
            plan = solve_plan(pool, fh_state, **opt_kw).gw_plans[0]
            keep_squad = True
        if chip:
            played_by_gw[gw] = chip

        if keep_squad:
            n_buys, hits, buys, sells = 0, 0, [], []
        else:
            n_buys, hits = len(plan.buys), plan.hits
            buys, sells = list(plan.buys), list(plan.sells)
            if not squad:
                bank = STARTING_BUDGET - sum(int(cost_of[c])
                                             for c in plan.squad)
            else:
                bank += (sum(int(pool_sell[c]) for c in plan.sells)
                         - sum(int(cost_of[c]) for c in plan.buys))
            squad = list(plan.squad)
            for c in squad:
                sell_of.setdefault(c, int(cost_of.get(c, 0)))
            for c in plan.buys:
                sell_of[c] = int(cost_of[c])

        actuals = _actuals_frame(rows)
        known = set(actuals["code"])
        missing = [c for c in set(plan.squad) | set(squad) if c not in known]
        if missing:
            actuals = pd.concat([actuals, pd.DataFrame(
                {"code": missing, "total_points": 0, "minutes": 0,
                 "position": [pos_of.get(c, "MID") for c in missing]})],
                ignore_index=True)
        pts = score_gw(actuals, plan.xi, plan.bench, plan.captain, plan.vice,
                       hits, captain_mult=captain_mult,
                       bench_boost=bench_boost)
        total += pts

        if len(log) == 0:          # initial squad build, not transfers
            n_buys, free_transfers = 0, 1
        else:
            # A wildcard's transfers are free and unlimited, and a free hit
            # makes none at all, so both weeks feed the ordinary formula a
            # transfer-free week and simply bank another FT.
            counted = 0 if chip == "wildcard" else n_buys
            free_transfers = min(
                MAX_FREE_TRANSFERS,
                max(0, free_transfers - counted + hits) + 1)
        log.append({"gw": gw, "points": pts, "total": total,
                    "hits": hits, "transfers": n_buys, "chip": chip,
                    "buys": ", ".join(name_of.get(c, str(c)) for c in buys),
                    "sells": ", ".join(name_of.get(c, str(c)) for c in sells),
                    "captain": name_of.get(plan.captain, str(plan.captain)),
                    "bank": bank, "free_transfers": free_transfers,
                    "expected_pts": round(float(plan.expected_pts), 2)})
        print(f"gw{gw}: {pts} (total {total})", flush=True)

    per_gw = round(total / len(log), 2) if log else 0.0
    store.save(pd.DataFrame(log), "live/backtest_log.parquet")
    return {"season": season, "from_gw": start_gw, "total": total,
            "per_gw": per_gw, "log": log, "chips_played": played_by_gw}
