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
