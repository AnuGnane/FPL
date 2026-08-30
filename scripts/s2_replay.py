"""Gate S2: the 2025-26 gated replay, heuristic σ against estimation σ.

The corrected S1 driver, committed. ``run_backtest`` never touches the
scenario machinery — scenario gating is an advise-time feature — so this
injects it the way the v4c gated replay did: stash the component frame the
replay computes each week, derive real xMins from it, and wrap the replay's
BASE solve with ``run_scenarios`` -> ``decide`` -> ``coherent_plan``. Chip
valuation and execution solves (``wildcard_gw`` set, or ``free_transfers ==
15`` for a Free Hit and the opening squad) stay raw, mirroring production.

The arms differ ONLY in the noise scale:

  heur        the pre-v6 (92 - xmins) / 134 heuristic (loader pinned to None)
  estimation  the payload at argv[2], installed through the *shipping* path

The estimation arm deliberately flips ``CALIBRATED_NOISE_DEFAULT`` and stubs
``load_scenario_noise`` rather than threading a ``table=`` kwarg, because
``run_scenarios`` -> ``noised_pool`` passes no table and resolves through
``scenario_noise()``. Flipping the constant is what Task 18 does permanently,
so the gate measures what shipping would actually do.

Usage::

    caffeinate -i nohup .venv/bin/python scripts/s2_replay.py heur \\
        > logs/s2_heur.log 2>&1 &
    caffeinate -i nohup .venv/bin/python scripts/s2_replay.py estimation \\
        reports/scenario_noise_estimation.json > logs/s2_est.log 2>&1 &
    grep S2_ARM_DONE logs/s2_*.log

Ship (spec §3) only if the estimation arm's total is at least the heuristic
arm's minus 5 — a tie is a win for the better-founded noise model — AND
captain sim-support on the current live advise stays at or above 60%.
"""

import json
import sys
from pathlib import Path

import pandas as pd

import gaffer.backtest as bt
import gaffer.optimize.scenarios as sc
from gaffer.optimize.policy import Thresholds, coherent_plan, decide
from gaffer.optimize.scenarios import (move_frequencies, run_scenarios,
                                       xmins_by_player_gw)

mode = sys.argv[1]
assert mode in ("heur", "estimation")
if mode == "heur":
    sc.load_scenario_noise = lambda: None
    sc.scenario_noise.cache_clear()
    assert sc.scenario_noise() is None, "heuristic arm must serve no table"
else:
    payload = json.loads(Path(sys.argv[2]).read_text())
    assert payload.get("source") == "estimation", \
        f"argv[2] is a {payload.get('source')!r} table, not an estimation one"
    sc.CALIBRATED_NOISE_DEFAULT = True
    sc.load_scenario_noise = lambda: payload
    sc.scenario_noise.cache_clear()
    assert sc.scenario_noise() is payload, "asset missing — arm invalid"

_stash: dict = {}
_real_pcs = bt.predict_components_simple


def pcs(models, rows):
    comp = _real_pcs(models, rows)
    _stash["xmins"] = xmins_by_player_gw(comp)
    return comp


bt.predict_components_simple = pcs

_real_solve = bt.solve_plan
gated_weeks = held_weeks = 0


def gated(pool, state, **kw):
    global gated_weeks, held_weeks
    plan = _real_solve(pool, state, **kw)
    if (not state.owned_codes or state.wildcard_gw is not None
            or state.free_transfers >= 15):
        return plan
    xm = _stash.get("xmins") or {}
    if not xm:
        return plan
    gw = int(state.gws[0])
    run = run_scenarios(pool, state, xm, n=40, seed=20260827 + gw, **kw)
    if not run.completed:
        return plan
    gated_weeks += 1
    decision = decide(move_frequencies(run.plans), plan, Thresholds())
    if decision.hold:
        held_weeks += 1
    return coherent_plan(pool, state, decision, **kw)


bt.solve_plan = gated

r = bt.run_backtest(season="2025-26", start_gw=5, horizon=3, chips=True)
d = pd.read_parquet("data/live/backtest_log.parquet")
chip_pts = d[d["chip"] != ""].groupby("chip")["points"].sum().to_dict()
print("S2_ARM_DONE", mode, json.dumps({
    "total": r["total"],
    "hits": int(d["hits"].sum()),
    "transfers": int(d["transfers"].sum()),
    "gated_weeks": gated_weeks,
    "held_weeks": held_weeks,
    "chips_played": r["chips_played"],
    "chip_points": {str(k): int(v) for k, v in chip_pts.items()},
}), flush=True)
