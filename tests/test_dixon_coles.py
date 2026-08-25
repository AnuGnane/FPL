import math

import numpy as np
import pandas as pd

from gaffer.models.dixon_coles import (GOAL_CAP, fixture_outcomes,
                                       scoreline_pmf, tau_correction)


def test_tau_correction_is_one_away_from_the_low_score_corner():
    assert tau_correction(2, 3, 1.4, 1.1, -0.1) == 1.0
    assert tau_correction(0, 2, 1.4, 1.1, -0.1) == 1.0


def test_tau_correction_matches_the_published_four_cases():
    lam, mu, rho = 1.4, 1.1, -0.12
    assert abs(tau_correction(0, 0, lam, mu, rho) - (1 - lam * mu * rho)) < 1e-12
    assert abs(tau_correction(0, 1, lam, mu, rho) - (1 + lam * rho)) < 1e-12
    assert abs(tau_correction(1, 0, lam, mu, rho) - (1 + mu * rho)) < 1e-12
    assert abs(tau_correction(1, 1, lam, mu, rho) - (1 - rho)) < 1e-12


def test_scoreline_pmf_sums_to_one():
    pmf = scoreline_pmf(1.6, 1.1, -0.12)
    assert abs(pmf.sum() - 1.0) < 1e-12
    assert pmf.shape == (GOAL_CAP + 1, GOAL_CAP + 1)


def test_scoreline_pmf_with_zero_rho_is_independent_poisson():
    pmf = scoreline_pmf(1.6, 1.1, 0.0)
    for x in (0, 1, 3):
        for y in (0, 2):
            want = (math.exp(-1.6) * 1.6 ** x / math.factorial(x)
                    * math.exp(-1.1) * 1.1 ** y / math.factorial(y))
            assert abs(pmf[x, y] - want) < 1e-6


def test_scoreline_pmf_negative_rho_lifts_the_nil_nil():
    """The correction exists because low-scoring scorelines are more common
    than independence implies; a negative rho is what buys that."""
    assert scoreline_pmf(1.4, 1.1, -0.12)[0, 0] > scoreline_pmf(1.4, 1.1, 0.0)[0, 0]


def test_scoreline_pmf_is_never_negative():
    for rho in (-0.4, -0.1, 0.0, 0.1, 0.4):
        assert (scoreline_pmf(0.4, 3.5, rho) >= 0.0).all()


def test_fixture_outcomes_clean_sheet_is_the_opponents_zero_column():
    out = fixture_outcomes(1.6, 1.1, -0.12)
    pmf = scoreline_pmf(1.6, 1.1, -0.12)
    assert abs(out["p_cs_home"] - pmf[:, 0].sum()) < 1e-12
    assert abs(out["p_cs_away"] - pmf[0, :].sum()) < 1e-12


def test_fixture_outcomes_expected_goals_conceded_matches_the_mean():
    out = fixture_outcomes(1.6, 1.1, 0.0)
    # With rho = 0 the marginals are Poisson, so E[GC] is the mu — up to the
    # mass truncated past GOAL_CAP, which is worth ~1e-5 of the mean at
    # Premier League scoring rates.
    assert abs(out["e_gc_home"] - 1.1) < 1e-4
    assert abs(out["e_gc_away"] - 1.6) < 1e-4


def test_fixture_outcomes_result_probabilities_sum_to_one():
    out = fixture_outcomes(1.6, 1.1, -0.12)
    total = out["p_home_win"] + out["p_draw"] + out["p_away_win"]
    assert abs(total - 1.0) < 1e-12


def test_fixture_outcomes_reports_the_two_goal_concession_band():
    """The -0.5/goal deduction only starts biting at two conceded, so the
    band is worth carrying out of the one coherent distribution."""
    out = fixture_outcomes(1.6, 1.1, -0.12)
    pmf = scoreline_pmf(1.6, 1.1, -0.12)
    assert abs(out["p_gc2_home"] - pmf[:, 2:].sum()) < 1e-12


def test_fixture_outcomes_stronger_side_has_the_better_clean_sheet():
    strong = fixture_outcomes(2.2, 0.6, -0.12)
    weak = fixture_outcomes(0.6, 2.2, -0.12)
    assert strong["p_cs_home"] > weak["p_cs_home"]
