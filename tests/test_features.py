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


# --- Understat rolling features -------------------------------------------

from gaffer.features.engineer import (TEAM_US_FEATURES, US_WINDOWS,
                                      add_understat_rolling,
                                      add_understat_team_rolling,
                                      merge_understat_team,
                                      understat_feature_columns)


def _us_rows(spec, code=1):
    """spec: list of (gw, us_minutes, us_shots)."""
    return pd.DataFrame([
        {"code": code, "season_idx": 0, "gw": gw,
         "kickoff_time": f"2024-08-{10 + gw:02d}T14:00:00Z",
         "us_minutes": m, "us_shots": s, "us_key_passes": 1.0,
         "us_npxg": 0.1, "us_xgchain": 0.2, "us_xgbuildup": 0.1}
        for gw, m, s in spec])


def test_add_understat_rolling_is_leakage_safe():
    """A match's own shots must never reach its own features."""
    out = add_understat_rolling(_us_rows([(1, 90, 4), (2, 90, 2)])
                                ).set_index("gw")
    assert pd.isna(out.loc[1, "us_shots90_r3"])
    assert out.loc[2, "us_shots90_r3"] == 4.0


def test_add_understat_rolling_is_a_per_ninety_not_a_per_match_mean():
    """Two matches, 90 and 45 minutes, five shots between them: the rate is
    5 / 135 * 90, not the mean of 4 and 1."""
    out = add_understat_rolling(_us_rows([(1, 90, 4), (2, 45, 1), (3, 90, 0)])
                                ).set_index("gw")
    assert abs(out.loc[3, "us_shots90_r3"] - 5.0 / 135.0 * 90.0) < 1e-9


def test_add_understat_rolling_window_only_reaches_back_w_matches():
    out = add_understat_rolling(
        _us_rows([(1, 90, 9), (2, 90, 0), (3, 90, 0), (4, 90, 0),
                  (5, 90, 0)])).set_index("gw")
    assert out.loc[5, "us_shots90_r3"] == 0.0
    assert abs(out.loc[5, "us_shots90_r38"] - 9.0 / 360.0 * 90.0) < 1e-9


def test_add_understat_rolling_zero_minutes_window_is_nan_not_inf():
    """An unused substitute run of matches would divide by zero, and an
    infinity in a feature column is a crash downstream, not a signal."""
    out = add_understat_rolling(_us_rows([(1, 0, 0), (2, 90, 1)])
                                ).set_index("gw")
    assert pd.isna(out.loc[2, "us_shots90_r3"])


def test_add_understat_rolling_keeps_players_separate():
    frame = pd.concat([_us_rows([(1, 90, 6), (2, 90, 0)], code=1),
                       _us_rows([(1, 90, 0), (2, 90, 0)], code=2)],
                      ignore_index=True)
    out = add_understat_rolling(frame).set_index(["code", "gw"])
    assert out.loc[(1, 2), "us_shots90_r3"] == 6.0
    assert out.loc[(2, 2), "us_shots90_r3"] == 0.0


def test_add_understat_rolling_without_any_understat_columns_is_all_nan():
    """The degradation rail: no Understat parquet means the columns exist and
    are empty, so LightGBM's schema is identical either way."""
    frame = pd.DataFrame([{"code": 1, "season_idx": 0, "gw": 1,
                           "kickoff_time": "2024-08-11T14:00:00Z"}])
    out = add_understat_rolling(frame)
    for col in understat_feature_columns():
        assert col in out.columns
        assert out[col].isna().all()


def test_understat_feature_columns_covers_every_stat_and_window():
    cols = understat_feature_columns()
    assert len(cols) == 5 * len(US_WINDOWS)
    assert "us_kp90_r5" in cols and "us_xgbuildup90_r38" in cols


def _ut_rows(team_code, dates, xga, ppda):
    return pd.DataFrame([
        {"team_code": team_code, "season_idx": 0, "date": d,
         "us_xga": g, "ppda": p}
        for d, g, p in zip(dates, xga, ppda)])


def test_add_understat_team_rolling_is_leakage_safe():
    ut = _ut_rows(3, ["2024-08-17", "2024-08-24", "2024-08-31"],
                  [0.5, 2.5, 1.0], [9.0, 11.0, 10.0])
    out = add_understat_team_rolling(ut).set_index("date")
    assert pd.isna(out.loc["2024-08-17", "team_us_xga_r5"])
    assert out.loc["2024-08-24", "team_us_xga_r5"] == 0.5
    assert out.loc["2024-08-31", "team_us_xga_r5"] == 1.5


def test_merge_understat_team_attaches_own_and_opponent_columns():
    ut = pd.concat([
        _ut_rows(3, ["2024-08-17", "2024-08-24"], [0.5, 2.5], [9.0, 11.0]),
        _ut_rows(4, ["2024-08-17", "2024-08-24"], [3.0, 1.0], [14.0, 13.0]),
    ], ignore_index=True)
    rolled = add_understat_team_rolling(ut)
    df = pd.DataFrame([{"code": 1, "season_idx": 0, "gw": 2, "team_code": 3,
                        "opp_code": 4,
                        "kickoff_time": "2024-08-24T14:00:00Z"}])
    out = merge_understat_team(df, rolled)
    assert out.loc[0, "team_us_xga_r5"] == 0.5
    assert out.loc[0, "opp_us_xga_r5"] == 3.0
    assert out.loc[0, "opp_ppda_r5"] == 14.0
    assert set(TEAM_US_FEATURES) <= set(out.columns)


def test_merge_understat_team_without_data_still_creates_the_columns():
    df = pd.DataFrame([{"code": 1, "season_idx": 0, "gw": 2, "team_code": 3,
                        "opp_code": 4,
                        "kickoff_time": "2024-08-24T14:00:00Z"}])
    out = merge_understat_team(df, None)
    for col in TEAM_US_FEATURES:
        assert col in out.columns and out[col].isna().all()


def test_merge_understat_team_does_not_add_rows():
    """A many-to-one join that fans out would double a player's gameweek."""
    ut = _ut_rows(3, ["2024-08-24", "2024-08-24"], [2.5, 2.5], [11.0, 11.0])
    rolled = add_understat_team_rolling(ut)
    df = pd.DataFrame([{"code": 1, "season_idx": 0, "gw": 2, "team_code": 3,
                        "opp_code": 4,
                        "kickoff_time": "2024-08-24T14:00:00Z"}])
    assert len(merge_understat_team(df, rolled)) == 1


from gaffer.features.engineer import (SHRINK_K, SHRINK_K_GRID,
                                      SHRUNK_FEATURES, add_shrunken_rates,
                                      best_shrinkage_k)


def _goal_rows(spec, code=1, position="FWD", team_code=3):
    """spec: list of (gw, minutes, goals, assists)."""
    return pd.DataFrame([
        {"code": code, "season_idx": 0, "gw": gw, "position": position,
         "team_code": team_code,
         "kickoff_time": f"2024-08-{10 + gw:02d}T14:00:00Z",
         "minutes": m, "goals": g, "assists": a}
        for gw, m, g, a in spec])


def test_add_shrunken_rates_adds_both_columns():
    out = add_shrunken_rates(_goal_rows([(1, 90, 1, 0), (2, 90, 0, 1)]))
    for col in SHRUNK_FEATURES:
        assert col in out.columns


def test_add_shrunken_rates_is_leakage_safe():
    """A match's own goal must not raise its own shrunken rate."""
    a = add_shrunken_rates(_goal_rows([(1, 90, 0, 0), (2, 90, 5, 0)]))
    b = add_shrunken_rates(_goal_rows([(1, 90, 0, 0), (2, 90, 0, 0)]))
    assert a.loc[1, "shrunk_goals90"] == b.loc[1, "shrunk_goals90"]


def test_add_shrunken_rates_pulls_a_thin_sample_toward_the_prior():
    """One match with a goal is not a one-goal-per-90 player."""
    frame = pd.concat([
        _goal_rows([(1, 90, 1, 0), (2, 90, 0, 0)], code=1),
        _goal_rows([(1, 90, 0, 0), (2, 90, 0, 0)], code=2),
        _goal_rows([(1, 90, 0, 0), (2, 90, 0, 0)], code=3),
    ], ignore_index=True)
    out = add_shrunken_rates(frame, k=10.0).set_index(["code", "gw"])
    assert 0.0 < out.loc[(1, 2), "shrunk_goals90"] < 0.5


def test_add_shrunken_rates_lets_go_of_the_prior_with_evidence():
    """Thirty matches of a goal each has to read close to one per 90.

    The scoreless teammate keeps the prior at 0.5 rather than 1.0 — with only
    one player in the (position, club) group the prior *is* his own rate and
    the shrunken value would sit at 1.0 from the first match, proving nothing.
    """
    frame = pd.concat([
        _goal_rows([(gw, 90, 1, 0) for gw in range(1, 32)], code=1),
        _goal_rows([(gw, 90, 0, 0) for gw in range(1, 32)], code=2),
    ], ignore_index=True)
    out = add_shrunken_rates(frame, k=10.0).set_index(["code", "gw"])
    assert out.loc[(1, 31), "shrunk_goals90"] > out.loc[(1, 5),
                                                        "shrunk_goals90"]
    assert out.loc[(1, 31), "shrunk_goals90"] > 0.6


def test_add_shrunken_rates_prior_excludes_the_same_gameweek():
    """A teammate's goals in the very same fixture must not enter the prior —
    the row would be predicting a match partly from that match's own result.
    Likewise nothing later: the frame is sorted by player, not by time, so a
    naive per-row cumsum over the (position, club) group would see both."""
    loud = pd.concat([
        _goal_rows([(1, 90, 0, 0), (2, 90, 0, 0)], code=1),
        _goal_rows([(1, 90, 0, 0), (2, 90, 5, 0)], code=2),
    ], ignore_index=True)
    quiet = pd.concat([
        _goal_rows([(1, 90, 0, 0), (2, 90, 0, 0)], code=1),
        _goal_rows([(1, 90, 0, 0), (2, 90, 0, 0)], code=2),
    ], ignore_index=True)
    a = add_shrunken_rates(loud, k=10.0).set_index(["code", "gw"])
    b = add_shrunken_rates(quiet, k=10.0).set_index(["code", "gw"])
    assert a.loc[(1, 2), "shrunk_goals90"] == b.loc[(1, 2), "shrunk_goals90"]


def test_add_shrunken_rates_with_no_history_at_all_is_the_prior():
    """The first row of a (position, club) group has neither a player sample
    nor a prior, and NaN is the honest answer."""
    out = add_shrunken_rates(_goal_rows([(1, 90, 0, 0)]))
    assert pd.isna(out.loc[0, "shrunk_goals90"])


def test_add_shrunken_rates_separates_positions_within_a_club():
    """A defender's prior is other defenders, not the club's strikers."""
    frame = pd.concat([
        _goal_rows([(gw, 90, 1, 0) for gw in range(1, 11)], code=1,
                   position="FWD"),
        _goal_rows([(gw, 90, 0, 0) for gw in range(1, 11)], code=2,
                   position="DEF"),
        _goal_rows([(gw, 90, 0, 0) for gw in range(1, 11)], code=3,
                   position="DEF"),
    ], ignore_index=True)
    out = add_shrunken_rates(frame, k=20.0).set_index(["code", "gw"])
    assert out.loc[(2, 10), "shrunk_goals90"] < out.loc[(1, 10),
                                                        "shrunk_goals90"]


def test_add_shrunken_rates_ignores_zero_minute_rows_in_the_denominator():
    out = add_shrunken_rates(_goal_rows([(1, 0, 0, 0), (2, 90, 1, 0),
                                         (3, 90, 0, 0)])).set_index("gw")
    assert out.loc[3, "shrunk_goals90"] > 0.0


def test_best_shrinkage_k_picks_from_the_grid():
    frame = pd.concat([
        _goal_rows([(gw, 90, gw % 2, 0) for gw in range(1, 26)], code=1),
        _goal_rows([(gw, 90, 0, 0) for gw in range(1, 26)], code=2),
    ], ignore_index=True)
    k = best_shrinkage_k(frame, holdout_slots=5)
    assert k in SHRINK_K_GRID


def test_best_shrinkage_k_on_a_frame_with_no_holdout_returns_the_default():
    k = best_shrinkage_k(_goal_rows([(1, 90, 0, 0)]), holdout_slots=5)
    assert k == SHRINK_K


from gaffer.features.engineer import (build_prediction_frame,
                                      latest_shrunken_rates,
                                      latest_understat_rolling,
                                      latest_understat_team)


def test_latest_understat_rolling_is_the_next_rows_form_vector():
    """The value a hypothetical next match would see: the same window,
    evaluated one row past the end of history."""
    hist = _us_rows([(1, 90, 4), (2, 90, 2)])
    latest = latest_understat_rolling(hist)
    assert abs(latest.loc[1, "us_shots90_r3"] - 6.0 / 180.0 * 90.0) < 1e-9


def test_latest_understat_rolling_is_one_row_per_player():
    hist = pd.concat([_us_rows([(1, 90, 4), (2, 90, 2)], code=1),
                      _us_rows([(1, 90, 0)], code=2)], ignore_index=True)
    latest = latest_understat_rolling(hist)
    assert sorted(latest.index) == [1, 2]


def test_latest_shrunken_rates_is_one_row_per_player():
    hist = pd.concat([_goal_rows([(gw, 90, 1, 0) for gw in range(1, 11)],
                                 code=1),
                      _goal_rows([(gw, 90, 0, 0) for gw in range(1, 11)],
                                 code=2)], ignore_index=True)
    latest = latest_shrunken_rates(hist)
    assert sorted(latest.index) == [1, 2]
    assert latest.loc[1, "shrunk_goals90"] > latest.loc[2, "shrunk_goals90"]


def test_latest_shrunken_rates_include_the_last_played_match():
    """The broadcast is the *next* fixture's value, and at the next fixture
    every match already played is legal evidence — the same convention the
    other three latest_* broadcasts follow. Tailing the shifted training
    column instead serves a vector one match stale, so a hat-trick on the
    final matchday would not reach the model until the week after."""
    hist = _goal_rows([(1, 90, 0, 0), (2, 90, 0, 0), (3, 90, 3, 0)])
    latest = latest_shrunken_rates(hist)
    # Own record 3 goals in 3 nineties; the position-by-club prior is this
    # lone player's own 1.0, so the shrunk rate is 1.0 either way it mixes.
    assert abs(latest.loc[1, "shrunk_goals90"] - 1.0) < 1e-9


def test_latest_understat_team_is_the_last_value_per_club():
    ut = pd.concat([
        _ut_rows(3, ["2024-08-17", "2024-08-24"], [0.5, 2.5], [9.0, 11.0]),
        _ut_rows(4, ["2024-08-17", "2024-08-24"], [3.0, 1.0], [14.0, 13.0]),
    ], ignore_index=True)
    latest = latest_understat_team(add_understat_team_rolling(ut))
    assert sorted(latest.index) == [3, 4]
    assert latest.loc[3, "team_us_xga_r5"] == 1.5


def test_merge_understat_team_falls_back_to_the_latest_for_future_rows():
    """A fixture in three weeks has no Understat row of its own; without the
    broadcast the column is NaN at serve time and NaN-free in training, which
    is exactly the train/serve skew this codebase keeps avoiding."""
    ut = pd.concat([
        _ut_rows(3, ["2024-08-17", "2024-08-24"], [0.5, 2.5], [9.0, 11.0]),
        _ut_rows(4, ["2024-08-17", "2024-08-24"], [3.0, 1.0], [14.0, 13.0]),
    ], ignore_index=True)
    rolled = add_understat_team_rolling(ut)
    future = pd.DataFrame([{"code": 1, "season_idx": 0, "gw": 9,
                            "team_code": 3, "opp_code": 4,
                            "kickoff_time": "2024-10-19T14:00:00Z"}])
    out = merge_understat_team(future, rolled,
                               latest=latest_understat_team(rolled))
    assert out.loc[0, "team_us_xga_r5"] == 1.5
    assert out.loc[0, "opp_us_xga_r5"] == 2.0


def test_feature_columns_covers_every_new_block():
    from gaffer.features.engineer import feature_columns

    cols = set(feature_columns())
    assert set(understat_feature_columns()) <= cols
    assert set(TEAM_US_FEATURES) <= cols
    assert set(SHRUNK_FEATURES) <= cols


def _pred_hist():
    rows = _us_rows([(1, 90, 4), (2, 90, 2)])
    rows["position"] = "FWD"
    rows["team_code"] = 3
    rows["opp_code"] = 4
    rows["was_home"] = True
    rows["minutes"] = 90
    rows["goals"] = 1
    rows["assists"] = 0
    rows["starts"] = 1
    return rows


def test_build_prediction_frame_broadcasts_the_new_features():
    hist = _pred_hist()
    future = pd.DataFrame([{"code": 1, "season_idx": 0, "gw": 3,
                            "position": "FWD", "team_code": 3, "opp_code": 4,
                            "was_home": True,
                            "kickoff_time": "2024-08-24T14:00:00Z"}])
    out = build_prediction_frame(hist, future)
    assert out["us_shots90_r3"].notna().all()
    assert out["shrunk_goals90"].notna().all()
    assert len(out) == 1


def test_build_prediction_frame_takes_the_team_understat_frame():
    hist = _pred_hist()
    future = pd.DataFrame([{"code": 1, "season_idx": 0, "gw": 3,
                            "position": "FWD", "team_code": 3, "opp_code": 4,
                            "was_home": True,
                            "kickoff_time": "2024-08-24T14:00:00Z"}])
    ut = pd.concat([
        _ut_rows(3, ["2024-08-11", "2024-08-18"], [0.5, 2.5], [9.0, 11.0]),
        _ut_rows(4, ["2024-08-11", "2024-08-18"], [3.0, 1.0], [14.0, 13.0]),
    ], ignore_index=True)
    out = build_prediction_frame(hist, future,
                                 understat_team=add_understat_team_rolling(ut))
    assert out.loc[0, "opp_us_xga_r5"] == 2.0


def test_build_prediction_frame_without_understat_still_makes_the_columns():
    hist = _pred_hist().drop(columns=["us_minutes", "us_shots",
                                      "us_key_passes", "us_npxg",
                                      "us_xgchain", "us_xgbuildup"])
    future = pd.DataFrame([{"code": 1, "season_idx": 0, "gw": 3,
                            "position": "FWD", "team_code": 3, "opp_code": 4,
                            "was_home": True,
                            "kickoff_time": "2024-08-24T14:00:00Z"}])
    out = build_prediction_frame(hist, future)
    for col in understat_feature_columns() + TEAM_US_FEATURES:
        assert col in out.columns


def _congestion_frame() -> pd.DataFrame:
    """One club (team_code 3), one player, four league matches over 24 days."""
    kicks = ["2025-08-16T14:00:00Z", "2025-08-23T14:00:00Z",
             "2025-08-30T14:00:00Z", "2025-09-09T14:00:00Z"]
    return pd.DataFrame({
        "code": [1] * 4, "season_idx": [3] * 4, "gw": [1, 2, 3, 4],
        "team_code": [3] * 4, "minutes": [90, 90, 90, 90],
        "kickoff_time": kicks})


def test_congestion_measures_the_gaps_either_side_of_a_match():
    from gaffer.features.engineer import add_congestion

    out = add_congestion(_congestion_frame()).set_index("gw")
    assert pd.isna(out.loc[1, "days_since_last_match"])   # no earlier match
    assert out.loc[2, "days_since_last_match"] == 7.0
    assert out.loc[4, "days_since_last_match"] == 10.0
    assert out.loc[1, "days_to_next_match"] == 7.0
    assert out.loc[3, "days_to_next_match"] == 10.0
    assert pd.isna(out.loc[4, "days_to_next_match"])      # end of the frame


def test_congestion_counts_only_strictly_earlier_matches_in_the_window():
    """A row's own match is not in its own 14-day history — the same
    shift(1) discipline every other feature in this module keeps."""
    from gaffer.features.engineer import add_congestion

    out = add_congestion(_congestion_frame()).set_index("gw")
    assert out.loc[1, "matches_last_14d"] == 0.0
    assert out.loc[2, "matches_last_14d"] == 1.0
    assert out.loc[3, "matches_last_14d"] == 2.0
    # GW4 is 2025-09-09: only 2025-08-30 falls inside 14 days.
    assert out.loc[4, "matches_last_14d"] == 1.0


def test_congestion_counts_cup_matches_the_league_calendar_cannot_see():
    """The whole point of data/cups.py: a midweek EFL Cup tie is a real
    congestion event and appears in no FPL fixture list."""
    from gaffer.features.engineer import add_congestion

    cups = pd.DataFrame({"season": ["2025-26"] * 2, "season_idx": [3] * 2,
                         "tournament": ["efl-cup"] * 2,
                         "date": [pd.Timestamp("2025-08-27").date(),
                                  pd.Timestamp("2025-09-02").date()],
                         "team_code": [3, 3]})
    out = add_congestion(_congestion_frame(), cups=cups).set_index("gw")
    # GW3 (2025-08-30) now also sees the 08-27 tie.
    assert out.loc[3, "matches_last_14d"] == 3.0
    # GW4 (2025-09-09) sees 08-30, 09-02 and 08-27 is 13 days back.
    assert out.loc[4, "matches_last_14d"] == 3.0
    # The 08-30 league match still counts once, not twice.
    assert out.loc[2, "matches_last_14d"] == 1.0


def test_congestion_with_no_cup_frame_is_league_only_not_nan():
    """`cups=None` means "no cup data on this machine", which must produce a
    number, not a hole — the model has to see the same column in training and
    at serve time."""
    from gaffer.features.engineer import add_congestion

    out = add_congestion(_congestion_frame(), cups=None)
    assert out["matches_last_14d"].notna().all()


def test_feature_columns_include_the_congestion_block():
    from gaffer.features.engineer import CONGESTION_FEATURES, feature_columns

    cols = set(feature_columns())
    assert set(CONGESTION_FEATURES) <= cols


def test_prediction_frame_carries_congestion_for_future_fixtures():
    """A future row's congestion is genuinely knowable at the deadline: the
    fixture calendar is published weeks ahead. Without it the column would be
    populated in training and empty at serve time."""
    from gaffer.features.engineer import build_prediction_frame

    hist = _congestion_frame()
    future = pd.DataFrame({
        "code": [1], "season_idx": [3], "gw": [5], "team_code": [3],
        "opp_code": [43], "was_home": [True], "position": ["MID"],
        "kickoff_time": ["2025-09-13T14:00:00Z"]})
    out = build_prediction_frame(hist, future)
    assert out["days_since_last_match"].iloc[0] == 4.0
    assert out["matches_last_14d"].iloc[0] == 2.0


def test_shrunk_rate_is_unchanged_by_the_denominator_refactor():
    """v4b's rates are a shipped, gated feature. The generalisation under
    them must be arithmetic-identical: (sum stat + k*prior) / (sum 90s + k)."""
    from gaffer.features.engineer import _shrunk_rate

    df = pd.DataFrame({
        "code": [1, 1, 1], "season_idx": [0, 0, 0], "gw": [1, 2, 3],
        "position": ["FWD"] * 3, "team_code": [3] * 3,
        "minutes": [90.0, 90.0, 90.0], "goals": [1.0, 0.0, 2.0]})
    out = _shrunk_rate(df, "goals", k=2.0)
    # Row 3 sees one 90 with 1 goal from row 1 and one with 0 from row 2:
    # own = 1 goal / 2 nineties; the prior has no other club-mate, so it is
    # NaN and the whole expression is NaN. Row 1 has no history at all.
    assert pd.isna(out.iloc[0])
    assert len(out) == 3


def _mode_frame() -> pd.DataFrame:
    """Two club-mates: a nailed starter and a fringe player with two cameos."""
    rows = []
    for gw in range(1, 11):
        rows.append({"code": 1, "season_idx": 0, "gw": gw, "position": "MID",
                     "team_code": 3, "minutes": 90.0, "starts": 1.0,
                     "kickoff_time": None})
        mins = 15.0 if gw in (3, 7) else 0.0
        rows.append({"code": 2, "season_idx": 0, "gw": gw, "position": "MID",
                     "team_code": 3, "minutes": mins,
                     "starts": 0.0, "kickoff_time": None})
    return pd.DataFrame(rows)


def test_shrunken_modes_separate_a_starter_from_a_fringe_player():
    from gaffer.features.engineer import add_shrunken_modes

    out = add_shrunken_modes(_mode_frame(), k=2.0)
    last = out[out["gw"] == 10].set_index("code")
    assert last.loc[1, "shrunk_start_rate"] > 0.7
    assert last.loc[2, "shrunk_start_rate"] < 0.3
    # The club prior is dragged up by the ever-present starter, so both land
    # above the fringe player's own 15-minute record — the separation the
    # feature has to preserve is the gap, not the absolute level.
    assert last.loc[1, "shrunk_min_per_app"] > 70.0
    assert last.loc[2, "shrunk_min_per_app"] < 60.0


def test_shrunken_modes_pull_toward_the_prior_at_low_n():
    """The whole point of the shrinkage: two matches is not evidence. A
    heavier k must move a thin record further toward the club prior."""
    from gaffer.features.engineer import add_shrunken_modes

    df = _mode_frame()
    early = df[df["gw"] <= 3]
    light = add_shrunken_modes(early, k=1.0)
    heavy = add_shrunken_modes(early, k=50.0)
    row = (light["code"] == 2) & (light["gw"] == 3)
    light_v = light.loc[row, "shrunk_start_rate"].iloc[0]
    heavy_v = heavy.loc[row, "shrunk_start_rate"].iloc[0]
    # The club prior is dragged up by the ever-present starter, so heavier
    # shrinkage lifts the fringe player toward it.
    assert heavy_v > light_v


def test_shrunken_modes_never_see_the_rows_own_match():
    """Leakage rail. A player whose only match is this one has nothing of his
    own to average, so the value is the prior or NaN — never his own start."""
    from gaffer.features.engineer import add_shrunken_modes

    out = add_shrunken_modes(_mode_frame(), k=2.0)
    first = out[out["gw"] == 1].set_index("code")
    assert pd.isna(first.loc[1, "shrunk_start_rate"])
    assert pd.isna(first.loc[2, "shrunk_start_rate"])


def test_minutes_per_appearance_ignores_matches_he_did_not_play():
    """A DNP is not a zero-minute appearance. Averaging it in would read a
    rotated-out starter as a 20-minute cameo player."""
    from gaffer.features.engineer import add_shrunken_modes

    out = add_shrunken_modes(_mode_frame(), k=0.0)
    last = out[(out["gw"] == 10) & (out["code"] == 2)]
    # Two appearances of 15 minutes and eight DNPs -> 15, not 3.
    assert abs(last["shrunk_min_per_app"].iloc[0] - 15.0) < 1e-9


def test_feature_columns_include_the_mode_rate_block():
    from gaffer.features.engineer import SHRUNK_MODE_FEATURES, feature_columns

    assert set(SHRUNK_MODE_FEATURES) <= set(feature_columns())


def test_prediction_frame_carries_the_mode_rates_including_the_last_match():
    """Same as-of-end contract latest_shrunken_rates keeps: a future row's
    rate counts every played match, the last one included."""
    from gaffer.features.engineer import build_prediction_frame

    hist = _mode_frame()
    future = pd.DataFrame({
        "code": [1, 2], "season_idx": [0, 0], "gw": [11, 11],
        "team_code": [3, 3], "opp_code": [43, 43], "was_home": [True, True],
        "position": ["MID", "MID"], "kickoff_time": [None, None]})
    out = build_prediction_frame(hist, future).set_index("code")
    assert out.loc[1, "shrunk_start_rate"] > out.loc[2, "shrunk_start_rate"]
