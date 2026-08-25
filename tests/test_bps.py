import pandas as pd

from gaffer.features.bps import (adjust_bps, award_bonus, fixture_pair,
                                 rederive_bonus)


def _rows(spec):
    """spec: list of (season_idx, bps, cbi)."""
    return pd.DataFrame([{"season_idx": s, "bps": b, "cbi": c,
                          "minutes": 90}
                         for s, b, c in spec])


def test_adjust_bps_applies_the_cbi_rebalance_to_old_seasons():
    # cbi 6 earned 3 BPS under the old per-two rule and earns 2 under the
    # new per-three rule: floor(6/3) - floor(6/2) = -1.
    out = adjust_bps(_rows([(0, 30.0, 6.0)]), current_idx=3)
    assert list(out) == [29.0]


def test_adjust_bps_delta_is_never_positive():
    frame = _rows([(0, 30.0, float(c)) for c in range(0, 25)])
    delta = adjust_bps(frame, current_idx=3) - frame["bps"]
    assert (delta <= 0).all()


def test_adjust_bps_leaves_current_season_rows_untouched():
    # Current-season rows are already scored under the new rules.
    out = adjust_bps(_rows([(3, 30.0, 12.0)]), current_idx=3)
    assert list(out) == [30.0]


def test_adjust_bps_treats_a_missing_cbi_count_as_no_adjustment():
    # cbi only exists from 2025-26 onwards; older rows cannot be corrected.
    out = adjust_bps(_rows([(0, 30.0, float("nan"))]), current_idx=3)
    assert list(out) == [30.0]


def test_adjust_bps_keeps_a_missing_bps_missing():
    out = adjust_bps(_rows([(0, float("nan"), 6.0)]), current_idx=3)
    assert out.isna().all()

def test_award_bonus_standard_three_two_one():
    assert award_bonus([30.0, 25.0, 20.0, 10.0]) == [3, 2, 1, 0]
    assert sum(award_bonus([30.0, 25.0, 20.0, 10.0])) == 6


def test_award_bonus_tie_for_first_among_two_is_three_three_one():
    assert award_bonus([30.0, 30.0, 25.0, 10.0]) == [3, 3, 1, 0]


def test_award_bonus_tie_for_first_among_three_awards_no_two_or_one():
    assert award_bonus([30.0, 30.0, 30.0, 25.0, 10.0]) == [3, 3, 3, 0, 0]


def test_award_bonus_tie_for_second_awards_two_two_and_no_one():
    assert award_bonus([30.0, 25.0, 25.0, 10.0]) == [3, 2, 2, 0]


def test_award_bonus_tie_for_third_gives_every_tied_player_one():
    assert award_bonus([30.0, 25.0, 20.0, 20.0, 10.0]) == [3, 2, 1, 1, 0]


def test_award_bonus_on_an_empty_fixture_awards_nothing():
    assert award_bonus([]) == []


def _fixture(bps_values, gw=1, season_idx=0, team=1, opp=2,
             kickoff="2025-08-16T14:00:00Z"):
    """One side of a match per row — both teams share the fixture key."""
    return pd.DataFrame([
        {"season_idx": season_idx, "gw": gw, "kickoff_time": kickoff,
         "team_code": team if i % 2 == 0 else opp,
         "opp_code": opp if i % 2 == 0 else team,
         "bps": v, "minutes": 90}
        for i, v in enumerate(bps_values)])


def test_fixture_pair_is_the_same_string_for_both_sides():
    pair = fixture_pair(_fixture([30.0, 25.0]))
    assert pair.iloc[0] == pair.iloc[1]


def test_rederive_bonus_awards_six_points_across_a_non_tied_fixture():
    out = rederive_bonus(_fixture([30.0, 25.0, 20.0, 10.0]))
    assert list(out) == [3.0, 2.0, 1.0, 0.0]
    assert out.sum() == 6.0


def test_rederive_bonus_scores_each_fixture_independently():
    one = _fixture([30.0, 25.0, 20.0], gw=1, team=1, opp=2)
    two = _fixture([9.0, 8.0, 7.0], gw=1, team=3, opp=4,
                   kickoff="2025-08-16T16:30:00Z")
    out = rederive_bonus(pd.concat([one, two], ignore_index=True))
    assert list(out) == [3.0, 2.0, 1.0, 3.0, 2.0, 1.0]


def test_rederive_bonus_splits_a_double_gameweek_by_kickoff():
    first = _fixture([30.0, 25.0, 20.0], gw=7,
                     kickoff="2025-10-01T19:00:00Z")
    second = _fixture([12.0, 11.0, 10.0], gw=7,
                      kickoff="2025-10-04T14:00:00Z")
    out = rederive_bonus(pd.concat([first, second], ignore_index=True))
    assert list(out) == [3.0, 2.0, 1.0, 3.0, 2.0, 1.0]


def test_rederive_bonus_ignores_players_who_did_not_appear():
    frame = _fixture([30.0, 25.0, 20.0, 0.0])
    frame.loc[3, "minutes"] = 0
    out = rederive_bonus(frame)
    assert list(out) == [3.0, 2.0, 1.0, 0.0]


def test_rederive_bonus_reads_an_explicit_adjusted_series():
    frame = _fixture([30.0, 25.0, 20.0])
    adjusted = pd.Series([10.0, 40.0, 20.0], index=frame.index)
    out = rederive_bonus(frame, adjusted)
    assert list(out) == [1.0, 3.0, 2.0]
