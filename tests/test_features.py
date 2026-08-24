import numpy as np
import pandas as pd

from gaffer.features.engineer import (add_player_rolling, add_setpiece,
                                      build_prediction_frame, feature_columns)


def _frame():
    return pd.DataFrame({
        "code": [1, 1, 1, 1],
        "season_idx": [0, 0, 0, 0],
        "gw": [1, 2, 3, 4],
        "total_points": [2.0, 4.0, 100.0, 6.0],
        "minutes": [90, 90, 90, 90],
    })


def test_rolling_excludes_current_row_no_leakage():
    out = add_player_rolling(_frame(), stats=["total_points"], windows=[3])
    # feature at gw3 must NOT include gw3's 100 points
    assert out.loc[out.gw == 3, "total_points_r3"].iloc[0] == (2 + 4) / 2
    # gw4 sees gw1-3
    assert out.loc[out.gw == 4, "total_points_r3"].iloc[0] == (2 + 4 + 100) / 3
    # gw1 has no history -> NaN
    assert np.isnan(out.loc[out.gw == 1, "total_points_r3"].iloc[0])


def test_prediction_frame_future_rows_get_history_features():
    hist = _frame()
    future = pd.DataFrame({"code": [1, 1], "season_idx": [0, 0], "gw": [5, 6],
                           "opp_code": [10, 11], "was_home": [True, False]})
    pred = build_prediction_frame(hist, future, stats=["total_points"],
                                  windows=[3])
    assert len(pred) == 2
    # gw5 window = gw2-4 actuals; gw6 window skips gw5's NaN
    assert pred.loc[pred.gw == 5, "total_points_r3"].iloc[0] == (4 + 100 + 6) / 3
    assert pred.loc[pred.gw == 6, "total_points_r3"].iloc[0] == (100 + 6) / 2


def test_rolling_never_crosses_players():
    df = pd.DataFrame({
        "code": [1, 2, 1, 2, 1, 2],
        "season_idx": [0, 0, 0, 0, 0, 0],
        "gw": [1, 1, 2, 2, 3, 3],
        "total_points": [2.0, 50.0, 4.0, 50.0, 6.0, 50.0],
    })
    out = add_player_rolling(df, stats=["total_points"], windows=[3])
    a3 = out.loc[(out.code == 1) & (out.gw == 3), "total_points_r3"].iloc[0]
    assert a3 == (2 + 4) / 2          # player 2's 50s must not appear
    b3 = out.loc[(out.code == 2) & (out.gw == 3), "total_points_r3"].iloc[0]
    assert b3 == 50.0
    assert np.isnan(
        out.loc[(out.code == 2) & (out.gw == 1), "total_points_r3"].iloc[0])


def test_rolling_spans_season_boundary():
    df = pd.DataFrame({
        "code": [1, 1, 1],
        "season_idx": [0, 0, 1],
        "gw": [37, 38, 1],
        "total_points": [3.0, 9.0, 100.0],
    })
    out = add_player_rolling(df, stats=["total_points"], windows=[3])
    new_season = out.loc[
        (out.season_idx == 1) & (out.gw == 1), "total_points_r3"].iloc[0]
    assert new_season == (3 + 9) / 2  # last season's form carries over


def test_double_gameweek_fixtures_order_by_kickoff():
    """Both of a DGW's fixtures share (code, season_idx, gw); without
    kickoff_time in the sort the r1 window can see the later match."""
    df = pd.DataFrame({
        "code": [1, 1, 1],
        "season_idx": [0, 0, 0],
        "gw": [5, 6, 6],
        "kickoff_time": ["2025-09-20T14:00:00Z", "2025-09-27T19:00:00Z",
                         "2025-09-24T14:00:00Z"],
        "total_points": [2.0, 9.0, 5.0],
    })
    out = add_player_rolling(df, stats=["total_points"], windows=[1])
    by_kick = out.set_index("kickoff_time")["total_points_r1"]
    # Earlier DGW match sees GW5; the later one sees the earlier DGW match.
    assert by_kick["2025-09-24T14:00:00Z"] == 2.0
    assert by_kick["2025-09-27T19:00:00Z"] == 5.0


def _setpiece_frame(**cols):
    n = len(next(iter(cols.values())))
    base = {"code": [1] * n, "season_idx": [0] * n, "gw": list(range(1, n + 1))}
    return pd.DataFrame({**base, **cols})


def test_pen_taker_from_live_penalties_order():
    """Live rows carry the bootstrap order directly: 1 -> 1.0, 2 -> 0.5,
    anything from 3 down the queue -> 0.0."""
    df = _setpiece_frame(penalties_order=[1.0, 2.0, 5.0])
    out = add_setpiece(df)
    assert list(out["pen_taker"]) == [1.0, 0.5, 0.0]


def test_pen_taker_history_proxy_from_pens_missed():
    """History rows have no order column, so a missed penalty is the only
    evidence the player takes them — and only from the *next* match on."""
    df = pd.DataFrame({
        "code": [1, 1, 1, 1, 2, 2, 2, 2],
        "season_idx": [0] * 8,
        "gw": [1, 2, 3, 4, 1, 2, 3, 4],
        "pens_missed": [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "penalties_order": [np.nan] * 8,
    })
    out = add_setpiece(df).set_index(["code", "gw"])["pen_taker"]
    assert np.isnan(out[(1, 1)]) and np.isnan(out[(1, 2)])
    assert np.isnan(out[(1, 3)])            # the miss must not see itself
    assert out[(1, 4)] == 1.0
    assert out.loc[2].isna().all()          # never missed -> unknown, not 0


def test_pen_taker_proxy_expires_after_38_matches():
    n = 45
    df = _setpiece_frame(pens_missed=[1.0] + [0.0] * (n - 1),
                         penalties_order=[np.nan] * n)
    out = add_setpiece(df)
    assert out.loc[out.gw == 2, "pen_taker"].iloc[0] == 1.0
    assert out.loc[out.gw == 39, "pen_taker"].iloc[0] == 1.0
    assert np.isnan(out.loc[out.gw == 40, "pen_taker"].iloc[0])


def test_setpiece_taker_takes_nan_safe_best_of_both_orders():
    df = _setpiece_frame(
        direct_freekicks_order=[np.nan, 3.0, np.nan, 2.0],
        corners_and_indirect_freekicks_order=[1.0, np.nan, np.nan, 4.0])
    out = add_setpiece(df)
    assert out["setpiece_taker"].iloc[0] == 1.0     # corners #1
    assert out["setpiece_taker"].iloc[1] == 0.0     # direct #3
    assert np.isnan(out["setpiece_taker"].iloc[2])  # no history proxy
    assert out["setpiece_taker"].iloc[3] == 0.5     # min(2, 4) = 2


def test_add_setpiece_tolerates_missing_source_columns():
    out = add_setpiece(_frame())
    assert out["pen_taker"].isna().all()
    assert out["setpiece_taker"].isna().all()


def test_feature_columns_include_setpiece_features():
    cols = feature_columns()
    assert "pen_taker" in cols and "setpiece_taker" in cols


def test_prediction_frame_carries_setpiece_features():
    hist = _frame()
    hist["penalties_order"] = np.nan
    future = pd.DataFrame({"code": [1], "season_idx": [0], "gw": [5],
                           "opp_code": [10], "was_home": [True],
                           "penalties_order": [2.0],
                           "direct_freekicks_order": [np.nan],
                           "corners_and_indirect_freekicks_order": [1.0]})
    pred = build_prediction_frame(hist, future, stats=["total_points"],
                                  windows=[3])
    assert pred["pen_taker"].iloc[0] == 0.5
    assert pred["setpiece_taker"].iloc[0] == 1.0
