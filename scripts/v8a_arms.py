"""Gate G1: the v8a feature arms on the 2024-25 walk-forward benchmark.

One run of ``evaluate_benchmark`` per arm over one memoised training frame.
An arm is a *feature list*: ``train.MINUTES_FEATURES`` is read as a module
global by ``train_all``, so setting it is the whole of the intervention and
nothing in the shipped code moves. The frame is memoised because it is the
expensive half of the run and cannot differ between arms by construction; it
hands back copies, so an arm that mutates its frame cannot poison the next.

Run it, watch it, read the verdicts::

    caffeinate -i nohup .venv/bin/python scripts/v8a_arms.py \\
        > logs/v8a_arms.log 2>&1 &
    grep -e V8A_ARM_DONE -e V8A_VERDICT logs/v8a_arms.log

The pre-registered rule (v8a spec §6, G1), each arm against the *baseline arm
of this same run* rather than against a banked number: KEEP iff zeros RMSE
improves by at least :data:`ZEROS_MIN_GAIN` AND neither haulers RMSE nor
all-stratum RMSE regresses by more than :data:`GUARD_TOLERANCE`. Ties and
marginals withdraw. This script prints the comparison; the shipping decision
is the orchestrator's, and Task 17 of the plan is where a kept arm lands.
"""

from __future__ import annotations

import json
from pathlib import Path

import gaffer.evaluation as ev
from gaffer.features.engineer import (CONGESTION_FEATURES,
                                      LEAGUE_CONGESTION_FEATURES,
                                      ROTATION_PRIOR_FEATURES)
from gaffer.models import train as tr

ZEROS_MIN_GAIN = 0.005
GUARD_TOLERANCE = 0.005

ARMS: dict[str, list[str]] = {
    "baseline": [],
    **{f"f1_{col}": [col] for col in ROTATION_PRIOR_FEATURES},
    "f2_league": list(LEAGUE_CONGESTION_FEATURES),
    "f2_cups": list(CONGESTION_FEATURES),
}
"""One arm per candidate. F1's four features are ablated individually because
a withdrawal has to be targetable; F2's two variants are blocks because
"congestion" is one claim measured two ways.

``baseline`` is the control arm convention 3 requires: same code, same batch,
same frame, no candidate columns.
"""

_cached = None
_real_load = tr.load_training_frame


def _memoised():
    global _cached
    if _cached is None:
        _cached = _real_load()
    df, tg, elo = _cached
    return df.copy(), tg.copy(), elo


def arm_features(name: str) -> list[str]:
    """The feature list this arm trains the minutes model on.

    Reads ``tr.MINUTES_FEATURES`` afresh rather than closing over it, and
    returns a new list, so calling this never mutates the shipped constant.
    """
    return list(tr.MINUTES_FEATURES) + list(ARMS[name])


def scores(payload: dict) -> dict:
    """The three numbers the gate rule reads, off a benchmark payload."""
    table = payload["stratified"]["all"]
    return {"zeros": table["zeros"]["rmse"],
            "haulers": table["haulers"]["rmse"],
            "all": table["all"]["rmse"],
            "zeros_n": table["zeros"]["n"]}


def verdict(base: dict, arm: dict) -> dict:
    """The pre-registered rule, applied to one arm against the control."""
    gain = base["zeros"] - arm["zeros"]
    haulers_cost = arm["haulers"] - base["haulers"]
    all_cost = arm["all"] - base["all"]
    keep = (gain >= ZEROS_MIN_GAIN
            and haulers_cost <= GUARD_TOLERANCE
            and all_cost <= GUARD_TOLERANCE)
    return {"zeros_gain": round(gain, 4),
            "haulers_cost": round(haulers_cost, 4),
            "all_cost": round(all_cost, 4),
            "decision": "keep" if keep else "withdraw"}


def main() -> None:
    tr.load_training_frame = _memoised
    shipped = list(tr.MINUTES_FEATURES)
    results: dict[str, dict] = {}
    try:
        for name in ARMS:
            tr.MINUTES_FEATURES = arm_features(name)
            payload = ev.evaluate_benchmark()
            results[name] = scores(payload)
            print("V8A_ARM_DONE", name, json.dumps(results[name]), flush=True)
    finally:
        tr.MINUTES_FEATURES = shipped
        tr.load_training_frame = _real_load

    base = results["baseline"]
    verdicts = {name: verdict(base, arm)
                for name, arm in results.items() if name != "baseline"}
    for name, v in verdicts.items():
        print("V8A_VERDICT", name, json.dumps(v), flush=True)
    print("V8A_KEEP", json.dumps(
        [n for n, v in verdicts.items() if v["decision"] == "keep"]),
        flush=True)

    Path("reports").mkdir(exist_ok=True)
    Path("reports/v8a_arms.json").write_text(
        json.dumps({"arms": results, "verdicts": verdicts}, indent=1))


if __name__ == "__main__":
    main()
