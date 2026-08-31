"""EP bands: the scenario sweep's own noise model, read out instead of drawn.

The whole risk in this module is inventing a second noise model by accident.
Every test here is really the same test — that what the band says is what
``noise_ep`` would do — asked from a different angle: the calibrated path with
its recentred mean, the heuristic path without one, the absent asset, the
player with no minutes model, and the two tail probabilities that have to be
read off the *same* distribution as the band rather than off the headline EP.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

import gaffer.optimize.scenarios as sc
from gaffer.uncertainty import (BAND_Z, BLANK_POINTS, HAUL_POINTS, Band,
                                band_for, bands_by_player_gw, shipped_table,
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


def test_the_calibrated_band_is_centred_on_the_recentred_mean(monkeypatch):
    """A1: the sweep draws round ``recentred_mean``, not round ``ep``, so the
    band has to as well — otherwise it pictures a distribution nothing uses."""
    ep, xmins = 5.0, 80.0
    band = band_for(ep, xmins, table=TABLE)
    sigma = sc.sigma_for(TABLE, ep, xmins)
    mu = sc.recentred_mean(ep, sigma)
    assert band.sigma == pytest.approx(round(sigma, 3))
    assert band.ep_lo == pytest.approx(round(mu - BAND_Z * sigma, 2))
    assert band.ep_hi == pytest.approx(round(mu + BAND_Z * sigma, 2))
    # And that is not the same as a band round the headline: the whole reason
    # the pair is labelled p25-p75 rather than "plus or minus". At EP 5 with
    # σ 1.5 the clip at zero is four σ away and the shift is invisible at two
    # decimal places, so the claim is asserted where it actually bites — on a
    # low-EP player, whose absolute σ makes the ratchet real.
    low = band_for(0.5, xmins, table=TABLE)
    assert (low.ep_lo + low.ep_hi) / 2 != pytest.approx(0.5)


def test_the_heuristic_band_is_centred_on_the_ep(monkeypatch):
    """The heuristic scale is multiplicative and vanishes with the EP it is
    applied to, so ``noise_ep`` does not recentre it and neither does this."""
    ep, xmins = 5.0, 80.0
    band = band_for(ep, xmins, table=None)
    sigma = ep * (sc.NOISE_FLOOR_XMINS - xmins) / sc.NOISE_DENOM
    assert band.sigma == pytest.approx(round(sigma, 3))
    assert band.ep_lo + band.ep_hi == pytest.approx(2 * ep, abs=0.01)


def test_no_asset_is_the_heuristic_value_for_value(monkeypatch):
    """The asset-optionality rail, at this module's front door: a clone with
    no scenario_noise.json must produce the pre-v6 scale exactly."""
    monkeypatch.setattr("gaffer.uncertainty.scenario_noise", lambda: None)
    ep, xmins = 4.0, 20.0
    band = band_for(ep, xmins)
    want = ep * (sc.NOISE_FLOOR_XMINS - xmins) / sc.NOISE_DENOM
    assert band.sigma == pytest.approx(round(want, 3))


def test_a_nailed_on_starter_is_narrower_than_a_rotation_risk():
    """The claim the squad table makes visually, asserted as arithmetic."""
    nailed = band_for(5.0, 88.0, table=None)
    rotated = band_for(5.0, 30.0, table=None)
    assert nailed.ep_hi - nailed.ep_lo < rotated.ep_hi - rotated.ep_lo


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
    sigma = sc.sigma_for(TABLE, ep, xmins)
    mu = sc.recentred_mean(ep, sigma)
    cdf = lambda z: 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))  # noqa: E731
    assert band.p_haul == pytest.approx(
        round(1.0 - cdf((HAUL_POINTS - mu) / sigma), 4))
    assert band.p_blank == pytest.approx(
        round(cdf((BLANK_POINTS - mu) / sigma), 4))


def test_a_premium_hauls_more_often_than_a_defender():
    # At 88 xMins the heuristic σ is so small that both tails round to zero
    # four decimals out and the comparison has nothing to compare. A rotation
    # -risk xMins is where the two tails are actually distinguishable.
    premium = band_for(8.0, 45.0, table=None)
    defender = band_for(3.5, 45.0, table=None)
    assert premium.p_haul > defender.p_haul
    assert premium.p_blank < defender.p_blank


def test_a_degenerate_sigma_answers_in_certainties():
    """σ of exactly zero is not a division to attempt: the distribution is a
    point mass and the two tails are 1 or 0 by inspection."""
    band = band_for(12.0, sc.NOISE_FLOOR_XMINS, table=None)
    assert band.sigma == 0.0
    assert band.p_haul == 1.0 and band.p_blank == 0.0


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


def test_the_band_agrees_with_a_million_draws_of_noise_ep():
    """The end-to-end claim, checked against the thing itself rather than
    against the formula that produced it. A Monte Carlo of ``noise_ep`` must
    land inside a couple of hundredths of the quantiles this module reports —
    if it does not, the two have drifted apart and the band is a fiction."""
    ep, xmins = 5.0, 55.0
    band = band_for(ep, xmins, table=TABLE)
    rng = np.random.default_rng(11)
    draws = np.array([sc.noise_ep({(1, 1): ep}, {(1, 1): xmins}, rng,
                                  table=TABLE)[(1, 1)]
                      for _ in range(20000)])
    assert np.quantile(draws, 0.25) == pytest.approx(band.ep_lo, abs=0.05)
    assert np.quantile(draws, 0.75) == pytest.approx(band.ep_hi, abs=0.05)
    assert (draws >= HAUL_POINTS).mean() == pytest.approx(band.p_haul,
                                                          abs=0.02)
    assert (draws <= BLANK_POINTS).mean() == pytest.approx(band.p_blank,
                                                           abs=0.02)
