"""F1 and F2's builders: what they compute, and what they refuse to see."""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.features.engineer import (ROTATION_PRIOR_FEATURES,
                                      TENURE_SHRINK_K, add_rotation_priors)


def _frame(managers=("A", "A", "A", "B", "B", "B")) -> pd.DataFrame:
    """Six matchdays, two players at one club, one manager change midway."""
    rows = []
    for i, _ in enumerate(managers):
        when = pd.Timestamp("2023-08-05", tz="UTC") + pd.Timedelta(days=7 * i)
        for code, started in ((1, 1.0), (2, 1.0 if i >= 3 else 0.0)):
            rows.append({"code": code, "team_code": 3, "season_idx": 1,
                         "gw": i + 1, "kickoff_time": when.isoformat(),
                         "starts": started,
                         "minutes": 90.0 if started else 0.0})
    return pd.DataFrame(rows)


def _tenures() -> pd.DataFrame:
    return pd.DataFrame({
        "team_code": [3, 3],
        "club": ["Arsenal", "Arsenal"],
        "manager": ["A", "B"],
        "start_date": pd.to_datetime(["2023-01-01", "2023-08-26"], utc=True),
        "end_date": pd.to_datetime(["2023-08-26", None], utc=True)})


def test_every_prior_feature_is_produced():
    out = add_rotation_priors(_frame(), _tenures())
    for col in ROTATION_PRIOR_FEATURES:
        assert col in out.columns


def test_the_first_match_of_a_spell_has_no_prior_evidence():
    """Strictly-past windows: the opening match under a manager has nothing
    before it, so the share and the churn are undefined rather than zero."""
    out = add_rotation_priors(_frame(), _tenures()).sort_values(
        ["code", "gw"]).reset_index(drop=True)
    first = out[(out["code"] == 1) & (out["gw"] == 1)].iloc[0]
    assert pd.isna(first["tenure_start_share"])
    assert pd.isna(first["xi_churn_r5"])
    assert first["manager_tenure_matches"] == 0.0


def test_the_tenure_counter_restarts_when_the_manager_changes():
    out = add_rotation_priors(_frame(), _tenures())
    by_gw = out[out["code"] == 1].set_index("gw")["manager_tenure_matches"]
    # Matches 1-3 under A, 4-6 under B: the count is matches *before* this one.
    assert list(by_gw.loc[[1, 2, 3]]) == [0.0, 1.0, 2.0]
    assert list(by_gw.loc[[4, 5, 6]]) == [0.0, 1.0, 2.0]


def test_the_share_is_shrunk_toward_the_club_mean():
    """Player 2 starts nothing under A. With one prior match his own record
    says 0.0 and the club's says 0.5, and the shrunk value sits between."""
    out = add_rotation_priors(_frame(), _tenures())
    row = out[(out["code"] == 2) & (out["gw"] == 2)].iloc[0]
    expected = (0.0 + TENURE_SHRINK_K * 0.5) / (1.0 + TENURE_SHRINK_K)
    assert row["tenure_start_share"] == pytest.approx(expected)


def test_started_last_match_reads_the_previous_row_only():
    out = add_rotation_priors(_frame(), _tenures())
    by_gw = out[out["code"] == 2].set_index("gw")["started_last_match"]
    assert pd.isna(by_gw.loc[1])
    assert by_gw.loc[4] == 0.0     # gw3 was a benching
    assert by_gw.loc[5] == 1.0     # gw4 was a start


def test_the_churn_index_counts_changes_between_consecutive_xis():
    """Player 2 comes into the XI at match 4, so exactly one name changed.

    The comparison is scoped to the spell, so it is only visible when match 3
    and match 4 sit in the same window: under the real tenures they are the
    last match of A and the first of B, and a new manager's opening XI is not
    a change *he* made.
    """
    out = add_rotation_priors(_frame(), None)
    row = out[(out["code"] == 1) & (out["gw"] == 6)].iloc[0]
    assert row["xi_churn_r5"] > 0.0
    spelled = add_rotation_priors(_frame(), _tenures())
    across = spelled[(spelled["code"] == 1) & (spelled["gw"] == 6)].iloc[0]
    assert across["xi_churn_r5"] == 0.0


def test_without_the_asset_the_window_is_the_club_season():
    """No asset: one spell per club-season, so the counter never restarts
    inside a season and every column still computes."""
    out = add_rotation_priors(_frame(), None)
    by_gw = out[out["code"] == 1].set_index("gw")["manager_tenure_matches"]
    assert list(by_gw.loc[[1, 4, 6]]) == [0.0, 3.0, 5.0]
    assert out["tenure_start_share"].notna().any()


def test_a_frame_without_starts_yields_all_nan_columns():
    df = _frame().drop(columns=["starts"])
    out = add_rotation_priors(df, _tenures())
    for col in ROTATION_PRIOR_FEATURES:
        assert out[col].isna().all()


# --- serve side ------------------------------------------------------------

from gaffer.features.engineer import (build_prediction_frame,  # noqa: E402
                                      feature_columns,
                                      latest_rotation_priors)


def _future(gws=(7, 8), team=3) -> pd.DataFrame:
    rows = []
    for i, gw in enumerate(gws):
        when = pd.Timestamp("2023-09-16", tz="UTC") + pd.Timedelta(days=7 * i)
        for code in (1, 2):
            rows.append({"code": code, "season_idx": 1, "gw": gw,
                         "team_code": team, "opp_code": 4, "was_home": True,
                         "position": "MID",
                         "kickoff_time": when.isoformat()})
    return pd.DataFrame(rows)


def test_the_serve_state_is_one_row_per_player():
    out = latest_rotation_priors(_frame(), _tenures())
    assert sorted(out.index) == [1, 2]
    for col in ROTATION_PRIOR_FEATURES:
        assert col in out.columns


def test_the_serve_state_counts_the_last_played_match():
    """As-of-end, like every other ``latest_*``: six matches have been played
    under the two spells, three of them under the current one."""
    out = latest_rotation_priors(_frame(), _tenures())
    assert out.loc[1, "manager_tenure_matches"] == 3.0
    assert out.loc[1, "started_last_match"] == 1.0


def test_the_prediction_frame_carries_every_prior_feature():
    out = build_prediction_frame(_frame(), _future(), tenures=_tenures())
    for col in ROTATION_PRIOR_FEATURES:
        assert col in out.columns
    assert out["manager_tenure_matches"].notna().all()


def test_a_change_of_manager_blanks_the_share_it_no_longer_describes():
    """The state was measured under the manager in post at the last match.
    A future fixture past a change describes a squad nobody has picked yet."""
    later = _tenures().copy()
    later.loc[len(later)] = {"team_code": 3, "club": "Arsenal",
                             "manager": "C",
                             "start_date": pd.Timestamp("2023-09-10",
                                                        tz="UTC"),
                             "end_date": pd.NaT}
    later.loc[1, "end_date"] = pd.Timestamp("2023-09-10", tz="UTC")
    out = build_prediction_frame(_frame(), _future(), tenures=later)
    assert out["tenure_start_share"].isna().all()
    assert (out["manager_tenure_matches"] == 0.0).all()


def test_the_prior_features_are_in_the_canonical_strip_list():
    cols = feature_columns()
    for col in ROTATION_PRIOR_FEATURES:
        assert col in cols


# --- F2: the two congestion arms ------------------------------------------

from gaffer.features.engineer import (CONGESTION_FEATURES,  # noqa: E402
                                      LEAGUE_CONGESTION_FEATURES,
                                      add_congestion)


def _cups() -> pd.DataFrame:
    return pd.DataFrame({"team_code": [3],
                         "date": [pd.Timestamp("2023-08-09", tz="UTC")]})


def test_the_league_arm_has_its_own_column_names():
    assert LEAGUE_CONGESTION_FEATURES == ["lg_days_since_last_match",
                                          "lg_days_to_next_match",
                                          "lg_matches_last_14d"]


def test_the_two_arms_coexist_in_one_frame():
    """Both variants on one frame is what makes them separable arms: the
    driver picks columns, it does not rebuild the features."""
    out = add_congestion(_frame(), _cups())
    out = add_congestion(out, None, prefix="lg_")
    for col in CONGESTION_FEATURES + LEAGUE_CONGESTION_FEATURES:
        assert col in out.columns


def test_the_cup_tie_lands_only_in_the_cup_inclusive_arm():
    """The whole of D2: with cup ties in, a club's midweek tie raises the
    load; league-only, it cannot, so the arm carries no season indicator."""
    out = add_congestion(_frame(), _cups())
    out = add_congestion(out, None, prefix="lg_")
    row = out[(out["code"] == 1) & (out["gw"] == 2)].iloc[0]
    assert row["matches_last_14d"] > row["lg_matches_last_14d"]


def test_the_league_arm_is_the_no_cups_call_renamed():
    plain = add_congestion(_frame(), None)
    prefixed = add_congestion(_frame(), None, prefix="lg_")
    for a, b in zip(CONGESTION_FEATURES, LEAGUE_CONGESTION_FEATURES):
        pd.testing.assert_series_equal(plain[a], prefixed[b],
                                       check_names=False)


def test_a_frame_without_kickoffs_still_gets_prefixed_columns():
    out = add_congestion(_frame().drop(columns=["kickoff_time"]), None,
                         prefix="lg_")
    for col in LEAGUE_CONGESTION_FEATURES:
        assert col in out.columns and out[col].isna().all()


def test_the_prediction_frame_carries_both_arms():
    out = build_prediction_frame(_frame(), _future(), cups=_cups(),
                                 tenures=_tenures())
    for col in CONGESTION_FEATURES + LEAGUE_CONGESTION_FEATURES:
        assert col in out.columns


def test_both_arms_are_in_the_canonical_strip_list():
    cols = feature_columns()
    for col in CONGESTION_FEATURES + LEAGUE_CONGESTION_FEATURES:
        assert col in cols
