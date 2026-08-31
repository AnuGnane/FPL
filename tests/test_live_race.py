"""The live EP race: where the score is going, not where it is.

Every owned player carries a banked expectation for this gameweek — the same
``ep`` the optimizer picked him on. The race spends it down as his match is
played: none of it before kick-off, all of it by full time. Add what is left
to the projected score and you have the number the afternoon is heading for.
"""

from __future__ import annotations

import pytest

from gaffer.live_gw import race_value, remaining_ep_total, remaining_fraction


def test_a_match_yet_to_kick_off_still_owes_everything():
    assert remaining_fraction(0, started=False, finished=False) == 1.0


def test_a_finished_match_owes_nothing_however_many_minutes_were_played():
    assert remaining_fraction(0, started=True, finished=True) == 0.0
    assert remaining_fraction(90, started=True, finished=True) == 0.0


def test_an_in_play_match_owes_the_minutes_not_yet_played():
    assert remaining_fraction(45, started=True, finished=False) == 0.5
    assert remaining_fraction(30, started=True, finished=False) == pytest.approx(
        2 / 3)


def test_stoppage_time_never_owes_a_negative():
    assert remaining_fraction(96, started=True, finished=False) == 0.0


def test_a_double_gameweek_still_owes_the_fixture_not_yet_played():
    """Banked EP is the sum of both fixtures'. One of them played out and the
    other not kicked off leaves half of it owed, however many minutes the
    first one took."""
    assert remaining_fraction(90, started=True, finished=False,
                              fixtures=2, unplayed=1) == 0.5
    assert remaining_fraction(0, started=True, finished=False,
                              fixtures=2, unplayed=1) == 1.0


def test_a_double_gameweek_with_one_match_in_play_owes_the_rest_of_it():
    """A third of the first match left plus the whole of the second, over two
    fixtures."""
    assert remaining_fraction(60, started=True, finished=False, fixtures=2,
                              unplayed=1) == pytest.approx(2 / 3)


def test_a_double_gameweek_that_is_over_owes_nothing():
    assert remaining_fraction(180, started=True, finished=True, fixtures=2,
                              unplayed=0) == 0.0


def test_a_single_gameweek_is_the_arithmetic_it_always_was():
    """The counts default to one fixture, none unplayed, so every existing
    caller keeps the fraction it had."""
    assert remaining_fraction(45, started=True, finished=False,
                              fixtures=1, unplayed=0) == 0.5


def test_remaining_ep_spends_a_double_gameweek_down_fixture_by_fixture():
    """Element 1 has played the first of two; half his banked EP is still
    owed. Element 2 has a single fixture and is unaffected."""
    total = remaining_ep_total({1: 1, 2: 1}, {1: 8.0, 2: 4.0},
                               {1: 90, 2: 45}, {1: True, 2: True},
                               {1: False, 2: False},
                               counts_of={1: (2, 1), 2: (1, 0)})
    assert total == 4.0 + 2.0


def test_remaining_ep_scales_by_multiplier_and_skips_the_bench():
    mult = {1: 2, 2: 1, 3: 0}
    ep = {1: 5.0, 2: 4.0, 3: 9.0}
    minutes = {1: 0, 2: 45, 3: 0}
    started = {1: False, 2: True, 3: False}
    finished = {1: False, 2: False, 3: False}
    # 2 x 5.0 x 1.0 + 1 x 4.0 x 0.5, and nothing for the benched 9.0
    assert remaining_ep_total(mult, ep, minutes, started, finished) == 12.0


def test_remaining_ep_is_zero_when_every_match_is_over():
    mult = {1: 2, 2: 1}
    finished = {1: True, 2: True}
    assert remaining_ep_total(mult, {1: 5.0, 2: 4.0}, {1: 90, 2: 90},
                              {1: True, 2: True}, finished) == 0.0


def test_a_player_with_no_banked_ep_contributes_nothing_rather_than_failing():
    """Someone bought after the advice ran, or outside the candidate pool."""
    assert remaining_ep_total({1: 1}, {}, {1: 0}, {1: False}, {1: False}) == 0.0


def test_remaining_ep_with_no_components_at_all_is_zero():
    """The degradation the router turns into a notice: the race becomes the
    projected score, which is still the truth, just less of it."""
    assert remaining_ep_total({1: 2, 2: 1}, {}, {}, {}, {}) == 0.0


def test_race_value_adds_the_projected_score_to_what_is_left():
    assert race_value(41, 12.75) == 53.75


def test_race_value_of_a_spent_gameweek_is_the_score_itself():
    assert race_value(66, 0.0) == 66.0
