import pandas as pd
import pytest
from gaffer.league_mode import (SIGMA, LAMBDA_CAP, Strategy,
                                compute_strategy, win_probability)

RIVALS = pd.DataFrame({"entry_name": ["Leader", "Mid", "Tail"],
                       "total": [500, 460, 400]})


def test_small_gap_is_neutral():
    s = compute_strategy(my_total=495, rivals=RIVALS, current_gw=10)
    assert s.stance == "neutral" and s.lam == 0.0


def test_big_gap_chases_with_positive_lambda():
    s = compute_strategy(my_total=380, rivals=RIVALS, current_gw=30)
    assert s.stance == "chase"
    assert s.lam == pytest.approx(
        0.5 * min(120 / (2 * 18 * 9 ** 0.5) - 0.5, 1.0))
    assert s.rival_name == "Leader"


def test_leading_big_defends_with_negative_lambda():
    s = compute_strategy(my_total=560, rivals=RIVALS, current_gw=36)
    assert s.stance == "defend" and s.lam < 0
    assert s.rival_name == "Leader"          # nearest chaser


def test_win_probability_symmetric_and_bounded():
    assert win_probability(500, 500, 10) == pytest.approx(0.5)
    assert 0.5 < win_probability(520, 500, 10) < 1.0


def test_empty_rivals_is_neutral():
    s = compute_strategy(500, pd.DataFrame(columns=["entry_name", "total"]),
                         10)
    assert s.stance == "neutral" and s.lam == 0.0


def test_tied_with_leader_is_neutral():
    """Dead level: gap 0 must land on neutral, not flip into a stance."""
    s = compute_strategy(my_total=500, rivals=RIVALS, current_gw=36)
    assert s.stance == "neutral"
    assert s.lam == 0.0
    assert s.gap == 0
    assert isinstance(s, Strategy)
    assert (SIGMA, LAMBDA_CAP) == (18.0, 0.5)
