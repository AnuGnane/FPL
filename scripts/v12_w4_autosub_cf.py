"""v12 W4 §5.2, the decision half: do the new arms earn points on autosub
weeks?

``scripts/v12_w4_arms.py`` measures the arms' *predictions*. This measures
whether a better ``p_play`` changes a squad that the real week then rewards,
which is the question the bucket RMSE cannot answer and the one spec §5.2
means by "the v10 rule … autosub-week counterfactual".

**The arm rule, in full** (spec §5.2's "the v10 rule", v10 §F3a, and the
orchestrator's 2026-09-03 restatement of both halves). An arm is KEPT only if
**both** hold:

  (a) ``scripts/v12_w4_arms.py`` — the starters-slice ``p_start`` log-loss
      improves by >= 1% relative to that run's own control **and** the zeros
      RMSE gets no worse than 0.005; **and**
  (b) *this* driver — the mean points delta over the weeks in which an autosub
      actually fired is >= 0.

Either half failing is a withdrawal; neither half alone ships an arm. And when
``train_covered == 0`` the arms are **not measurable** rather than neutral —
:func:`v12_w4_arms.check_coverage` is called here first, and exits, for
exactly that reason.

``scripts/v10_autosub_cf.py`` is the template and the differences are two.
There, both arms were the same fitted model into two solvers; here both arms
are two *fitted models* into the same solver, so the fit is inside the arm
loop and the memoised frame is the only thing shared. And the window is
:mod:`v12_w4_arms`' shifted one, for that module's reason — the archive's
earliest season is the shipped benchmark's test season.

The headline is restricted to **weeks where an autosub actually fired**: on
every other week the two arms score the same eleven and the delta is
structurally zero, so pooling would divide the real effect by however many
quiet weeks there were. Both numbers are printed; only the first is the gate.

**The lever guard**: before anything is scored, the driver asserts that the
two arms' ``p_play`` dicts actually differ on the first gameweek. If they do
not, both arms are the same arm and every delta is a decorated zero.

**Runtime**: the longer of the two by a distance — three ``train_all`` fits,
as in :mod:`v12_w4_arms`, *plus* a MILP solve per arm per test gameweek, so
roughly 38 x 3 solves on a full season on top of the fits. Hours, not minutes;
run it under ``caffeinate`` and read the ``W4_CF_GW`` lines as they land.

Run it, watch it, read the lines::

    mkdir -p logs && caffeinate -i nohup .venv/bin/python \\
        scripts/v12_w4_autosub_cf.py > logs/v12_w4_autosub_cf.log 2>&1 &
    grep -e W4_CF_LEVER -e W4_CF_GW -e W4_CF_DONE logs/v12_w4_autosub_cf.log
"""

from __future__ import annotations

import importlib.util as _ilu
import json
from pathlib import Path

import pandas as pd

import gaffer.evaluation as ev
from gaffer.backtest import STARTING_BUDGET, _players_frame
from gaffer.models import train as tr
from gaffer.optimize.milp import SolveInput, build_pool, solve_plan
from gaffer.review import score_squad

_spec = _ilu.spec_from_file_location(
    "v12_w4_arms", Path(__file__).with_name("v12_w4_arms.py"))
arms_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(arms_mod)
"""The arm definitions, the window and the rule, loaded from the sibling
driver rather than copied. Two files disagreeing about which columns an arm
is, is how a cycle ends up reporting one arm's numbers under another arm's
name."""

OPT_KW = dict(decay=0.9, bench_weight=0.1, vice_weight=0.1, ft_value=0.0,
              itb_value=0.0, hit_cost=4, ft_use_penalty=0.0,
              bench_curve=[0.21, 0.06, 0.002])
"""The solve every arm shares, ``scripts/v10_autosub_cf.py:56-58`` verbatim.

The ``bench_curve`` is required and is not read from ``config.toml``: with no
curve there are no bench-slot indicators and a better ``p_play`` has nothing
to move. ``ft_value``/``itb_value`` are zero and the horizon is one week
because every squad here is built from scratch — there is no next week to bank
a transfer for.
"""


def _p_play_by_code(comp: pd.DataFrame, gw: int) -> dict[int, dict[int, float]]:
    """``comp`` -> ``{code: {gw: p_play}}``.

    Grouped ``mean`` per ``(code, gw)``: "did he turn out at all" is one
    outcome, so a doubled-up player's probability is the mean of his fixtures
    and not their sum — ``news_shadow.shadow_rows``' rule, for its reason, and
    ``scripts/v10_autosub_cf.py:71-86`` verbatim.
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


def _fit(arm: str, train_df, train_tg):
    """One arm's models, with ``MINUTES_FEATURES`` restored afterwards.

    The composition is one statement for :mod:`v12_w4_arms`' reason:
    ``arm_features`` reads the module global, so a driver that assigned the
    shipped list and then composed onto it would build arm n+1 on top of
    arm n. Here ``shipped`` is captured before the assignment and restored in
    the ``finally``, so every arm composes from the same base.

    What is added is ``arms_mod.arm_additions``' answer and not the raw arm
    list: W4 shipped ``role``, so its columns are inside ``shipped`` already
    and naming them again would hand LightGBM a duplicated feature name.
    """
    from gaffer.models.train import train_all

    shipped = list(tr.MINUTES_FEATURES)
    adds = arms_mod.arm_additions(arm, shipped)
    try:
        tr.MINUTES_FEATURES = list(shipped) + adds
        return train_all(train_df, train_tg.dropna(subset=["elo_diff"]),
                         save=False)
    finally:
        tr.MINUTES_FEATURES = shipped


def main() -> None:
    from gaffer.assets import load_bootstrap_sample
    from gaffer.data.bootstrap import scoring_table
    from gaffer.models.assemble import apply_calibration, assemble_ep, ep_matrix
    from gaffer.models.train import (load_training_frame,
                                     predict_components_simple)

    print("W4_CF_RULE", arms_mod.ARM_RULE, flush=True)
    df, tg, _ = load_training_frame()
    arms_mod.check_coverage(arms_mod.coverage(df, arms_mod.ARM_COLS))
    arms_mod.check_lever(df)

    train_df, test_df = ev.benchmark_split(df, arms_mod.TRAIN_MAX_IDX,
                                           arms_mod.TEST_IDX)
    train_tg, _ = ev.benchmark_split(tg, arms_mod.TRAIN_MAX_IDX,
                                     arms_mod.TEST_IDX)
    fits = {name: _fit(name, train_df, train_tg) for name in arms_mod.ARMS}
    scoring = ev.benchmark_scoring(scoring_table(load_bootstrap_sample()))

    rows: list[dict] = []
    levered = False
    for gw in sorted(int(g) for g in test_df["gw"].dropna().unique()):
        week = test_df[test_df["gw"] == gw].reset_index(drop=True)
        if week.empty:
            continue
        players = _players_frame(week, gw)
        picks = pd.DataFrame(columns=["code", "sell"])
        state = SolveInput(owned_codes=[], bank=STARTING_BUDGET,
                           free_transfers=15, gws=[gw])
        squads: dict[str, object] = {}
        p_plays: dict[str, dict] = {}
        failed = False
        for name, models in fits.items():
            comp = predict_components_simple(models, week)
            ep = ep_matrix(apply_calibration(assemble_ep(comp, scoring),
                                             models.get("calibration")))
            ep_by = {(int(r.code), int(r.gw)): float(r.ep)
                     for r in ep.itertuples()}
            pool = build_pool(players, ep_by, picks, [gw])
            p_plays[name] = _p_play_by_code(comp, gw)
            try:
                squads[name] = solve_plan(pool, state, **OPT_KW,
                                          p_play=p_plays[name]).gw_plans[0]
            except Exception as exc:  # noqa: BLE001 — one week is not the gate
                print(f"gw{gw}: {name} solve failed ({exc}) — week skipped",
                      flush=True)
                failed = True
                break
        if failed:
            continue

        if not levered:
            # Both arms would be the same arm if their p_play agreed, and
            # every delta below would be a decorated zero.
            same = all(p_plays[n] == p_plays["baseline"]
                       for n in arms_mod.ARMS if n != "baseline")
            if same:
                raise SystemExit(
                    "the lever is disconnected: every arm produced the same "
                    "p_play as the control on the first gameweek, so all "
                    "three squads are one squad.")
            print("W4_CF_LEVER ok", flush=True)
            levered = True

        # score_gw's contract (backtest.py:110): [code, total_points, minutes,
        # position], ONE row per player, double gameweeks already aggregated.
        actuals = (week.groupby("code", as_index=False)
                   .agg(minutes=("minutes", "sum"),
                        total_points=("total_points", "sum"),
                        position=("position", "first")))
        points = {name: score_squad(actuals, xi=plan.xi, bench=plan.bench,
                                    captain=plan.captain, vice=plan.vice,
                                    hits=0)
                  for name, plan in squads.items()}
        row = {"gw": gw, **{f"pts_{n}": points[n] for n in points},
               **{f"delta_{n}": points[n] - points["baseline"]
                  for n in points if n != "baseline"},
               "autosub": any(_autosub_fired(p, actuals)
                              for p in squads.values()),
               **{f"same_xi_{n}": sorted(squads[n].xi)
                  == sorted(squads["baseline"].xi)
                  for n in squads if n != "baseline"},
               **{f"bench_{n}": list(squads[n].bench) for n in squads}}
        rows.append(row)
        print("W4_CF_GW", json.dumps(row), flush=True)

    if not rows:
        raise SystemExit("no gameweek scored — nothing measured.")
    frame = pd.DataFrame(rows)
    fired = frame[frame["autosub"]]
    payload = {"window": {"train_max_idx": arms_mod.TRAIN_MAX_IDX,
                          "test_idx": arms_mod.TEST_IDX},
               "rule": arms_mod.ARM_RULE,
               "half": "b",
               "autosub_weeks": int(len(fired)), "all_weeks": int(len(frame))}
    for name in arms_mod.ARMS:
        if name == "baseline":
            continue
        mean_delta = (round(float(fired[f"delta_{name}"].mean()), 3)
                      if not fired.empty else None)
        payload[name] = {
            "autosub_mean_delta": mean_delta,
            # Half (b) of the rule, evaluated here rather than left to a
            # reader's arithmetic. ``None`` — no week fired an autosub — is
            # "not measurable", not a pass.
            "half_b": ("not measurable" if mean_delta is None
                       else "pass" if mean_delta >= 0 else "fail"),
            "all_mean_delta": round(float(frame[f"delta_{name}"].mean()), 3),
            "different_xi_weeks": int((~frame[f"same_xi_{name}"]).sum()),
            "different_bench_weeks": int(
                (frame[f"bench_{name}"].map(tuple)
                 != frame["bench_baseline"].map(tuple)).sum())}
    print("W4_CF_DONE", json.dumps(payload), flush=True)
    Path("reports").mkdir(exist_ok=True)
    Path("reports/v12_w4_autosub_cf.json").write_text(
        json.dumps({"summary": payload, "per_gw": rows}, indent=1))


if __name__ == "__main__":
    main()
