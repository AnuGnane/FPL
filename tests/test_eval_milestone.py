"""The milestone evaluation's two helpers, on a six-row frame (holiday F-175).

``scripts/eval_milestone.py`` ran at module level until F-175, so its
``baseline`` and ``bias_60`` read the globals ``holdout`` and ``truth`` and
importing it trained every head. They now take those frames as parameters and
the run sits under ``main()``, so this imports the script without a fit.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import eval_milestone

# Player 1 has a double gameweek in GW30 (two matches, one rolling value
# each); player 3's GW31 rolling value is missing.
HOLDOUT = pd.DataFrame({
    "code": [1, 1, 1, 2, 2, 3],
    "gw": [30, 30, 31, 30, 31, 31],
    "total_points_r5": [4.0, 4.1, 5.0, 2.0, 3.0, float("nan")],
})


def test_baseline_keeps_one_row_per_player_gameweek_and_drops_a_missing_value():
    b = eval_milestone.baseline(HOLDOUT, "total_points_r5")
    assert list(b.columns) == ["code", "gw", "ep"]
    assert b.values.tolist() == [[1, 30, 4.0], [1, 31, 5.0], [2, 30, 2.0], [2, 31, 3.0]]


def test_bias_60_is_the_signed_mean_error_over_starters_only():
    pred = pd.DataFrame({"code": [1, 1, 2, 2], "gw": [30, 31, 30, 31],
                         "ep": [6.0, 5.0, 2.0, 9.0]})
    truth = pd.DataFrame({"code": [1, 1, 2, 2], "gw": [30, 31, 30, 31],
                          "total_points": [10, 2, 1, 2], "minutes": [180, 90, 59, 0]})
    # Starters: (1, 30) at -4 and (1, 31) at +3; player 2 never reached 60.
    assert eval_milestone.bias_60(pred, truth) == -0.5


def test_importing_the_script_runs_nothing():
    assert callable(eval_milestone.main)
    assert not hasattr(eval_milestone, "holdout")
