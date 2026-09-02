"""v12 W4 §5.2: the two new minutes arms, pre-registered.

**These are new arms and they are not the withdrawn congestion arm.**
``role_wb_share`` is a *positional* reading of a defender's last five starts,
which nothing in this project has ever had. ``density_pub_7d`` is a count of
*published* fixtures — a forward list — where v5's ``CONGESTION_FEATURES`` and
v8a's ``f2_cups`` counted *played* matches out of an archive that began in
2025-26. Different tables, different quantities, and the spec and the model
quality table say so.

**The arm rule, in full, pre-registered before any arm runs** (spec §5.2's
"the v10 rule", v10 §F3a, and the orchestrator's 2026-09-03 restatement of
both halves). An arm is KEPT only if **both** of these hold:

  (a) *this* driver — the starters-slice ``p_start`` log-loss improves by
      >= :data:`LOGLOSS_MIN_RELATIVE_GAIN` (1%, relative) **and** the zeros
      RMSE gets no worse than :data:`GUARD_TOLERANCE` (0.005); **and**
  (b) ``scripts/v12_w4_autosub_cf.py`` — the mean points delta over the weeks
      in which an autosub actually fired is >= 0.

Either half failing is a withdrawal. This file measures half (a) only, and
:func:`verdict` says so in the payload it writes, because an arm shipped on
one half of a two-half rule is an arm nobody measured for the thing the rule
was written to protect. And if training coverage is zero the arms are **not
measurable** — neither half — and :func:`check_coverage` exits rather than
printing a number, because "not measurable" and "no effect" are different
findings and only one of them is true here.

Every comparison is against the **control arm of this same run** and never
against a banked number (CONVENTIONS §1, §3).

**The window is shifted, deliberately.** ``evaluation`` ships
``BENCHMARK_TRAIN_MAX_IDX = 1`` / ``BENCHMARK_TEST_IDX = 2`` — train 2022-23 +
2023-24, test 2024-25. FPL-Core-Insights' earliest season is 2024-2025, so on
the shipped window both arms are null through the whole of training and the
only thing a fit could learn is "populated implies test season" — which is the
exact confound that withdrew v5's congestion features and made v8a's
``f2_league`` and ``f2_cups`` value-identical. This driver runs at
:data:`TRAIN_MAX_IDX` = 2 and :data:`TEST_IDX` = 3 (train 2022-23..2024-25,
test 2025-26), with the control on the same window. **The numbers here are
therefore not comparable to any banked benchmark figure**, which is why every
printed line carries the window.

**Four lever guards**, all before any arm is scored, because this repo has
produced a clean meaningless negative twice — v9c's rebound lever that was
bound rather than read, and v8a's ``f2_league``/``f2_cups`` pair that were two
lists with identical values on the window:

1. the arm's feature list differs from the control's;
2. every arm column exists on the training frame;
3. no arm column is entirely null or constant on the window;
4. **training coverage is non-zero**, printed per season — the guard this
   archive specifically needs.

Run it, watch it, read the verdicts::

    mkdir -p logs && caffeinate -i nohup .venv/bin/python \\
        scripts/v12_w4_arms.py > logs/v12_w4_arms.log 2>&1 &
    grep -e W4_ARM_LEVER -e W4_COVERAGE -e W4_ARM_DONE -e W4_VERDICT \\
        logs/v12_w4_arms.log
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import gaffer.evaluation as ev
from gaffer.features.engineer import DENSITY_FEATURES, ROLE_FEATURES
from gaffer.models import train as tr

TRAIN_MAX_IDX = 2
TEST_IDX = 3
"""The shifted window. See the module docstring: the shipped
``BENCHMARK_TEST_IDX = 2`` puts every populated row in the test season and
makes both arms season indicators."""

LOGLOSS_MIN_RELATIVE_GAIN = 0.01
"""v10 §F3a's ">= 1%", read as a *relative* improvement — absolute would be
the wrong scale on a loss that sits around 0.3."""

GUARD_TOLERANCE = 0.005
"""v8a's guard, reused unchanged (``scripts/v8a_arms.py:36``). "Zeros RMSE not
worse" with no tolerance would withdraw an arm on solver noise."""

ARM_RULE = (
    "KEEP an arm iff BOTH halves hold: (a) starters-slice p_start log-loss "
    "improves by >= 1% relative to THIS run's control AND zeros RMSE is not "
    "worse by more than 0.005 (this driver); AND (b) the mean points delta "
    "over the weeks in which an autosub actually fired is >= 0 "
    "(scripts/v12_w4_autosub_cf.py). Either half failing is a withdrawal. "
    "train_covered == 0 means the arms are NOT MEASURABLE — neither half — "
    "and no verdict is printed at all."
)
"""The pre-registered rule, as a string, printed on every run and written into
the report. A rule that lives only in a docstring is a rule the person reading
the JSON six weeks from now never sees."""

ARMS: dict[str, list[str]] = {
    "baseline": [],
    "role": list(ROLE_FEATURES),
    "density": list(DENSITY_FEATURES),
}
"""Two arms and one control, each arm's columns going in as a block: the share
and its missing indicator are one claim, and a withdrawal is a withdrawal of
the claim rather than of a column."""

ARM_COLS = ["role_wb_share", "density_pub_7d"]
"""The *value* columns, as opposed to the missing indicators. Coverage is
measured on these — an indicator is never null and would report 100%."""

_cached = None
_real_load = tr.load_training_frame


def _memoised():
    """One ``load_training_frame`` for the whole run, handed out as copies.

    ``scripts/v10_shrunk_arm.py:88-99``, verbatim in intent: the frame is the
    expensive half and cannot differ between arms by construction, and copies
    mean an arm that mutates its frame cannot poison the next one.
    """
    global _cached
    if _cached is None:
        _cached = _real_load()
    df, tg, elo = _cached
    return df.copy(), tg.copy(), elo


def arm_features(name: str) -> list[str]:
    return list(tr.MINUTES_FEATURES) + list(ARMS[name])


def coverage(df: pd.DataFrame, cols: list[str]) -> dict:
    """Non-null share of each arm column, per season, split train vs test.

    The number this archive makes necessary. ``train_covered`` counts rows at
    ``season_idx <= TRAIN_MAX_IDX`` where at least one arm column is
    populated; zero of them means every arm is a season indicator and no
    verdict below would mean anything.

    A column the frame never grew reports zero coverage rather than raising:
    the guard has to be able to *describe* the state it exists to refuse.
    """
    idx = pd.to_numeric(df.get("season_idx"), errors="coerce")
    present = None
    per_season: dict[str, dict[str, float]] = {}
    for col in cols:
        raw = df.get(col)
        series = (pd.to_numeric(raw, errors="coerce") if raw is not None
                  else pd.Series(float("nan"), index=df.index))
        ok = series.notna()
        present = ok if present is None else (present | ok)
        for s in sorted(idx.dropna().unique()):
            rows = idx == s
            n = int(rows.sum())
            per_season.setdefault(str(int(s)), {})[col] = (
                round(float((ok & rows).sum()) / n, 4) if n else 0.0)
    if present is None:
        present = pd.Series(False, index=df.index)
    train = idx <= TRAIN_MAX_IDX
    test = idx == TEST_IDX
    return {"train_max_idx": TRAIN_MAX_IDX, "test_idx": TEST_IDX,
            "per_season": per_season,
            "train_rows": int(train.sum()),
            "train_covered": int((present & train).sum()),
            "test_rows": int(test.sum()),
            "test_covered": int((present & test).sum())}


def check_coverage(report: dict) -> None:
    """Lever guard 4. Exits rather than measuring a season indicator."""
    print("W4_COVERAGE", json.dumps(report), flush=True)
    if report["train_covered"] <= 0:
        raise SystemExit(
            "NOT MEASURABLE — the arms are season indicators on this window: "
            f"zero training rows (season_idx <= {report['train_max_idx']}) "
            "carry either arm column, so all any fit could learn is "
            "'populated implies test season'. Neither half of the arm rule "
            "can be evaluated. Run `gaffer core-insights` first, and if the "
            "archive still publishes nothing before the test season, record "
            "the arms as not measurable rather than running them.")
    if report["test_covered"] <= 0:
        raise SystemExit(
            "NOT MEASURABLE — zero *test* rows carry either arm column, so "
            "both arms would predict the test season with a column that is "
            "null throughout it: a decorated zero.")


def check_lever(df: pd.DataFrame) -> None:
    """Lever guards 1-3 (``scripts/v10_shrunk_arm.py:107-133``)."""
    base = set(arm_features("baseline"))
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
                    f"lists it but load_training_frame did not produce it.")
            series = pd.to_numeric(df[col], errors="coerce")
            if not series.notna().any():
                raise SystemExit(f"{col} is entirely null on this window.")
            if series.nunique(dropna=True) <= 1:
                raise SystemExit(
                    f"{col} is constant on this window — LightGBM will never "
                    f"split on it and the arm is the control by another name.")
    print("W4_ARM_LEVER ok", flush=True)


def run_arm(name: str) -> dict:
    """One fit, then the benchmark's own walk with the modes captured.

    A re-walk of ``evaluation.evaluate_benchmark``'s loop rather than a call to
    it, for ``v10_shrunk_arm``'s reason: the gate needs a ``p_start`` log-loss
    and a zeros RMSE off the *same* fitted model and the shipped function
    returns only the second. Every number is computed by shipped code; only
    the loop and the window are ours.
    """
    from gaffer.assets import load_bootstrap_sample
    from gaffer.data.bootstrap import scoring_table
    from gaffer.models.assemble import apply_calibration, assemble_ep, ep_matrix
    from gaffer.models.train import predict_components_simple, train_all

    df, tg, _ = _memoised()
    train_df, test_df = ev.benchmark_split(df, TRAIN_MAX_IDX, TEST_IDX)
    train_tg, _ = ev.benchmark_split(tg, TRAIN_MAX_IDX, TEST_IDX)
    models = train_all(train_df, train_tg.dropna(subset=["elo_diff"]),
                       save=False)

    fitted = list(getattr(models["minutes"], "feature_cols", []))
    for col in ARMS[name]:
        if col not in fitted:
            raise SystemExit(
                f"arm {name!r} set MINUTES_FEATURES but the fitted model's "
                f"feature_cols does not contain {col} — the module global is "
                f"no longer the whole of the intervention (v9c's lesson).")

    scoring = ev.benchmark_scoring(scoring_table(load_bootstrap_sample()))
    ep_parts, mode_parts = [], []
    for gw in sorted(int(g) for g in test_df["gw"].dropna().unique()):
        rows = test_df[test_df["gw"] == gw].reset_index(drop=True)
        if rows.empty:
            continue
        comp = predict_components_simple(models, rows)
        ep = ep_matrix(apply_calibration(assemble_ep(comp, scoring),
                                         models.get("calibration")))
        truth = rows.groupby(["code", "gw"], as_index=False).agg(
            total_points=("total_points", "sum"), minutes=("minutes", "sum"))
        ep_parts.append(ep.merge(truth, on=["code", "gw"], how="inner"))
        modes = models["minutes"].predict_modes(rows)
        mode_parts.append(pd.DataFrame({
            "p_start": pd.to_numeric(modes["p_start"], errors="coerce").values,
            "minutes": pd.to_numeric(rows["minutes"], errors="coerce").values,
            "started": ev.start_truth(rows).values}))
        print(f"{name} (train<={TRAIN_MAX_IDX} test={TEST_IDX}) gw{gw}: "
              f"{len(ep_parts[-1])} rows", flush=True)

    if not ep_parts:
        raise SystemExit(
            f"the test window (season_idx {TEST_IDX}) has no rows — the "
            f"configured train_seasons do not reach it.")
    scored = pd.concat(ep_parts, ignore_index=True)
    heads = pd.concat(mode_parts, ignore_index=True)
    starters = heads[pd.to_numeric(heads["minutes"], errors="coerce")
                     .fillna(0.0) >= ev.STARTER_MINUTES]
    table = ev.stratified_metrics(scored["ep"], scored["total_points"])
    return {
        "train_max_idx": TRAIN_MAX_IDX, "test_idx": TEST_IDX,
        "zeros": table["zeros"]["rmse"], "zeros_n": table["zeros"]["n"],
        "haulers": table["haulers"]["rmse"], "all": table["all"]["rmse"],
        "p_start_ll_starters": round(
            float(ev.log_loss(starters["p_start"], starters["started"])), 5),
        "p_start_ll_all": round(
            float(ev.log_loss(heads["p_start"], heads["started"])), 5),
        "starters_n": int(len(starters)), "rows": int(len(heads)),
    }


def verdict(base: dict, arm: dict) -> dict:
    """Half (a) of the pre-registered rule, applied to one arm.

    ``decision`` is this driver's half and nothing more: a ``keep`` here is a
    keep **subject to** half (b), the autosub-week counterfactual, and the
    payload says which half it is so that a reader of ``reports/`` cannot
    mistake one half for the whole rule. See :data:`ARM_RULE`.
    """
    b, a = base["p_start_ll_starters"], arm["p_start_ll_starters"]
    gain = (b - a) / b if b else 0.0
    zeros_cost = arm["zeros"] - base["zeros"]
    keep = gain >= LOGLOSS_MIN_RELATIVE_GAIN and zeros_cost <= GUARD_TOLERANCE
    return {"logloss_relative_gain": round(gain, 5),
            "zeros_cost": round(zeros_cost, 5),
            "decision": "keep" if keep else "withdraw",
            "half": "a",
            "keep_also_requires":
                "half (b): scripts/v12_w4_autosub_cf.py, mean points delta "
                "over autosub weeks >= 0",
            "rule": ARM_RULE}


def main() -> None:
    print("W4_ARM_RULE", ARM_RULE, flush=True)
    tr.load_training_frame = _memoised
    shipped = list(tr.MINUTES_FEATURES)
    df, _tg, _elo = _memoised()
    check_coverage(coverage(df, ARM_COLS))
    check_lever(df)
    results: dict[str, dict] = {}
    try:
        for name in ARMS:
            # One statement, and that is the point: ``arm_features`` reads the
            # module global, so assigning the shipped list and then composing
            # onto the global would leave arm n+1 built on top of arm n and
            # report the union of two arms under the second one's name.
            tr.MINUTES_FEATURES = list(shipped) + list(ARMS[name])
            results[name] = run_arm(name)
            print("W4_ARM_DONE", name, json.dumps(results[name]), flush=True)
    finally:
        tr.MINUTES_FEATURES = shipped
        tr.load_training_frame = _real_load

    verdicts = {name: verdict(results["baseline"], results[name])
                for name in ARMS if name != "baseline"}
    for name, v in verdicts.items():
        print("W4_VERDICT", name, json.dumps(v), flush=True)
    Path("reports").mkdir(exist_ok=True)
    Path("reports/v12_w4_arms.json").write_text(
        json.dumps({"window": {"train_max_idx": TRAIN_MAX_IDX,
                               "test_idx": TEST_IDX},
                    "rule": ARM_RULE,
                    "arms": results, "verdicts": verdicts}, indent=1))


if __name__ == "__main__":
    main()
