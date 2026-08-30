import numpy as np
import pandas as pd

from gaffer.zeros_diagnostic import (ZERO_STRATA, dnp_reliability, stratify,
                                     zeros_report)


def _scored() -> pd.DataFrame:
    """One row per (code, gw): what the harness has after its merge."""
    return pd.DataFrame([
        # fringe, cold start, absent for five, actually a zero
        {"code": 1, "gw": 1, "ep": 1.4, "total_points": 0, "minutes": 0,
         "season_start_share": 0.0, "minutes_r5": 0.0, "p_dnp": 0.55},
        # regular, mid-season, absent recently, a zero
        {"code": 2, "gw": 20, "ep": 3.1, "total_points": 0, "minutes": 0,
         "season_start_share": 0.9, "minutes_r5": 0.0, "p_dnp": 0.20},
        # regular, mid-season, playing, a hauler
        {"code": 3, "gw": 20, "ep": 5.0, "total_points": 9, "minutes": 90,
         "season_start_share": 0.95, "minutes_r5": 88.0, "p_dnp": 0.05},
        # fringe, mid-season, playing, a blank
        {"code": 4, "gw": 20, "ep": 2.0, "total_points": 2, "minutes": 30,
         "season_start_share": 0.1, "minutes_r5": 12.0, "p_dnp": 0.45},
    ])


def test_every_documented_stratum_is_produced():
    out = stratify(_scored())
    assert set(out) == set(ZERO_STRATA)


def test_the_fringe_cut_is_the_season_start_share_threshold():
    out = stratify(_scored())
    assert sorted(out["fringe"]["code"]) == [1, 4]
    assert sorted(out["regular"]["code"]) == [2, 3]


def test_the_cold_start_cut_is_the_first_four_gameweeks():
    out = stratify(_scored())
    assert sorted(out["cold_start"]["code"]) == [1]
    assert sorted(out["settled"]["code"]) == [2, 3, 4]


def test_recent_absence_stands_in_for_the_official_flag():
    out = stratify(_scored())
    assert sorted(out["recent_absence"]["code"]) == [1, 2]
    assert sorted(out["recent_presence"]["code"]) == [3, 4]


def test_a_missing_feature_column_leaves_its_strata_empty_not_crashed():
    frame = _scored().drop(columns=["season_start_share"])
    out = stratify(frame)
    assert out["fringe"].empty and out["regular"].empty
    assert not out["settled"].empty


def test_dnp_reliability_bins_predicted_against_observed():
    frame = pd.DataFrame({
        "p_dnp": np.concatenate([np.full(50, 0.05), np.full(50, 0.95)]),
        "minutes": np.concatenate([np.zeros(5), np.full(45, 90.0),
                                   np.zeros(45), np.full(5, 90.0)]),
    })
    curve = dnp_reliability(frame, bins=10)
    assert [row["decile"] for row in curve] == [0, 9]
    assert curve[0]["pred"] == 0.05 and curve[0]["obs"] == 0.1
    assert curve[1]["pred"] == 0.95 and curve[1]["obs"] == 0.9
    assert curve[0]["n"] == 50


def test_zeros_report_scores_each_stratum_on_the_zeros_rows_only():
    payload = zeros_report(_scored())
    zeros = payload["strata"]["fringe"]
    assert zeros["n"] == 1                       # only code 1 is a zero
    assert zeros["rmse"] == 1.4
    assert payload["strata"]["flagged"]["n"] == 0
    assert "no availability snapshot" in payload["strata"]["flagged"]["note"]
    assert payload["overall"]["n"] == 2          # codes 1 and 2
