"""Gate G1, v12 §3.5: the xG-per-shot arm on the 2024-25 benchmark.

``us_npxg_per_shot_r{w}`` is shot *quality* beside the shot volume the
attacking model already reads. The claim is narrow and worth stating before
the numbers arrive: two players with the same npxG per 90 are different
players if one takes eight shots for it and the other takes two, and every
Understat column fed today is a volume or a total.

**The pre-registered bar (spec §3.5), against the control arm of this same
run and never against a banked number:**

    KEEP iff  mean haulers RMSE improves
              AND no other bucket's mean worsens by more than that bucket's
                  own seed-spread on the control arm.

Three seed bases, six fits. CONVENTIONS §1: the bar names a seed-spread, and a
spread measured on one draw is not a spread. ``AttackingModel`` takes a
``seed`` (attacking.py:42-52) and it is the only thing that differs between
the three runs of an arm — ``seed_stats.py``'s rule, applied by construction
rather than checked afterwards.

**The lever guards (v10's A12, v9c's lesson).** Three, all before any arm is
scored, because this repo has produced a clean meaningless negative twice. The
driver raises rather than printing a decorated zero.

Run it, watch it, read the verdict::

    mkdir -p logs && caffeinate -i nohup .venv/bin/python \\
        scripts/v12_xgps_arm.py > logs/v12_xgps_arm.log 2>&1 &
    grep -e V12_ARM_DONE -e V12_VERDICT -e V12_ARM_LEVER logs/v12_xgps_arm.log

For scale: v8a's baseline on this benchmark was zeros 1.066 / haulers 5.179 /
all 1.968. That is the loosest of sanity ranges and not a comparison for
either arm — CONVENTIONS §1 — and it is not expected to *reproduce*. Both arms
here are seeded, and ``AttackingModel(seed=)`` merges ``ENSEMBLE_KW`` into its
hyperparameters (attacking.py:49-52, minutes.py:23): a seeded fit bags its
rows and its columns, which the v8a figure's unseeded fit did not. The two arms
are comparable to each other because they differ in features alone; neither is
comparable to a number banked under different hyperparameters.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import gaffer.evaluation as ev
from gaffer.features.engineer import XG_PER_SHOT_FEATURES
from gaffer.models import train as tr

SEED_BASES = (20260901, 20260902, 20260903)
"""Three, per CONVENTIONS §1. Consecutive rather than scattered: they are
LightGBM ``random_state`` values and any three distinct integers are as good
as any other three, so the readable ones are chosen."""

ARMS: dict[str, list[str]] = {
    "baseline": [],
    "xg_per_shot": list(XG_PER_SHOT_FEATURES),
}
"""The eight columns go in as a block: they are one claim measured at four
windows, and a withdrawal here withdraws the claim rather than a column."""

BUCKETS = ("zeros", "blanks", "tickers", "haulers", "all")
"""``evaluation.RETURN_CATEGORIES``, restated so the verdict's loop reads in
the order the bar is written in."""

_cached = None
_real_load = tr.load_training_frame


def _memoised():
    """One ``load_training_frame`` for the whole run, handed out as copies.

    The frame is the expensive half and cannot differ between arms by
    construction; copies mean an arm that mutates its frame cannot poison the
    next one. ``scripts/v10_shrunk_arm.py:88-99``, verbatim in intent.
    """
    global _cached
    if _cached is None:
        _cached = _real_load()
    df, tg, elo = _cached
    return df.copy(), tg.copy(), elo


def arm_features(name: str) -> list[str]:
    from gaffer.models.attacking import ATTACK_FEATURES

    return list(ATTACK_FEATURES) + list(ARMS[name])


def check_lever(df: pd.DataFrame) -> None:
    """Three guards, all before any arm is scored."""
    from gaffer.models.attacking import ATTACK_FEATURES

    base = set(ATTACK_FEATURES)
    for name, cols in ARMS.items():
        if name == "baseline":
            continue
        if set(arm_features(name)) == base:
            raise SystemExit(
                f"the lever is disconnected: arm {name!r} builds the same "
                f"feature list as the control, so both sides would fit the "
                f"same model and every number below would be a zero with a "
                f"name on it.")
        for col in cols:
            if col not in df.columns:
                raise SystemExit(
                    f"{col} is not on the training frame — feature_columns() "
                    f"lists it but load_training_frame did not produce it, so "
                    f"the arm would fail at fit time or silently drop it.")
            series = pd.to_numeric(df[col], errors="coerce")
            if not series.notna().any():
                raise SystemExit(f"{col} is entirely null on this window.")
            if series.nunique(dropna=True) <= 1:
                raise SystemExit(
                    f"{col} is constant on this window — LightGBM will never "
                    f"split on it and the arm is the control by another name.")
    # Guard 4, this cycle's own: the indicator must not be all-1. An Understat
    # parquet that never landed would make every ratio missing, every value
    # 0.0, and the arm a rename of the control that guard 3 cannot see —
    # because a column of all-zeros with a column of all-ones beside it is two
    # constants, and only the pair is suspicious.
    for w_col in [c for c in XG_PER_SHOT_FEATURES if "missing" in c]:
        if float(pd.to_numeric(df[w_col], errors="coerce").mean()) > 0.95:
            raise SystemExit(
                f"{w_col} is raised on more than 95% of rows — the Understat "
                f"shot columns are effectively absent on this window and the "
                f"arm would be the control with eight constants attached.")
    print("V12_ARM_LEVER ok", flush=True)


def run_arm(name: str, seed: int) -> dict:
    """One fit at one seed, then the benchmark's own walk.

    Deliberately a re-walk of ``evaluate_benchmark``'s loop rather than a call
    to it: the bar reads every bucket off the *same* fitted model, and the arm
    is a seed as well as a feature list. Every number is computed by shipped
    code; only the loop is re-written.
    """
    from gaffer.assets import load_bootstrap_sample
    from gaffer.data.bootstrap import scoring_table
    from gaffer.models.assemble import apply_calibration, assemble_ep, ep_matrix
    from gaffer.models.attacking import AttackingModel
    from gaffer.models.train import predict_components_simple, train_all

    df, tg, _ = _memoised()
    train_df, test_df = ev.benchmark_split(df, ev.BENCHMARK_TRAIN_MAX_IDX,
                                           ev.BENCHMARK_TEST_IDX)
    train_tg, _ = ev.benchmark_split(tg, ev.BENCHMARK_TRAIN_MAX_IDX,
                                     ev.BENCHMARK_TEST_IDX)
    models = train_all(train_df, train_tg.dropna(subset=["elo_diff"]),
                       save=False)
    # The intervention, applied where it is measurable: the attacking head is
    # refitted on this arm's columns at this seed, and everything else in
    # ``models`` is the shared fit. train_all's own attacking model is
    # discarded, which is one wasted fit per arm and is the price of not
    # threading a seed through a function six other callers share.
    models["attacking"] = AttackingModel(arm_features(name),
                                         seed=seed).fit(train_df)

    # Guard 3: the fit actually read the arm's columns.
    fitted = set(getattr(models["attacking"], "feature_cols", []))
    for col in ARMS[name]:
        if col not in fitted:
            raise SystemExit(
                f"arm {name!r} was built with {col} but the fitted model's "
                f"feature_cols does not contain it — the intervention is not "
                f"what it says it is (v9c's lesson).")

    scoring = ev.benchmark_scoring(scoring_table(load_bootstrap_sample()))
    parts = []
    for gw in sorted(int(g) for g in test_df["gw"].dropna().unique()):
        rows = test_df[test_df["gw"] == gw].reset_index(drop=True)
        if rows.empty:
            continue
        comp = predict_components_simple(models, rows)
        ep = ep_matrix(apply_calibration(assemble_ep(comp, scoring),
                                         models.get("calibration")))
        truth = rows.groupby(["code", "gw"], as_index=False).agg(
            total_points=("total_points", "sum"), minutes=("minutes", "sum"))
        parts.append(ep.merge(truth, on=["code", "gw"], how="inner"))
        print(f"{name} seed{seed} gw{gw}: {len(parts[-1])} rows", flush=True)

    scored = pd.concat(parts, ignore_index=True)
    table = ev.stratified_metrics(scored["ep"], scored["total_points"])
    return {b: table[b]["rmse"] for b in BUCKETS} | {
        "rows": int(len(scored)),
        "haulers_n": table["haulers"]["n"],
        "zeros_n": table["zeros"]["n"]}


def verdict(base: list[dict], arm: list[dict]) -> dict:
    """The pre-registered rule, applied to the means and the control spread.

    The spread is the control arm's own max-minus-min across the three seeds,
    per bucket. v7b measured a seed spread of 116 points on a replay — larger
    than every arm gap this project has ever gated on — and the whole point of
    naming the spread in the bar is that an arm has to clear the noise it was
    measured in rather than a number somebody liked.
    """
    def mean(rows, key):
        return sum(r[key] for r in rows) / len(rows)

    spread = {b: max(r[b] for r in base) - min(r[b] for r in base)
              for b in BUCKETS}
    deltas = {b: round(mean(arm, b) - mean(base, b), 5) for b in BUCKETS}
    regressions = {b: deltas[b] for b in BUCKETS
                   if b != "haulers" and deltas[b] > spread[b]}
    keep = deltas["haulers"] < 0 and not regressions
    return {"seed_bases": list(SEED_BASES),
            "base_mean": {b: round(mean(base, b), 5) for b in BUCKETS},
            "arm_mean": {b: round(mean(arm, b), 5) for b in BUCKETS},
            "control_spread": {b: round(spread[b], 5) for b in BUCKETS},
            "delta": deltas, "regressions": regressions,
            "decision": "keep" if keep else "withdraw"}


def main() -> None:
    tr.load_training_frame = _memoised
    df, _tg, _elo = _memoised()
    check_lever(df)
    results: dict[str, list[dict]] = {"baseline": [], "xg_per_shot": []}
    try:
        for seed in SEED_BASES:
            for name in ARMS:
                row = run_arm(name, seed)
                results[name].append(row)
                print("V12_ARM_DONE", name, seed, json.dumps(row), flush=True)
    finally:
        tr.load_training_frame = _real_load

    v = verdict(results["baseline"], results["xg_per_shot"])
    print("V12_VERDICT xg_per_shot", json.dumps(v), flush=True)
    Path("reports").mkdir(exist_ok=True)
    Path("reports/v12_xgps_arm.json").write_text(
        json.dumps({"arms": results, "verdict": v}, indent=1))


if __name__ == "__main__":
    main()
