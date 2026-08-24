"""Season replay: what would the tool have scored, week by week.

The harness re-runs the whole pipeline over a finished season. At each
gameweek it retrains on data strictly before that gameweek, predicts every
component, solves for the squad, then scores the resulting XI against what
actually happened. Nothing downstream of the deadline is ever visible to the
model: ``load_training_frame(max_season_idx, max_gw)`` truncates the training
frame, and the per-gameweek feature rows are leakage-safe by construction —
:func:`gaffer.features.engineer.add_player_rolling` shifts every rolling
window one match back, so a GW row's features only see earlier matches.

Two joins repeat the lessons the weekly advisor learned the hard way:
component predictions are stitched **positionally** (``predict`` returns one
row per input row in input order, and ``(code, gw)`` is not unique in a
double gameweek), and double-gameweek actuals are aggregated per code before
scoring while the expected-points side is collapsed by ``ep_matrix``.

v1 simplifications — all of them conservative, i.e. they understate what the
tool would really have scored:

* **No chips.** No wildcard, free hit, bench boost or triple captain is ever
  played, so the replay forgoes every points spike a chip would have bought.
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
* **Single-gameweek optimization** (``gws=[gw]``): the MILP maximises this
  week only, with no multi-week horizon, no free-transfer planning value and
  no fixture-swing anticipation.
"""

from __future__ import annotations

from collections import Counter

import pandas as pd

from gaffer.assets import load_bootstrap_sample
from gaffer.config import load_config
from gaffer.data import store
from gaffer.data.bootstrap import scoring_table
from gaffer.models.assemble import apply_calibration, assemble_ep, ep_matrix
from gaffer.models.train import (DEFAULT_E_GC, DEFAULT_P_CS,  # noqa: F401
                                 load_training_frame,
                                 predict_components_simple, train_all)
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
             captain: int, vice: int, hits: int) -> int:
    """Actual FPL points for one gameweek's team.

    ``actuals``: [code, total_points, minutes, position], one row per player
    (double gameweeks already aggregated). Codes missing from the frame are
    treated as 0 points / 0 minutes, which is what a player who did not
    feature at all scored.
    """
    pts_of = dict(zip(actuals["code"], actuals["total_points"]))
    mins_of = dict(zip(actuals["code"], actuals["minutes"]))
    pos_of = dict(zip(actuals["code"], actuals["position"]))

    def played(code) -> bool:
        return float(mins_of.get(code, 0) or 0) > 0

    xi = list(xi)
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

    total = sum(float(pts_of.get(c, 0) or 0) for c in xi)
    if played(captain):
        total += float(pts_of.get(captain, 0) or 0)
    elif played(vice):
        total += float(pts_of.get(vice, 0) or 0)
    return int(round(total - 4 * hits))


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


def _actuals_frame(rows: pd.DataFrame) -> pd.DataFrame:
    """Per-code actual points and minutes, double gameweeks summed."""
    return (rows.groupby("code", as_index=False)
            .agg(total_points=("total_points", "sum"),
                 minutes=("minutes", "sum"),
                 position=("position", "first")))


def run_backtest(season: str = "2025-26", start_gw: int = 5,
                 retrain_every: int = 4) -> dict:
    """Replay ``season`` from ``start_gw`` to GW38 following the tool.

    Returns {"season", "from_gw", "total", "per_gw", "log"} and writes the
    per-gameweek log to ``data/live/backtest_log.parquet``.
    """
    cfg = load_config()
    season_idx = cfg.train_seasons.index(season)
    opt_kw = dict(decay=cfg.decay, bench_weight=cfg.bench_weight,
                  vice_weight=cfg.vice_weight, ft_value=cfg.ft_value,
                  itb_value=cfg.itb_value, hit_cost=cfg.hit_cost)
    scoring = scoring_table(load_bootstrap_sample())

    full, _, _ = load_training_frame()
    season_rows = full[full["season_idx"] == season_idx]

    models: dict = {}
    squad: list[int] = []
    bank = STARTING_BUDGET
    free_transfers = 1
    sell_of: dict[int, int] = {}
    pos_of: dict[int, str] = {}
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

        comp = predict_components_simple(models, rows)
        ep = ep_matrix(apply_calibration(assemble_ep(comp, scoring),
                                         models.get("calibration")))
        ep_by = {(int(r.code), int(r.gw)): float(r.ep) for r in ep.itertuples()}
        players = _players_frame(season_rows, gw)
        pos_of.update(dict(zip(players["code"], players["position"])))
        name_of = dict(zip(players["code"], players["name"]))

        if not squad:
            picks = pd.DataFrame(columns=["code", "sell"])
            state = SolveInput(owned_codes=[], bank=STARTING_BUDGET,
                               free_transfers=15, gws=[gw])
        else:
            # sell price = this gameweek's value (see module docstring)
            price_now = dict(zip(players["code"], players["now_cost"]))
            for c in squad:
                sell_of[c] = int(price_now.get(c, sell_of.get(c, 0)))
            picks = pd.DataFrame({"code": squad,
                                  "sell": [sell_of[c] for c in squad]})
            state = SolveInput(owned_codes=list(squad), bank=bank,
                               free_transfers=free_transfers, gws=[gw])

        pool = build_pool(players, ep_by, picks, [gw])
        plan = solve_plan(pool, state, **opt_kw).gw_plans[0]

        cost_of = dict(zip(pool["code"], pool["cost"]))
        pool_sell = dict(zip(pool["code"], pool["sell"]))
        if not squad:
            bank = STARTING_BUDGET - sum(int(cost_of[c]) for c in plan.squad)
        else:
            bank += (sum(int(pool_sell[c]) for c in plan.sells)
                     - sum(int(cost_of[c]) for c in plan.buys))
        squad = list(plan.squad)
        for c in squad:
            sell_of.setdefault(c, int(cost_of.get(c, 0)))
        for c in plan.buys:
            sell_of[c] = int(cost_of[c])

        actuals = _actuals_frame(rows)
        missing = [c for c in squad if c not in set(actuals["code"])]
        if missing:
            actuals = pd.concat([actuals, pd.DataFrame(
                {"code": missing, "total_points": 0, "minutes": 0,
                 "position": [pos_of.get(c, "MID") for c in missing]})],
                ignore_index=True)
        pts = score_gw(actuals, plan.xi, plan.bench, plan.captain, plan.vice,
                       plan.hits)
        total += pts

        if len(log) == 0:          # initial squad build, not transfers
            n_buys, free_transfers = 0, 1
        else:
            n_buys = len(plan.buys)
            free_transfers = min(
                MAX_FREE_TRANSFERS,
                max(0, free_transfers - n_buys + plan.hits) + 1)
        log.append({"gw": gw, "points": pts, "total": total,
                    "hits": plan.hits, "transfers": n_buys,
                    "buys": ", ".join(name_of.get(c, str(c))
                                      for c in plan.buys),
                    "sells": ", ".join(name_of.get(c, str(c))
                                       for c in plan.sells),
                    "captain": name_of.get(plan.captain, str(plan.captain)),
                    "bank": bank, "free_transfers": free_transfers,
                    "expected_pts": round(float(plan.expected_pts), 2)})
        print(f"gw{gw}: {pts} (total {total})", flush=True)

    per_gw = round(total / len(log), 2) if log else 0.0
    store.save(pd.DataFrame(log), "live/backtest_log.parquet")
    return {"season": season, "from_gw": start_gw, "total": total,
            "per_gw": per_gw, "log": log}
