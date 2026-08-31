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

**The lever moved after the review, and the reason is worth reading.** The
first version of this script produced its baseline by removing ``"rc"`` from
``ROLL_STATS``, on the theory that the five ``rc_r*`` columns were what fed
the red term. That was true when it was written. The review's I3 then made
``card_penalty`` read ``shrunk_rc_rate`` instead — built by
``add_shrunken_cards`` from the **raw** ``rc`` column, which lives in
``CANONICAL_COLS`` and is present whatever ``ROLL_STATS`` says. So the old
lever stopped switching the term off, and the re-run duly reported costs of
exactly ``0.000`` on all three strata with a frame that genuinely differed by
five columns (149 vs 154). A gate measuring nothing, reporting ship.

That is the same shape of defect as the one D1 exists to close — a term that
looks live and is not — so the lever now sits on the term itself:
``models.components.CARD_RATES`` with the red row removed is the baseline, and
as it ships is the arm. The frame is identical between the two, which means it
can be memoised the way ``scripts/v8a_arms.py`` memoises its own, and the run
is roughly half what it was.

The ``ROLL_STATS`` width check survives as an assertion rather than an arm:
the five rolled columns still have to exist, because they are
``card_penalty``'s documented fallback for a frame built before v9c.
"""

from __future__ import annotations

import json
from pathlib import Path

import gaffer.evaluation as ev
from gaffer.features import engineer
from gaffer.models import components as comp
from gaffer.models import train as tr

GUARD_TOLERANCE = 0.005
"""v8a's own tolerance, reused so the two cycles read on one scale."""

CANDIDATE = "rc"

_cached = None
_real_load = tr.load_training_frame


def _memoised():
    """One frame for both arms — legal now that the arms differ in a formula
    and not in the frame. Hands back copies, so an arm that mutates its frame
    cannot poison the next (``v8a_arms`` does the same, for the same reason).
    """
    global _cached
    if _cached is None:
        _cached = _real_load()
    df, tg, elo = _cached
    return df.copy(), tg.copy(), elo


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


def main() -> None:
    assert CANDIDATE in engineer.ROLL_STATS, (
        "the rolled rc_r* columns are card_penalty's documented fallback for "
        "frames built before v9c; they must still exist even though the live "
        "path now reads the shrunk rate")
    assert len(comp.CARD_RATES) == 2, comp.CARD_RATES

    # The width check the old arm used as its lever, kept as an assertion.
    with_rc = len(engineer.feature_columns())
    engineer.ROLL_STATS.remove(CANDIDATE)
    try:
        without_rc = len(engineer.feature_columns())
    finally:
        engineer.ROLL_STATS.append(CANDIDATE)
    if with_rc <= without_rc:
        raise SystemExit(
            f"ROLL_STATS is not producing the rc_r* block: {without_rc} "
            f"feature columns without the entry vs {with_rc} with it. See "
            f"plan A3 — ROLL_STATS is a mutable default argument.")
    print("V9C_ARM_WIDTHS", json.dumps(
        {"without_rc": without_rc, "with_rc": with_rc}), flush=True)

    tr.load_training_frame = _memoised
    results: dict[str, dict] = {}
    try:
        # Baseline: the red term ablated where it is actually read.
        red_row = [r for r in comp.CARD_RATES if r[0] == "shrunk_rc_rate"]
        comp.CARD_RATES = tuple(r for r in comp.CARD_RATES
                                if r[0] != "shrunk_rc_rate")
        try:
            results["baseline"] = scores(ev.evaluate_benchmark())
            print("V9C_ARM_DONE baseline", json.dumps(results["baseline"]),
                  flush=True)
        finally:
            comp.CARD_RATES = tuple(list(comp.CARD_RATES) + red_row)

        results[CANDIDATE] = scores(ev.evaluate_benchmark())
        print("V9C_ARM_DONE", CANDIDATE, json.dumps(results[CANDIDATE]),
              flush=True)
    finally:
        tr.load_training_frame = _real_load

    if results["baseline"] == results[CANDIDATE]:
        # The trap that caught the first re-run: an arm reporting a clean
        # zero because the lever was not connected to the term.
        raise SystemExit(
            "both arms scored identically, so the red term was not actually "
            "ablated. Check that card_penalty reads CARD_RATES rather than "
            "closing over its own list.")

    v = verdict(results["baseline"], results[CANDIDATE])
    print("V9C_VERDICT", CANDIDATE, json.dumps(v), flush=True)
    print("V9C_DECISION", v["decision"], flush=True)

    Path("reports").mkdir(exist_ok=True)
    Path("reports/v9c_rc_arm.json").write_text(
        json.dumps({"arms": results,
                    "widths": {"without_rc": without_rc, "with_rc": with_rc},
                    "verdict": v}, indent=1))


if __name__ == "__main__":
    main()
