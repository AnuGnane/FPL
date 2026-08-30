"""Gate Z1: the zeros stratum with and without the DNP recalibration.

Two runs of ``evaluate_current`` over one training frame. Arm ``off`` is the
shipped model; arm ``on`` flips ``minutes.DNP_CALIBRATION_DEFAULT``, which is
the only difference between them — same slots, same components, same scoring
table, same assemble/calibrate seam.

``load_training_frame`` is memoised across the arms because it is the
expensive half of the run and it cannot differ between them by construction.
It hands back copies, so an arm that mutates its frame cannot poison the next.

Run it, watch it, read the verdict::

    caffeinate -i nohup .venv/bin/python scripts/z1_arms.py \\
        > logs/z1_arms.log 2>&1 &
    grep -e Z1_ARM_DONE -e Z1_VERDICT logs/z1_arms.log

The pre-registered rule (v7-model spec §2.3) against the 2026-08-29 baseline
(zeros 1.063, haulers 5.145, all 1.986): PASS needs zeros <= 1.042 AND
haulers <= 5.171 AND all <= 1.996. This script prints the comparison; the
shipping decision is the orchestrator's.
"""

import json
from pathlib import Path

import gaffer.evaluation as ev
import gaffer.models.minutes as mn
from gaffer.models import train as tr

ZEROS_TARGET = 1.042
HAULERS_CEILING = 5.171
ALL_CEILING = 1.996

_cached = None
_real_load = tr.load_training_frame


def _memoised():
    global _cached
    if _cached is None:
        _cached = _real_load()
    df, tg, elo = _cached
    return df.copy(), tg.copy(), elo


tr.load_training_frame = _memoised

arms = {}
for name, flag in (("off", False), ("on", True)):
    mn.DNP_CALIBRATION_DEFAULT = flag
    payload = ev.evaluate_current()
    arms[name] = payload
    table = payload["stratified"]["all"]
    print("Z1_ARM_DONE", name, json.dumps({
        "zeros": table["zeros"]["rmse"],
        "haulers": table["haulers"]["rmse"],
        "all": table["all"]["rmse"],
        "zeros_n": table["zeros"]["n"],
        "last5_zeros": payload["baselines"]["last5"]["zeros"]["rmse"],
    }), flush=True)

on = arms["on"]["stratified"]["all"]
verdict = {
    "zeros": on["zeros"]["rmse"],
    "zeros_pass": on["zeros"]["rmse"] <= ZEROS_TARGET,
    "haulers": on["haulers"]["rmse"],
    "haulers_pass": on["haulers"]["rmse"] <= HAULERS_CEILING,
    "all": on["all"]["rmse"],
    "all_pass": on["all"]["rmse"] <= ALL_CEILING,
}
verdict["gate"] = ("PASS" if all(verdict[k] for k in
                                 ("zeros_pass", "haulers_pass", "all_pass"))
                   else "FAIL")
print("Z1_VERDICT", json.dumps(verdict), flush=True)

Path("reports").mkdir(exist_ok=True)
Path("reports/z1_arms.json").write_text(
    json.dumps({"arms": arms, "verdict": verdict}, indent=1))
