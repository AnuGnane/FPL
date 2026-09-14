"""Gate G3, §F1: did the autosub weighting actually earn points?

The replay (G2) measures the shipped path end to end and is dominated by
transfer dynamics; this measures the thing §F1 changed and nothing else.

One fit on the 2024-25 benchmark split, then, for each gameweek of the test
season, **two squads built from scratch** under the real budget::

    main    solve_plan(pool, state)                    # today
    branch  solve_plan(pool, state, p_play=p_play)     # §F1a/b/c

Both are scored with ``review.score_squad``, which wraps ``backtest.score_gw``
and applies **real autosubs**, the real vice fallback and the real captaincy
rules against 2024-25's actual minutes. Both modules are imported and neither
is modified.

Fresh squads every week rather than a season-long ledger, and deliberately:
the question is "does a better-covered bench score more when someone does not
play", and a transfer ledger would answer it wrapped in thirty-eight weeks of
compounding decisions that §F1 does not touch. The cost of the isolation is
that the number is not a season total and must not be quoted as one.

The headline is restricted to **weeks where an autosub actually fired** —
where at least one XI player recorded zero minutes and a legal bench
replacement existed. On every other week the two arms are scoring the same
eleven and the delta is structurally zero, so pooling them would divide the
real effect by however many quiet weeks there were. Both numbers are printed;
only the first is the gate.

**The lever guard**, this repo's twice-learned lesson: before anything is
scored, the driver asserts that ``_p_play_lookup`` returns non-``None`` on the
first gameweek's pool. If it does not — no p_play, incomplete coverage, or no
spread — both arms are the same arm and every delta below is a decorated zero.
It exits rather than printing one.

Run it, watch it, read the lines::

    mkdir -p logs && caffeinate -i nohup .venv/bin/python \\
        scripts/v10_autosub_cf.py > logs/v10_autosub_cf.log 2>&1 &
    grep -e V10_CF_LEVER -e V10_CF_GW -e V10_CF_DONE logs/v10_autosub_cf.log
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import gaffer.evaluation as ev
from gaffer.backtest import STARTING_BUDGET, _players_frame
from gaffer.optimize.milp import (SolveInput, _p_play_lookup, build_pool,
                                  solve_plan)
from gaffer.review import score_squad

OPT_KW = dict(decay=0.9, bench_weight=0.1, vice_weight=0.1, ft_value=0.0,
              itb_value=0.0, hit_cost=4, ft_use_penalty=0.0,
              bench_curve=[0.21, 0.06, 0.002])
"""The solve both arms share.

A ``bench_curve`` is *required* here and is not read from ``config.toml``
(plan A9): with no curve there are no bench-slot indicators, §F1a has no
outfield weights to scale, and the arm would differ from the control only by
§F1b and §F1c. A gate that measured a third of the feature and reported it as
the feature would be worse than no gate. ``ft_value``/``itb_value`` are zero
and the horizon is one week because every squad here is built from scratch:
there is no next week to bank a transfer for.
"""


def _p_play_by_code(comp: pd.DataFrame, gw: int) -> dict[int, dict[int, float]]:
    """``comp`` -> ``{code: {gw: p_play}}``.

    Grouped ``mean`` per ``(code, gw)``: "did he turn out at all" is one
    outcome, so a doubled-up player's probability is the mean of his fixtures
    and not their sum — ``news_shadow.shadow_rows``' rule, for its reason.
    """
    grouped = (comp[comp["gw"] == int(gw)]
               .groupby("code", as_index=False)
               .agg(p_play=("p_play", "mean")))
    out: dict[int, dict[int, float]] = {}
    for row in grouped.itertuples():
        value = float(row.p_play)
        if value == value and 0.0 <= value <= 1.0:
            out[int(row.code)] = {int(gw): value}
    return out


def _autosub_fired(plan_gw, actuals: pd.DataFrame) -> bool:
    """Did at least one XI player record zero minutes with cover behind him?"""
    minutes = (actuals.groupby("code")["minutes"].sum()
               if not actuals.empty else pd.Series(dtype=float))
    blanks = [c for c in plan_gw.xi if float(minutes.get(c, 0.0)) <= 0.0]
    return bool(blanks) and bool(plan_gw.bench)


def main() -> None:
    from gaffer.assets import load_bootstrap_sample
    from gaffer.data.bootstrap import scoring_table
    from gaffer.models.assemble import apply_calibration, assemble_ep, ep_matrix
    from gaffer.models.train import (load_training_frame,
                                     predict_components_simple, train_all)

    df, tg, _ = load_training_frame()
    train_df, test_df = ev.benchmark_split(df, ev.BENCHMARK_TRAIN_MAX_IDX,
                                           ev.BENCHMARK_TEST_IDX)
    train_tg, _ = ev.benchmark_split(tg, ev.BENCHMARK_TRAIN_MAX_IDX,
                                     ev.BENCHMARK_TEST_IDX)
    models = train_all(train_df, train_tg.dropna(subset=["elo_diff"]),
                       save=False)
    scoring = ev.benchmark_scoring(scoring_table(load_bootstrap_sample()))

    rows: list[dict] = []
    levered = False
    for gw in sorted(int(g) for g in test_df["gw"].dropna().unique()):
        week = test_df[test_df["gw"] == gw].reset_index(drop=True)
        if week.empty:
            continue
        comp = predict_components_simple(models, week)
        ep = ep_matrix(apply_calibration(assemble_ep(comp, scoring),
                                         models.get("calibration")))
        ep_by = {(int(r.code), int(r.gw)): float(r.ep)
                 for r in ep.itertuples()}
        players = _players_frame(week, gw)
        picks = pd.DataFrame(columns=["code", "sell"])
        state = SolveInput(owned_codes=[], bank=STARTING_BUDGET,
                           free_transfers=15, gws=[gw])
        pool = build_pool(players, ep_by, picks, [gw])
        p_play = _p_play_by_code(comp, gw)

        if not levered:
            # The lever guard. Both arms would be the same arm if this were
            # None, and every delta below would be a decorated zero.
            if _p_play_lookup(pool, state, p_play) is None:
                raise SystemExit(
                    "the lever is disconnected: _p_play_lookup returned None "
                    "on the first gameweek's pool, so solve_plan's second "
                    "pass never runs and the branch arm *is* the control.")
            print("V10_CF_LEVER ok", flush=True)
            levered = True

        try:
            base = solve_plan(pool, state, **OPT_KW)
            arm = solve_plan(pool, state, **OPT_KW, p_play=p_play)
        except Exception as exc:  # noqa: BLE001 — one week is not the gate
            print(f"gw{gw}: solve failed ({exc}) — skipped", flush=True)
            continue

        # score_gw's contract (backtest.py:110): [code, total_points, minutes,
        # position], ONE row per player, double gameweeks already aggregated.
        # ``week`` is per-fixture, so aggregate here — sums for the scores,
        # first for the position, which does not change mid-week.
        actuals = (week.groupby("code", as_index=False)
                   .agg(minutes=("minutes", "sum"),
                        total_points=("total_points", "sum"),
                        position=("position", "first")))
        b_gw, a_gw = base.gw_plans[0], arm.gw_plans[0]
        b_pts = score_squad(actuals, xi=b_gw.xi, bench=b_gw.bench,
                            captain=b_gw.captain, vice=b_gw.vice, hits=0)
        a_pts = score_squad(actuals, xi=a_gw.xi, bench=a_gw.bench,
                            captain=a_gw.captain, vice=a_gw.vice, hits=0)
        row = {
            "gw": gw, "main": b_pts, "branch": a_pts,
            "delta": a_pts - b_pts,
            "autosub": _autosub_fired(b_gw, actuals)
                       or _autosub_fired(a_gw, actuals),
            "same_xi": sorted(b_gw.xi) == sorted(a_gw.xi),
            "main_bench": list(b_gw.bench), "branch_bench": list(a_gw.bench),
        }
        rows.append(row)
        print("V10_CF_GW", json.dumps(row), flush=True)

    if not rows:
        raise SystemExit("no gameweek scored — nothing measured.")
    frame = pd.DataFrame(rows)
    fired = frame[frame["autosub"]]
    payload = {
        "autosub_weeks": int(len(fired)),
        "autosub_mean_delta": (round(float(fired["delta"].mean()), 3)
                               if not fired.empty else None),
        "all_weeks": int(len(frame)),
        "all_mean_delta": round(float(frame["delta"].mean()), 3),
        "different_xi_weeks": int((~frame["same_xi"]).sum()),
        "different_bench_weeks": int(
            (frame["main_bench"].map(tuple)
             != frame["branch_bench"].map(tuple)).sum()),
    }
    print("V10_CF_DONE", json.dumps(payload), flush=True)
    Path("reports").mkdir(exist_ok=True)
    Path("reports/v10_autosub_cf.json").write_text(
        json.dumps({"summary": payload, "per_gw": rows}, indent=1))


if __name__ == "__main__":
    main()
