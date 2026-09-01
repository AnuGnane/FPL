"""Gate G1, §F3a: the SHRUNK_MODE_FEATURES arm on the 2024-25 benchmark.

``shrunk_start_rate`` and ``shrunk_min_per_app`` (engineer.py:1043) were built
in v5 and no head has ever claimed them. v5's gate N1 measured them, but it
measured them *bundled with congestion* — zeros RMSE 1.082-1.084 against
1.069-1.073 — and attributed the regression to the congestion half, whose cup
archive holds no rows at or before 2024-25 and is therefore partly a season
indicator on this window (train.py:66-72). The two halves were never
separated. This separates them: the arm is the mode rates alone, on a
benchmark the confounder is not in.

The pre-registered bar (spec §F3a), against the *control arm of this same
run* and never against a banked number:

    KEEP iff  starters-slice p_start log-loss improves by >= 1% (relative)
              AND zeros RMSE does not get worse by more than GUARD_TOLERANCE.

Both numbers come from **one fit per arm**. Calling ``evaluate_benchmark`` for
the RMSE and re-fitting for the modes would compare a log-loss from one model
against an RMSE from another, so the benchmark's own loop is re-walked here
with ``predict_modes`` captured alongside. Every piece of arithmetic is the
shipped one: ``benchmark_split``, ``train_all``, ``predict_components_simple``,
``assemble_ep``, ``ep_matrix``, ``stratified_metrics``, ``log_loss``,
``start_truth``, ``STARTER_MINUTES``.

**On the metric.** The starters slice is ``minutes >= STARTER_MINUTES``, the
house definition. On it, truth is almost always 1.0, so the log-loss is close
to ``-mean(log p_start)`` — a confidence score, and one an arm could game by
calling everyone a starter. The zeros guard is what makes that unprofitable:
an arm that does it inflates EP for the players who did not play, and that
lands in the zeros stratum. The two numbers are printed on one line for
exactly this reason, and the whole-frame log-loss rides along as a companion.

**The lever guards (plan A12).** Three, all before any arm is scored, because
this repo has produced a clean meaningless negative twice — v9c's rebound
lever that was bound rather than read, and v8a's f2_league/f2_cups pair that
were two lists with identical values on the window. The driver raises rather
than printing a decorated zero.

Run it, watch it, read the verdict::

    mkdir -p logs && caffeinate -i nohup .venv/bin/python \\
        scripts/v10_shrunk_arm.py > logs/v10_shrunk_arm.log 2>&1 &
    grep -e V10_ARM_DONE -e V10_VERDICT -e V10_ARM_LEVER logs/v10_shrunk_arm.log

For scale: v8a's baseline on this benchmark was zeros 1.066 / haulers 5.179 /
all 1.968 over 16279 zeros rows. That is a sanity range for the control arm,
not a comparison for the arm — CONVENTIONS §1, and scripts/replay_pair.sh's
own header, on why a banked number from an earlier cycle is not evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import gaffer.evaluation as ev
from gaffer.features.engineer import SHRUNK_MODE_FEATURES
from gaffer.models import train as tr

LOGLOSS_MIN_RELATIVE_GAIN = 0.01
"""Spec §F3a's "improves >= 1%", read as a *relative* improvement.

Absolute would be the wrong scale: a log-loss on a near-degenerate slice sits
around 0.1-0.3, and 0.01 absolute there is a 5-10% move that no feature pair
is going to make. Relative is what "1%" means about a loss.
"""

GUARD_TOLERANCE = 0.005
"""v8a's guard, reused unchanged (scripts/v8a_arms.py:36). "Zeros RMSE not
worse" with no tolerance at all would withdraw an arm on the fourth decimal
of solver noise."""

ARMS: dict[str, list[str]] = {
    "baseline": [],
    "shrunk_modes": list(SHRUNK_MODE_FEATURES),
}
"""One arm, one control. The two columns go in as a block because they are one
claim measured two ways — the same treatment v8a gave ``f2_cups`` — and
because a withdrawal here is a withdrawal of the claim, not of a column."""

_cached = None
_real_load = tr.load_training_frame


def _memoised():
    """One ``load_training_frame`` for the whole run, handed out as copies.

    The frame is the expensive half and cannot differ between arms by
    construction; copies mean an arm that mutates its frame cannot poison the
    next one. ``scripts/v8a_arms.py:53-67``, verbatim in intent.
    """
    global _cached
    if _cached is None:
        _cached = _real_load()
    df, tg, elo = _cached
    return df.copy(), tg.copy(), elo


def arm_features(name: str) -> list[str]:
    """The feature list this arm trains the minutes model on."""
    return list(tr.MINUTES_FEATURES) + list(ARMS[name])


def check_lever(df: pd.DataFrame) -> None:
    """Plan A12. Raises rather than reporting a decorated zero."""
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
                    f"lists it (engineer.py:853) but load_training_frame did "
                    f"not produce it, so the arm would fail at fit time or, "
                    f"worse, silently drop it.")
            series = pd.to_numeric(df[col], errors="coerce")
            if not series.notna().any():
                raise SystemExit(f"{col} is entirely null on this window.")
            if series.nunique(dropna=True) <= 1:
                raise SystemExit(
                    f"{col} is constant on this window — LightGBM will never "
                    f"split on it and the arm is the control by another name.")
    print("V10_ARM_LEVER ok", flush=True)


def run_arm(name: str) -> dict:
    """One fit, then the benchmark's own walk, with the modes captured.

    Deliberately a re-walk of ``evaluation.evaluate_benchmark``'s loop rather
    than a call to it: the gate needs a p_start log-loss and a zeros RMSE off
    the *same* fitted model, and the shipped function returns only the second.
    Every number is computed by shipped code; only the loop is re-written.
    """
    from gaffer.assets import load_bootstrap_sample
    from gaffer.data.bootstrap import scoring_table
    from gaffer.models.assemble import apply_calibration, assemble_ep, ep_matrix
    from gaffer.models.train import predict_components_simple, train_all

    df, tg, _ = _memoised()
    train_df, test_df = ev.benchmark_split(df, ev.BENCHMARK_TRAIN_MAX_IDX,
                                           ev.BENCHMARK_TEST_IDX)
    train_tg, _ = ev.benchmark_split(tg, ev.BENCHMARK_TRAIN_MAX_IDX,
                                     ev.BENCHMARK_TEST_IDX)
    models = train_all(train_df, train_tg.dropna(subset=["elo_diff"]),
                       save=False)

    # Guard 3: the fit actually read the arm's columns.
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
        print(f"{name} gw{gw}: {len(ep_parts[-1])} rows", flush=True)

    scored = pd.concat(ep_parts, ignore_index=True)
    heads = pd.concat(mode_parts, ignore_index=True)
    starters = heads[pd.to_numeric(heads["minutes"], errors="coerce")
                     .fillna(0.0) >= ev.STARTER_MINUTES]
    table = ev.stratified_metrics(scored["ep"], scored["total_points"])
    return {
        "zeros": table["zeros"]["rmse"],
        "zeros_n": table["zeros"]["n"],
        "all": table["all"]["rmse"],
        "p_start_ll_starters": round(
            float(ev.log_loss(starters["p_start"], starters["started"])), 5),
        "p_start_ll_all": round(
            float(ev.log_loss(heads["p_start"], heads["started"])), 5),
        "starters_n": int(len(starters)),
        "rows": int(len(heads)),
    }


def verdict(base: dict, arm: dict) -> dict:
    """The pre-registered rule, applied to the arm against the control."""
    b, a = base["p_start_ll_starters"], arm["p_start_ll_starters"]
    gain = (b - a) / b if b else 0.0
    zeros_cost = arm["zeros"] - base["zeros"]
    keep = gain >= LOGLOSS_MIN_RELATIVE_GAIN and zeros_cost <= GUARD_TOLERANCE
    return {"logloss_relative_gain": round(gain, 5),
            "zeros_cost": round(zeros_cost, 5),
            "decision": "keep" if keep else "withdraw"}


def main() -> None:
    tr.load_training_frame = _memoised
    shipped = list(tr.MINUTES_FEATURES)
    df, _tg, _elo = _memoised()
    check_lever(df)
    results: dict[str, dict] = {}
    try:
        for name in ARMS:
            # Restore the shipped list before reading it: ``arm_features``
            # composes off the module global, so without this an arm would
            # inherit the previous arm's columns. With one arm and a
            # baseline it happens not to bite; a second arm would make it a
            # silent contamination rather than a failure.
            tr.MINUTES_FEATURES = shipped
            tr.MINUTES_FEATURES = arm_features(name)
            results[name] = run_arm(name)
            print("V10_ARM_DONE", name, json.dumps(results[name]), flush=True)
    finally:
        tr.MINUTES_FEATURES = shipped
        tr.load_training_frame = _real_load

    v = verdict(results["baseline"], results["shrunk_modes"])
    print("V10_VERDICT shrunk_modes", json.dumps(v), flush=True)
    Path("reports").mkdir(exist_ok=True)
    Path("reports/v10_shrunk_arm.json").write_text(
        json.dumps({"arms": results, "verdict": v}, indent=1))


if __name__ == "__main__":
    main()
