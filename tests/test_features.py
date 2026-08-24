import numpy as np
import pandas as pd

from gaffer.features.engineer import (ROTATION_FEATURES, add_player_rolling,
                                      add_rotation, add_setpiece,
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
    # Both rows are predictions made today, so both see the same as-of-today
    # form: the last three played matches.
    assert pred.loc[pred.gw == 5, "total_points_r3"].iloc[0] == (4 + 100 + 6) / 3
    assert pred.loc[pred.gw == 6, "total_points_r3"].iloc[0] == (4 + 100 + 6) / 3


def _history(code=1, n=8):
    return pd.DataFrame({
        "code": [code] * n,
        "season_idx": [0] * n,
        "gw": list(range(1, n + 1)),
        "kickoff_time": [d.strftime("%Y-%m-%dT14:00:00Z") for d in
                         pd.date_range("2025-08-09", periods=n, freq="7D")],
        "team_code": [3] * n,
        "opp_code": list(range(20, 20 + n)),
        "was_home": [i % 2 == 0 for i in range(n)],
        "total_points": [2.0, 4.0, 1.0, 9.0, 6.0, 3.0, 12.0, 5.0][:n],
        "minutes": [90, 45, 90, 90, 12, 90, 90, 78][:n],
        "starts": [1, 0, 1, 1, 0, 1, 1, 1][:n],
    })


def _three_future(code=1):
    return pd.DataFrame({
        "code": [code] * 3,
        "season_idx": [0] * 3,
        "gw": [9, 10, 11],
        "kickoff_time": ["2025-10-04T14:00:00Z", "2025-10-08T19:45:00Z",
                         "2025-10-18T14:00:00Z"],
        "team_code": [3] * 3,
        "opp_code": [40, 41, 42],
        "was_home": [True, False, True],
    })


ROLL_SPOTS = ["total_points_r1", "minutes_r1", "minutes_r3", "starts_r5",
              *ROTATION_FEATURES]


def test_future_rows_share_one_as_of_today_form_vector():
    """A prediction made today for GW+2 knows exactly what a prediction for
    GW+1 knows: the same played matches. Only fixture context may differ."""
    hist = _history()
    pred = build_prediction_frame(hist, _three_future(),
                                  stats=["total_points", "minutes", "starts"],
                                  windows=[1, 3, 5])
    assert len(pred) == 3
    for col in ROLL_SPOTS:
        vals = pred[col].tolist()
        assert not np.isnan(vals[0]), col
        assert vals[0] == vals[1] == vals[2], (col, vals)
    # and that shared vector is the one the GW+1 row already got: the window
    # ending at the last played match.
    assert pred["total_points_r1"].iloc[0] == 5.0
    assert pred["minutes_r1"].iloc[0] == 78
    assert pred["minutes_r3"].iloc[0] == (90 + 90 + 78) / 3
    assert pred["starts_r5"].iloc[0] == (1 + 0 + 1 + 1 + 1) / 5


def test_future_rows_still_vary_by_fixture_context():
    pred = build_prediction_frame(_history(), _three_future(),
                                  stats=["total_points"], windows=[1])
    assert pred["opp_code"].tolist() == [40, 41, 42]
    assert pred["home"].tolist() == [1.0, 0.0, 1.0]
    # days_rest comes from the schedule's kickoff gaps, which are real
    # knowledge and must keep varying per row.
    assert pred["days_rest"].tolist() == [7.0, 4.0, 9.0]


def test_future_rows_for_a_player_with_no_history_stay_nan():
    hist = _history(code=1)
    future = pd.concat([_three_future(code=1), _three_future(code=2)],
                       ignore_index=True)
    pred = build_prediction_frame(hist, future,
                                  stats=["total_points", "minutes", "starts"],
                                  windows=[1, 3, 5])
    rookie = pred[pred["code"] == 2]
    assert len(rookie) == 3
    for col in ROLL_SPOTS:
        assert rookie[col].isna().all(), col
    assert not pred.loc[pred["code"] == 1, "minutes_r1"].isna().any()


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


def _rot(starts, minutes=None, seasons=None, gws=None, kickoffs=None, code=1):
    """One player's match history, one row per match, weekly kickoffs."""
    n = len(starts)
    if kickoffs is None:
        kickoffs = [d.strftime("%Y-%m-%dT14:00:00Z") for d in
                    pd.date_range("2025-08-09", periods=n, freq="7D")]
    if minutes is None:
        minutes = [90 if s else 20 for s in starts]
    return pd.DataFrame({
        "code": [code] * n,
        "season_idx": [0] * n if seasons is None else seasons,
        "gw": list(range(1, n + 1)) if gws is None else gws,
        "kickoff_time": kickoffs,
        "starts": starts,
        "minutes": minutes,
    })


def test_season_start_share_sees_only_the_current_season():
    """Where ``starts_r5`` blends August into last May, this feature resets.

    A nailed-on starter benched in the opener under a new manager reads 0.0
    here and still ~0.8 on the rolling window — that gap is the point.
    """
    df = _rot([1, 1, 1, 0, 0, 1], seasons=[0, 0, 0, 1, 1, 1],
              gws=[36, 37, 38, 1, 2, 3])
    out = add_rotation(add_player_rolling(df, stats=["starts"], windows=[5]))
    share = out.set_index(["season_idx", "gw"])["season_start_share"]
    assert np.isnan(share[(0, 36)])            # first match of the frame
    assert share[(0, 37)] == 1.0
    assert share[(0, 38)] == 1.0
    assert np.isnan(share[(1, 1)])             # first match of a new season
    assert share[(1, 2)] == 0.0                # one benching, nothing else
    assert share[(1, 3)] == 0.0                # two benchings
    # the rolling window is still dragging last season's starts along
    assert out.set_index(["season_idx", "gw"])["starts_r5"][(1, 2)] == 0.75


def test_season_start_share_excludes_the_current_row():
    df = _rot([0, 1, 1])
    share = add_rotation(df)["season_start_share"].tolist()
    assert np.isnan(share[0])
    assert share[1] == 0.0    # gw1 only; gw2's own start must not leak in
    assert share[2] == 0.5


def test_days_since_last_start_measures_the_gap_to_the_last_start():
    df = _rot([1, 0, 0, 1, 0])
    days = add_rotation(df)["days_since_last_start"].tolist()
    assert np.isnan(days[0])   # no earlier start
    assert days[1] == 7.0      # gw1's start, a week ago
    assert days[2] == 14.0
    assert days[3] == 21.0     # still gw1's start: gw2 and gw3 were benchings
    assert days[4] == 7.0      # gw4 reset it


def test_days_since_last_start_is_clipped_at_sixty_days():
    kick = ["2025-08-09T14:00:00Z", "2025-08-16T14:00:00Z",
            "2026-01-10T14:00:00Z"]
    df = _rot([1, 0, 0], kickoffs=kick)
    assert add_rotation(df)["days_since_last_start"].iloc[2] == 60.0


def test_days_since_last_start_is_nan_for_a_player_who_never_started():
    df = _rot([0, 0, 0])
    assert add_rotation(df)["days_since_last_start"].isna().all()


def test_sub_streak_counts_appearances_since_the_last_start():
    df = _rot([1, 0, 0, 1, 0], minutes=[90, 20, 15, 80, 10])
    streak = add_rotation(df)["sub_streak"].tolist()
    assert np.isnan(streak[0])   # no earlier appearance
    assert streak[1] == 0.0      # last appearance was a start
    assert streak[2] == 1.0
    assert streak[3] == 2.0
    assert streak[4] == 0.0      # gw4's start reset it


def test_sub_streak_ignores_matches_the_player_did_not_appear_in():
    """An unused substitute is not a benching signal on its own: the streak
    counts appearances, so a 0-minute row neither extends nor resets it."""
    df = _rot([1, 0, 0, 0], minutes=[90, 20, 0, 25])
    streak = add_rotation(df)["sub_streak"].tolist()
    assert streak[1] == 0.0
    assert streak[2] == 1.0      # carried across the unused-sub row
    assert streak[3] == 1.0


def test_sub_streak_counts_every_appearance_before_a_first_start():
    df = _rot([0, 0, 0], minutes=[20, 20, 20])
    streak = add_rotation(df)["sub_streak"].tolist()
    assert np.isnan(streak[0])
    assert streak[1] == 1.0
    assert streak[2] == 2.0


def test_rotation_features_never_cross_players():
    df = pd.concat([_rot([1, 1, 1], code=1), _rot([0, 0, 0], code=2)],
                   ignore_index=True)
    out = add_rotation(df).set_index(["code", "gw"])
    assert out["season_start_share"][(1, 3)] == 1.0
    assert out["season_start_share"][(2, 3)] == 0.0
    assert out["days_since_last_start"][(1, 3)] == 7.0
    assert np.isnan(out["days_since_last_start"][(2, 3)])
    assert out["sub_streak"][(1, 3)] == 0.0
    assert out["sub_streak"][(2, 3)] == 2.0


def test_add_rotation_tolerates_missing_source_columns():
    out = add_rotation(_frame().drop(columns=["minutes"]))
    for col in ROTATION_FEATURES:
        assert col in out.columns


def test_feature_columns_include_rotation_features():
    cols = feature_columns()
    for col in ROTATION_FEATURES:
        assert col in cols


def _benched_history(code=1):
    """Five starts, then dropped to the bench for three."""
    return _rot([1, 1, 1, 1, 1, 0, 0, 0], minutes=[90] * 5 + [20, 15, 10],
                code=code)


def test_prediction_frame_broadcasts_the_as_of_today_rotation_state():
    """Same as-of-today discipline as the rolling form vector: every future
    row of a player carries the state at the last played match."""
    pred = build_prediction_frame(_benched_history(), _three_future(),
                                  stats=["starts"], windows=[5])
    for col in ROTATION_FEATURES:
        vals = pred[col].tolist()
        assert not np.isnan(vals[0]), col
        assert vals[0] == vals[1] == vals[2], (col, vals)
    assert pred["season_start_share"].iloc[0] == 5 / 8
    # last start was gw5 (2025-09-06); the last match played was gw8
    # (2025-09-27), which is where an as-of-today feature is evaluated.
    assert pred["days_since_last_start"].iloc[0] == 21.0
    assert pred["sub_streak"].iloc[0] == 3.0


def test_prediction_frame_rotation_is_nan_for_a_player_with_no_history():
    future = pd.concat([_three_future(code=1), _three_future(code=2)],
                       ignore_index=True)
    pred = build_prediction_frame(_benched_history(), future,
                                  stats=["starts"], windows=[5])
    rookie = pred[pred["code"] == 2]
    for col in ROTATION_FEATURES:
        assert rookie[col].isna().all(), col


def test_prediction_frame_season_start_share_resets_in_a_new_season():
    """The opening gameweek of a new season: the player has no matches in it
    yet, so the share is undefined rather than last season's."""
    hist = _benched_history()
    future = _three_future()
    future["season_idx"] = 1
    pred = build_prediction_frame(hist, future, stats=["starts"], windows=[5])
    assert pred["season_start_share"].isna().all()
    # the other two are genuine cross-season knowledge and survive
    assert pred["sub_streak"].tolist() == [3.0, 3.0, 3.0]
    assert pred["days_since_last_start"].tolist() == [21.0] * 3


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


def test_pen_taker_is_nan_on_history_rows_even_after_a_missed_penalty():
    """No back-fill from ``pens_missed``.

    The proxy looked reasonable but measured out as noise: across the real
    113k-row history it left 1770 non-null values, every one of them
    identical, so it carried no signal and only gave the attacking model a
    near-constant column to split on. History rows stay NaN and LightGBM
    ignores them; the feature comes alive as live snapshots accumulate.
    """
    df = pd.DataFrame({
        "code": [1, 1, 1, 1, 2, 2, 2, 2],
        "season_idx": [0] * 8,
        "gw": [1, 2, 3, 4, 1, 2, 3, 4],
        "pens_missed": [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "penalties_order": [np.nan] * 8,
    })
    assert add_setpiece(df)["pen_taker"].isna().all()


def test_pen_taker_still_reads_a_live_order_alongside_pens_missed():
    """Dropping the proxy must not disturb the real source: where the
    bootstrap order is present it still wins, miss history or not."""
    df = _setpiece_frame(pens_missed=[1.0, 0.0, 0.0],
                         penalties_order=[np.nan, 1.0, 3.0])
    out = add_setpiece(df)["pen_taker"]
    assert np.isnan(out.iloc[0])
    assert out.iloc[1] == 1.0
    assert out.iloc[2] == 0.0


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
