"""Gate G1, D1: does switching the red-card term on cost anything?

Two arms on the fixed 2024-25 walk-forward benchmark — ``baseline`` with
``ROLL_STATS`` as it stood before v9c, ``rc`` with the entry added — and the
pre-registered rule below applied to the second against the first.

Run it, watch it, read the verdict::

    mkdir -p logs && caffeinate -i nohup .venv/bin/python scripts/v9c_rc_arm.py \\
        > logs/v9c_rc_arm.log 2>&1 &
    grep -e V9C_ARM_DONE -e V9C_VERDICT logs/v9c_rc_arm.log

**The pre-registered rule (plan A4), fixed before the first run:** this is a
*non-regression* gate, not an improvement gate. v8a's arms were candidate
signals and had to earn their place with a zeros gain; this is a term the
model has always documented and never applied, so the question is only
whether switching it on costs anything. SHIP iff no stratum's RMSE regresses
by more than :data:`GUARD_TOLERANCE`. Any breach withdraws, and the plan's
Task 2 then zeroes the term explicitly with these numbers in the comment.

Two differences from ``scripts/v8a_arms.py``, both forced (plan A2, A3):

* **The frame is not memoised.** v8a's arms differed in a feature *list* over
  one frame; this arm differs in the frame itself, so each arm pays for its
  own ``load_training_frame``. That is most of the wall clock.
* **The intervention mutates the list in place.** ``ROLL_STATS`` is a mutable
  default argument on four functions in ``engineer`` — rebinding the module
  global would leave every one of those defaults pointing at the original
  object, and both arms would silently build the same frame and report a gap
  of exactly zero. The width guard below refuses to report a verdict unless
  the two frames actually differ.
"""

from __future__ import annotations

import json
from pathlib import Path

import gaffer.evaluation as ev
from gaffer.features import engineer

GUARD_TOLERANCE = 0.005
"""v8a's own tolerance, reused so the two cycles read on one scale."""

CANDIDATE = "rc"


def scores(payload: dict) -> dict:
    """The three numbers the rule reads, off a benchmark payload.

    Identical to ``v8a_arms.scores`` so the two cycles' arm tables can be put
    beside each other without a footnote.
    """
    table = payload["stratified"]["all"]
    return {"zeros": table["zeros"]["rmse"],
            "haulers": table["haulers"]["rmse"],
            "all": table["all"]["rmse"],
            "zeros_n": table["zeros"]["n"]}


def verdict(base: dict, arm: dict) -> dict:
    """The pre-registered non-regression rule, applied once."""
    costs = {k: round(arm[k] - base[k], 4)
             for k in ("zeros", "haulers", "all")}
    ship = all(c <= GUARD_TOLERANCE for c in costs.values())
    return {**{f"{k}_cost": v for k, v in costs.items()},
            "tolerance": GUARD_TOLERANCE,
            "decision": "ship" if ship else "withdraw"}


def _column_count() -> int:
    """How many rolled columns the current ``ROLL_STATS`` produces.

    The guard against A3's trap: if the in-place mutation did not take, both
    arms build the same frame and this number does not move.
    """
    return len(engineer.feature_columns())


def main() -> None:
    assert CANDIDATE in engineer.ROLL_STATS, (
        "run this on a branch where the candidate has shipped; the baseline "
        "arm is produced by removing it, not by adding it")
    results: dict[str, dict] = {}
    widths: dict[str, int] = {}

    # Baseline first, so a crash leaves the shipped list restored.
    engineer.ROLL_STATS.remove(CANDIDATE)
    try:
        widths["baseline"] = _column_count()
        results["baseline"] = scores(ev.evaluate_benchmark())
        print("V9C_ARM_DONE baseline", json.dumps(results["baseline"]),
              flush=True)
    finally:
        engineer.ROLL_STATS.append(CANDIDATE)

    widths[CANDIDATE] = _column_count()
    results[CANDIDATE] = scores(ev.evaluate_benchmark())
    print("V9C_ARM_DONE", CANDIDATE, json.dumps(results[CANDIDATE]),
          flush=True)

    if widths[CANDIDATE] <= widths["baseline"]:
        # Refuse to report rather than report a zero gap that means nothing.
        raise SystemExit(
            f"the intervention did not take: {widths['baseline']} feature "
            f"columns baseline vs {widths[CANDIDATE]} with the candidate. "
            f"See plan A3 — ROLL_STATS is a mutable default argument.")

    v = verdict(results["baseline"], results[CANDIDATE])
    print("V9C_VERDICT", CANDIDATE, json.dumps(v), flush=True)
    print("V9C_DECISION", v["decision"], flush=True)

    Path("reports").mkdir(exist_ok=True)
    Path("reports/v9c_rc_arm.json").write_text(
        json.dumps({"arms": results, "widths": widths, "verdict": v},
                   indent=1))


if __name__ == "__main__":
    main()
