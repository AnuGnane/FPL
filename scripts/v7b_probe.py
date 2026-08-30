"""v7b Q2: the cheap non-replay diagnostic — two questions in minutes.

Budget rationale (spec §3 caps the cycle at ~20 replay runs, each multi-hour).
Four ``train_all`` fits and no MILP answer two Q2 sub-questions that would
otherwise cost four replays:

1. **Are the v5 training-frame additions inert to what the replay consumes?**
   Fit the components on the current frame, then again with ``cup_matches``
   neutralised and ``add_shrunken_modes`` an identity **and the frame reloaded
   under them**, and compare the two component frames exactly. Fact F1 expects
   ``identical: true`` — ``a0f314f`` withdrew the congestion columns from
   ``MINUTES_FEATURES`` and no other model's feature list names them. A PASS
   here **retires the ``--frame v4c`` replay arms outright**, zero runs spent.

2. **How far did the minutes-head swap move xMins?** Fact F2's named
   mechanism: the old ``p60`` was an independently-fit classifier clipped to
   ``p_play``; the new one is ``p_start * P(60+|start)``, derived and
   structurally smaller. If so ``xmins = 90·p_play·p60 + 45·p_play·(1−p60)``
   falls and the heuristic noise scale ``(92 − xmins) / 134`` **rises**, over-
   noising exactly the nailed-on starters. Measuring it here either names the
   reversal's mechanism at the component level — so the Task 8 replay arms
   exist to *price* it, not to discover it — or kills the hypothesis before two
   multi-hour runs are spent on it.

Usage (orchestrator)::

    caffeinate -i .venv/bin/python scripts/v7b_probe.py --gw 20 \\
        2>&1 | tee logs/v7b_probe.log
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

import gaffer.features.engineer as eng
import gaffer.models.train as tr
from gaffer.config import load_config
from gaffer.models.train import (load_training_frame,
                                 predict_components_simple, train_all)
from gaffer.optimize.scenarios import (NOISE_DENOM, NOISE_FLOOR_XMINS,
                                       xmins_by_player_gw)

from v7b_legacy_minutes import LegacyMinutesModel

SEASON = "2025-26"


def frames_identical(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    """Exact equality, column for column — this is an inertness claim.

    Not ``approx``: the question is whether the v5 frame additions reach the
    replay's components *at all*, and a difference in the last bit is still a
    difference that a 34-week replay can compound.
    """
    if list(a.columns) != list(b.columns) or len(a) != len(b):
        return False
    return all(a[c].reset_index(drop=True).equals(b[c].reset_index(drop=True))
               for c in a.columns)


def xmins_summary(comp: pd.DataFrame) -> dict:
    """xMins distribution and the heuristic noise scale it implies."""
    xm = pd.Series(list(xmins_by_player_gw(comp).values()), dtype="float64")
    scale = ((NOISE_FLOOR_XMINS - xm) / NOISE_DENOM).clip(lower=0.0)
    return {
        "n": int(len(xm)),
        "mean_xmins": float(xm.mean()),
        "median_xmins": float(xm.median()),
        "p90_xmins": float(xm.quantile(0.9)),
        "mean_noise_scale": float(scale.mean()),
    }


def _fit_and_predict(season_idx: int, gw: int) -> pd.DataFrame:
    """One decision gameweek's component frame, exactly as the replay makes it."""
    df, tg, _ = load_training_frame(max_season_idx=season_idx, max_gw=gw)
    full, _, _ = load_training_frame()
    season_rows = full[full["season_idx"] == season_idx]
    rows = season_rows[season_rows["gw"] == gw]
    models = train_all(df, tg, save=False)
    return predict_components_simple(models, rows)


def main(argv: list[str] | None = None) -> dict:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--gw", type=int, default=20)
    a = p.parse_args(argv)
    gw = a.gw
    season_idx = load_config().train_seasons.index(SEASON)

    # (1) frame arm — current, then with the v5 additions neutralised and the
    # frame *reloaded* under them, so the columns are genuinely absent.
    current = _fit_and_predict(season_idx, gw)

    real_cup, real_eng, real_tr = (tr.cup_matches, eng.add_shrunken_modes,
                                   tr.add_shrunken_modes)
    tr.cup_matches = lambda: None
    eng.add_shrunken_modes = lambda df, *args, **kw: df
    tr.add_shrunken_modes = lambda df, *args, **kw: df
    try:
        v4c_frame = _fit_and_predict(season_idx, gw)
    finally:
        tr.cup_matches, eng.add_shrunken_modes, tr.add_shrunken_modes = (
            real_cup, real_eng, real_tr)

    frame_result = {
        "gw": gw,
        "identical": frames_identical(current, v4c_frame),
        "moved_columns": [c for c in current.columns
                          if c in v4c_frame.columns and not
                          current[c].reset_index(drop=True).equals(
                              v4c_frame[c].reset_index(drop=True))],
        "rows_current": int(len(current)),
        "rows_v4c": int(len(v4c_frame)),
    }
    print("V7B_PROBE_FRAME", json.dumps(frame_result), flush=True)

    # (2) minutes arm — the current frame, shipped head against the vendored one.
    real_head = tr.ThreeModeModel
    tr.ThreeModeModel = LegacyMinutesModel
    try:
        legacy = _fit_and_predict(season_idx, gw)
    finally:
        tr.ThreeModeModel = real_head

    xmins_result = {"gw": gw, "current": xmins_summary(current),
                    "legacy": xmins_summary(legacy)}
    print("V7B_PROBE_XMINS", json.dumps(xmins_result), flush=True)

    out = {"frame": frame_result, "xmins": xmins_result}
    dest = Path("reports/v7b_probe.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    main(sys.argv[1:])
