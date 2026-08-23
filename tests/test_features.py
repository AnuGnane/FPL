import numpy as np
import pandas as pd

from gaffer.features.engineer import add_player_rolling, build_prediction_frame


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
