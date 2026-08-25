import pytest

from gaffer.optimize.ft_value import (FT_CAP, LambdaLookup, lambda_table,
                                      value_table)


def test_the_cap_is_five_free_transfers():
    assert FT_CAP == 5


def test_value_at_zero_weeks_remaining_is_zero_for_every_k():
    v = value_table([1.0, 2.0], weeks=3)
    for k in range(FT_CAP + 1):
        assert v[(k, 0)] == 0.0


def test_one_week_left_with_one_ft_is_the_expected_surplus():
    """Hand-checkable: one week, one transfer, no future. Spending beats not
    spending whenever the surplus is positive, so V(1,1) = E[max(s, 0)]."""
    v = value_table([0.0, 2.0], weeks=1)
    assert abs(v[(1, 1)] - 1.0) < 1e-12


def test_one_week_left_with_a_negative_surplus_draw_is_floored_at_zero():
    """Nobody is forced to make a transfer."""
    v = value_table([-3.0, 3.0], weeks=1)
    assert abs(v[(1, 1)] - 1.5) < 1e-12


def test_value_with_zero_fts_this_week_defers_to_next_week():
    v = value_table([2.0], weeks=2)
    assert abs(v[(0, 2)] - v[(1, 1)]) < 1e-12


def test_lambda_is_decreasing_in_k():
    """The core qualitative claim of spec §5: the fifth banked transfer is
    worth less than the second. If this fails the table is not shippable."""
    lam = lambda_table([0.5, 1.5, 3.0, 6.0], weeks=30)
    for t in (10, 20, 30):
        vals = [lam[(k, t)] for k in range(1, FT_CAP + 1)]
        assert vals == sorted(vals, reverse=True), (t, vals)


def test_lambda_decays_towards_zero_as_the_season_runs_out():
    lam = lambda_table([0.5, 1.5, 3.0, 6.0], weeks=30)
    assert lam[(2, 30)] > lam[(2, 10)] > lam[(2, 2)] > lam[(2, 1)]
    assert lam[(2, 1)] >= 0.0


def test_lambda_at_one_week_remaining_is_the_last_chance_value():
    """With one week left an FT is worth exactly what it can buy this week."""
    lam = lambda_table([0.0, 4.0], weeks=1)
    assert abs(lam[(1, 1)] - 2.0) < 1e-12


def test_lambda_is_never_negative():
    lam = lambda_table([-2.0, 0.0, 1.0, 8.0], weeks=20)
    assert min(lam.values()) >= 0.0


def test_the_overflow_cap_makes_the_sixth_transfer_worthless():
    """FPL loses the overflow; the table has to know that."""
    lam = lambda_table([1.0, 2.0], weeks=20)
    assert (FT_CAP + 1, 20) not in lam
    # And the fifth is worth strictly less than the fourth, because banking
    # to five risks losing the next arrival entirely.
    assert lam[(FT_CAP, 20)] < lam[(FT_CAP - 1, 20)]


def test_a_richer_surplus_distribution_raises_every_lambda():
    lean = lambda_table([0.5, 1.0], weeks=20)
    rich = lambda_table([3.0, 6.0], weeks=20)
    for k in range(1, FT_CAP + 1):
        assert rich[(k, 20)] > lean[(k, 20)]


def test_an_empty_surplus_distribution_raises():
    """A table built from nothing would silently price every FT at zero and
    turn the objective into 'always take the hit'."""
    with pytest.raises(ValueError):
        lambda_table([], weeks=10)


# --- the lookup ------------------------------------------------------------

def test_the_lookup_reads_the_table():
    lam = LambdaLookup({(1, 5): 2.0, (2, 5): 1.4})
    assert lam(1, 5) == 2.0 and lam(2, 5) == 1.4


def test_the_lookup_clamps_k_and_t_into_the_table():
    """A horizon can end past GW38 in a boundary week, and k can arrive as 0."""
    lam = LambdaLookup({(1, 1): 2.0, (1, 5): 3.0, (5, 5): 0.4})
    assert lam(1, 99) == 3.0        # clamped to the largest t present
    assert lam(9, 5) == 0.4         # clamped to the largest k present
    assert lam(0, 5) == 0.0         # holding zero transfers is worth zero


def test_the_lookup_on_an_empty_table_is_zero_everywhere():
    """The degradation path: no priors asset means no lambda pricing, and the
    caller falls back to flat ft_value."""
    assert LambdaLookup({})(2, 10) == 0.0
    assert LambdaLookup({}).empty is True


def test_the_lookup_reports_the_bank_value_of_holding_k_transfers():
    """The wildcard destroys a bank of FTs, and the sum of their lambdas is
    what it destroys."""
    lam = LambdaLookup({(1, 5): 2.0, (2, 5): 1.4, (3, 5): 1.0})
    assert abs(lam.bank_value(3, 5) - 4.4) < 1e-12
    assert lam.bank_value(0, 5) == 0.0
