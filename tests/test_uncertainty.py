"""EP bands: what he might score, priced off outcome variance and forecast σ.

The whole risk in this module is shipping a number nobody looked at. v8g's
first cut drew the band off the *estimation* σ alone — how far gaffer's own
forecast of a player moves when the ensemble is reseeded — and that table is
two hundredths of a point wide over most of the pool. The bands came out
narrower than the rounding on the headline and every haul chip read 0% or
100%, which is a certainty claim about football.

So the distribution these tests pin is the one :func:`league_sim.
element_sigmas` already ships on the League tab: outcome variance
(:data:`OUTCOME_VAR_PER_EP` per point of EP — whether the goal goes in) plus
estimation variance in quadrature, recentred so the clipped draw still
averages the forecast. Every test is a way of asking whether the band answers
"what might he score" rather than "how precisely have I estimated him".
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

import gaffer.optimize.scenarios as sc
from gaffer.league_sim import OUTCOME_VAR_PER_EP
from gaffer.uncertainty import (BAND_Z, BLANK_POINTS, HAUL_POINTS, Band,
                                band_for, bands_by_player_gw,
                                estimation_sigma_for, shipped_table,
                                xmins_by_player_gw)

TABLE = {"ep_edges": [0.0, 2.0, 4.0, 6.0], "xmins_edges": [0.0, 30.0, 60.0],
         "sigma": {"2_2": 1.5}, "ep_marginal": {"2": 2.0}, "global": 3.0}


def test_no_xmins_is_no_band_at_all(monkeypatch):
    """A3. ``noise_ep`` passes such a cell through untouched, and a zero-width
    band would draw the least-known player as the most certain one."""
    assert band_for(5.0, None, table=TABLE) is None


@pytest.mark.parametrize("xmins", [float("nan"), "nonsense", None])
def test_an_unusable_xmins_is_no_band(xmins):
    assert band_for(5.0, xmins, table=TABLE) is None


def test_a_zero_ep_player_has_no_spread(monkeypatch):
    """``noise_ep`` leaves an EP of zero at zero: every clipped draw round it
    is non-negative, so any noise would invent points."""
    band = band_for(0.0, 80.0, table=TABLE)
    assert band == Band(sigma=0.0, ep_lo=0.0, ep_hi=0.0, p_haul=0.0,
                        p_blank=1.0)


def _total_sigma(ep: float, xmins: float, table: dict | None) -> float:
    """The quadrature the module is supposed to be doing, spelled out here so
    the tests never read it back off the implementation."""
    est = sc.sigma_for(table, ep, xmins)
    if est is None:
        est = ep * (sc.NOISE_FLOOR_XMINS - xmins) / sc.NOISE_DENOM
    return math.sqrt(OUTCOME_VAR_PER_EP * max(ep, 0.0) + max(est, 0.0) ** 2)


def test_the_band_prices_outcome_variance_not_only_forecast_error():
    """B1. The whole fix, as one line of arithmetic.

    The estimation term is real and stays in — but it is the small one, and a
    band built from it alone was narrower than the rounding on the headline it
    decorated.
    """
    ep, xmins = 5.0, 80.0
    band = band_for(ep, xmins, table=TABLE)
    assert band.sigma == pytest.approx(round(_total_sigma(ep, xmins, TABLE),
                                             3))
    # And it really is wider than the estimation σ on its own, by a lot: that
    # gap is the difference between "what might he score" and "how precisely
    # have I estimated him".
    assert band.sigma > 2 * sc.sigma_for(TABLE, ep, xmins)


def test_the_band_is_centred_on_the_recentred_mean():
    """The outcome σ is absolute, so the clip at zero pushes only upward and
    the centre shifts down to keep the draw averaging the forecast. That is
    why every label reads p25-p75 and never "plus or minus"."""
    ep, xmins = 5.0, 80.0
    band = band_for(ep, xmins, table=TABLE)
    sigma = _total_sigma(ep, xmins, TABLE)
    mu = sc.recentred_mean(ep, sigma)
    assert band.ep_lo == pytest.approx(round(mu - BAND_Z * sigma, 2))
    assert band.ep_hi == pytest.approx(round(mu + BAND_Z * sigma, 2))
    assert (band.ep_lo + band.ep_hi) / 2 < ep


def test_the_heuristic_arm_adds_the_same_outcome_term():
    """No asset is a different *estimation* term, never a different question:
    a clone with no scenario_noise.json still prices football."""
    ep, xmins = 5.0, 80.0
    band = band_for(ep, xmins, table=None)
    assert band.sigma == pytest.approx(round(_total_sigma(ep, xmins, None), 3))


def test_no_asset_is_the_heuristic_value_for_value(monkeypatch):
    """The asset-optionality rail, at this module's front door: a clone with
    no scenario_noise.json must fall back to the pre-v6 *estimation* scale
    exactly — which is now one term of two rather than the whole σ."""
    monkeypatch.setattr("gaffer.uncertainty.scenario_noise", lambda: None)
    ep, xmins = 4.0, 20.0
    band = band_for(ep, xmins)
    want = ep * (sc.NOISE_FLOOR_XMINS - xmins) / sc.NOISE_DENOM
    assert estimation_sigma_for(ep, xmins) == pytest.approx(want)
    assert band.sigma == pytest.approx(round(_total_sigma(ep, xmins, None), 3))


def test_at_equal_ep_the_shipped_band_barely_moves_with_xmins():
    """I2. The property the squad table used to claim, corrected.

    Post-B1 the band is dominated by ``OUTCOME_VAR_PER_EP * ep``, and the
    shipped σ table is neither monotone nor materially varying across xMins
    bins at a fixed EP (0.278 at 10 minutes against 0.257 at 88, on a σ of
    4.4). So xMins does **not** reach the band around the EP — it reaches it
    *through* the EP, because a rotation risk's expected points are lower in
    the first place. Asserting a width ordering at fixed EP on the shipped
    path would be asserting a fact about the calibration table that is not
    true, which is how the first cut of this feature shipped.
    """
    nailed = band_for(5.0, 88.0, table=sc.scenario_noise())
    rotated = band_for(5.0, 30.0, table=sc.scenario_noise())
    assert nailed.sigma == pytest.approx(rotated.sigma, abs=0.05)


def test_the_band_widens_with_the_forecast_it_brackets():
    """What xMins actually drives, on the shipped path: a rotation risk is a
    lower-EP player, and a lower EP is a narrower absolute band and a wider
    relative one."""
    table = sc.scenario_noise()
    small, big = band_for(2.0, 60.0, table=table), band_for(8.0, 60.0,
                                                           table=table)
    assert small.sigma < big.sigma
    assert (small.ep_hi - small.ep_lo) < (big.ep_hi - big.ep_lo)
    assert (small.ep_hi - small.ep_lo) / 2.0 > (big.ep_hi - big.ep_lo) / 8.0


def test_the_estimation_sigma_stays_available_on_its_own():
    """The decision line on the sensitivity card answers a different question
    — "how wrong might my forecast be" — and must keep the estimation σ
    unmixed with football's own variance."""
    assert estimation_sigma_for(5.0, 80.0, table=TABLE) == pytest.approx(
        sc.sigma_for(TABLE, 5.0, 80.0))
    assert estimation_sigma_for(5.0, None, table=TABLE) is None
    assert estimation_sigma_for(0.0, 80.0, table=TABLE) == 0.0
    assert estimation_sigma_for(5.0, 80.0, table=TABLE) < band_for(
        5.0, 80.0, table=TABLE).sigma


def test_the_band_never_goes_below_zero():
    """A negative floor on an expected-points band is not a worse player, it
    is an incoherent one.

    The calibrated path, because that is the only one where it can happen: the
    heuristic σ is a fraction of the EP it scales (at most 92/134 of it), so
    ``BAND_Z`` times it can never reach the EP itself. The absolute σ can, and
    on a 0.4-point player it does."""
    band = band_for(0.4, 5.0, table=TABLE)
    assert band.ep_lo == 0.0


def test_the_tails_are_read_off_the_same_distribution_as_the_band():
    ep, xmins = 6.0, 80.0
    band = band_for(ep, xmins, table=TABLE)
    sigma = _total_sigma(ep, xmins, TABLE)
    mu = sc.recentred_mean(ep, sigma)
    cdf = lambda z: 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))  # noqa: E731
    assert band.p_haul == pytest.approx(
        round(1.0 - cdf((HAUL_POINTS - mu) / sigma), 4))
    assert band.p_blank == pytest.approx(
        round(cdf((BLANK_POINTS - mu) / sigma), 4))


def test_a_mid_ep_players_chips_are_interior_probabilities():
    """B1's headline symptom, pinned. A five-point midfielder hauls sometimes
    and blanks sometimes; a model that answers 0.0000 and 1.0000 for him is
    not a cautious model, it is a broken one."""
    band = band_for(5.0, 80.0, table=sc.scenario_noise())
    for chip in (band.p_haul, band.p_blank):
        assert 0.02 < chip < 0.98, chip
    # And they are not each other's complement — they are two different tails
    # of one distribution with the bulk of the mass between them.
    assert band.p_haul + band.p_blank < 0.9


@pytest.mark.parametrize("ep", [0.6, 1.5, 4.0, 7.0, 12.0])
@pytest.mark.parametrize("xmins", [5.0, 45.0, 88.0, sc.NOISE_FLOOR_XMINS])
@pytest.mark.parametrize("table", [None, TABLE, "shipped"])
def test_no_real_forecast_is_ever_a_certainty(ep, xmins, table):
    """The certainty-claim ban.

    Any player the model expects more than half a point from can haul and can
    blank; neither tail is allowed to reach 0 or 1. That was false before B1
    on every nailed-on starter — the heuristic σ vanishes at 92 xMins, and a
    12-point captain came back as a *guaranteed* haul.
    """
    band = band_for(ep, xmins,
                    table=sc.scenario_noise() if table == "shipped" else table)
    assert band.sigma > 0.0
    assert band.p_haul < 1.0, band
    assert band.p_blank < 1.0, band
    assert band.ep_hi > band.ep_lo, band
    # A rounded 0.0000 is allowed and honest — a 0.6-point forward hauling is
    # a one-in-ten-thousand week and the chip says so. A rounded 1.0000 is
    # not: there is no player and no gameweek about which this tool may say
    # "certainly".
    assert band.p_haul != 1.0 and band.p_blank != 1.0


def test_a_premium_hauls_more_often_than_a_defender():
    premium = band_for(8.0, 45.0, table=None)
    defender = band_for(3.5, 45.0, table=None)
    assert premium.p_haul > defender.p_haul
    assert premium.p_blank < defender.p_blank


# --- the frame helper --------------------------------------------------

COMP = pd.DataFrame([
    {"code": 11, "gw": 5, "ep": 3.0, "p_play": 0.95, "p60": 0.9},
    {"code": 11, "gw": 5, "ep": 2.5, "p_play": 0.95, "p60": 0.9},
    {"code": 11, "gw": 6, "ep": 4.0, "p_play": 0.95, "p60": 0.9},
    {"code": 22, "gw": 5, "ep": 1.0, "p_play": 0.30, "p60": 0.2},
])


def test_a_double_gameweek_sums_its_ep_and_averages_its_xmins():
    """``xmins_by_player_gw``'s rule, which this must not contradict: xMins is
    a nailedness score and a nailed-on starter with two fixtures is exactly as
    nailed on as one with a single fixture."""
    bands = bands_by_player_gw(COMP, table=None)
    xm = xmins_by_player_gw(COMP)
    assert bands[(11, 5)] == band_for(5.5, xm[(11, 5)], table=None)
    assert (11, 6) in bands and (22, 5) in bands


def test_a_frame_with_no_minutes_model_bands_nothing():
    frame = COMP.drop(columns=["p_play", "p60"])
    assert bands_by_player_gw(frame, table=None) == {}


@pytest.mark.parametrize("frame", [
    pd.DataFrame(), pd.DataFrame({"code": [1]}), None])
def test_an_unusable_frame_bands_nothing(frame):
    assert bands_by_player_gw(frame, table=None) == {}


def test_the_shipped_table_is_the_one_the_sweep_serves(monkeypatch):
    """One seam, so a rail that pins the sweep's asset also pins the band's."""
    monkeypatch.setattr("gaffer.uncertainty.scenario_noise", lambda: TABLE)
    assert shipped_table() is TABLE


MC_DRAWS = 200_000
"""Draws in the cross-check below. Named, and named honestly: the test it
replaces claimed a million in its own title and drew twenty thousand."""


def test_the_band_agrees_with_two_hundred_thousand_clipped_draws():
    """The end-to-end claim, checked against sampling rather than against the
    formula that produced it.

    The distribution being sampled is the shipped one — outcome and estimation
    variance in quadrature, recentred, clipped at zero — so this catches an
    error in the quantile arithmetic, in the recentring, or in either tail. It
    also pins the property that recentring exists for: the draws average the
    forecast, not something a third of a point above it.

    Tolerances are relative to σ rather than absolute. Post-B1 σ is over four
    points, so the old ``abs=0.05`` on a quantile was asking sampling noise to
    be a hundredth of the width of the thing it was measuring; and the tails
    are order 0.2 rather than order 0.001, where a two-point absolute
    tolerance was vacuous.
    """
    ep, xmins = 5.0, 55.0
    band = band_for(ep, xmins, table=TABLE)
    sigma = _total_sigma(ep, xmins, TABLE)
    mu = sc.recentred_mean(ep, sigma)
    rng = np.random.default_rng(11)
    draws = np.maximum(0.0, mu + sigma * rng.standard_normal(MC_DRAWS))

    # Three standard errors of a quantile is ~0.01σ at this many draws; a
    # fiftieth of σ is that with room, and it is a claim about the band rather
    # than about the random seed.
    tol = sigma / 50.0
    assert np.quantile(draws, 0.25) == pytest.approx(band.ep_lo, abs=tol)
    assert np.quantile(draws, 0.75) == pytest.approx(band.ep_hi, abs=tol)
    assert draws.mean() == pytest.approx(ep, abs=tol)
    # Tails of order 0.2: a 5% *relative* tolerance is about 0.01 absolute,
    # roughly ten binomial standard errors.
    assert (draws >= HAUL_POINTS).mean() == pytest.approx(band.p_haul,
                                                          rel=0.05)
    assert (draws <= BLANK_POINTS).mean() == pytest.approx(band.p_blank,
                                                           rel=0.05)
    assert 0.05 < band.p_haul < 0.5 and 0.05 < band.p_blank < 0.5
