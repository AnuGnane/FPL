"""§4.2: one bar, and it can say where it came from.

The headline test is the spec's own: with a priors asset present, no code path
reads the flat values. It is written as a *sentinel* rather than as a source
grep — both constants are monkeypatched to numbers no calibration could
produce, and any bar that comes back wearing one of them is a flat bar that
should have been θ.

The second half is the caption. A boolean would not do: there are three
distinct reasons a bar can be flat while an asset exists — the chip is not in
the table, the gameweek is outside the calibrated window, the caller passed no
lookup at all — and a UI that printed "flat fallback" for all three would be
telling a user to go and find an asset he already has.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.optimize import chips as chips_mod
from gaffer.optimize.chip_policy import (UNKNOWN_SOURCE,
                                         chip_thresholds_from_asset,
                                         flat_thresholds,
                                         threshold_with_source,
                                         thresholds_from_priors)
from gaffer.optimize.chips import wildcard_now_assessment
from gaffer.optimize.milp import SolveInput

SENTINEL_WC, SENTINEL_CHIP = 999.0, 998.0

CFG = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
           itb_value=0.05, hit_cost=4)


def _priors_covering_everything() -> dict:
    """A calibrated asset with a sample in every week of both chip windows,
    so no lookup has an excuse to fall through."""
    surplus = {str(gw): [3.0, 5.0, 7.0] for gw in range(1, 39)}
    return {"chip_surplus": {chip: dict(surplus)
                             for chip in ("wildcard", "bboost", "3xc",
                                          "freehit")}}


@pytest.fixture()
def sentinels(monkeypatch):
    """Both flat constants replaced by numbers a calibration cannot produce."""
    monkeypatch.setattr(chips_mod, "WILDCARD_RECOMMEND_THRESHOLD",
                        SENTINEL_WC)
    monkeypatch.setattr(chips_mod, "CHIP_PLAY_THRESHOLD", SENTINEL_CHIP)


def test_the_sentinels_reach_the_flat_lookup(sentinels):
    """The instrument first. ``flat_thresholds`` imports the constants inside
    its body, so the monkeypatch is only effective if it is read at call
    time — if this fails, every assertion below is vacuous."""
    flat = flat_thresholds()
    assert flat("wildcard", 7) == SENTINEL_WC
    assert flat("bboost", 7) == SENTINEL_CHIP


def test_with_an_asset_no_bar_is_ever_a_flat_value(sentinels):
    """Spec §4.2's test, over every chip and every gameweek of the season."""
    lookup = chip_thresholds_from_asset(_priors_covering_everything())
    for chip in ("wildcard", "bboost", "3xc", "freehit"):
        for gw in range(1, 39):
            bar, source = threshold_with_source(lookup, chip, gw)
            assert bar not in (SENTINEL_WC, SENTINEL_CHIP)
            assert source == "theta"


def test_a_missing_asset_is_flat_and_says_which_kind_of_flat():
    bar, source = threshold_with_source(chip_thresholds_from_asset(None),
                                        "bboost", 7)
    assert source == "flat: no calibrated priors asset"


def test_an_asset_with_no_usable_surplus_is_not_a_missing_asset():
    """T4-T7 review, Minor 7. Reaching the flat bars because there is no asset
    and reaching them because the asset is here and says nothing usable are
    different problems with different fixes — install it, or find out why
    calibration wrote nothing into it — and one caption sent both readers off
    to look for a file one of them already has.

    Both shapes of useless are covered: no ``chip_surplus`` key at all, and one
    whose every chip maps to nothing.
    """
    for priors in ({"ft_lambda": 1.0}, {"chip_surplus": {"bboost": {}}}):
        _, source = threshold_with_source(
            chip_thresholds_from_asset(priors), "bboost", 7)
        assert source == "flat: priors asset has no usable chip_surplus"


def test_the_default_flat_reason_is_still_the_absent_asset_one():
    """Every existing caller passes no reason and must keep the string it has
    always reported — including ``chip_policy.flat_thresholds()`` itself, the
    degradation rail the spec preserves."""
    _, source = threshold_with_source(flat_thresholds(), "wildcard", 3)
    assert source == "flat: no calibrated priors asset"


def test_a_chip_absent_from_the_asset_names_that_rather_than_the_asset():
    lookup = thresholds_from_priors({"bboost": {10: [4.0]}})
    _, source = threshold_with_source(lookup, "3xc", 10)
    assert source == "flat: no calibrated surplus for this chip"


def test_a_gameweek_outside_the_window_names_that():
    """``stopping_thresholds`` fills *every* week of ``[first_gw, last_gw]``,
    and ``thresholds_from_priors`` solves both halves, so a table built from a
    single sampled week still answers for all of GW1-38 — a gap in the
    calibration is missing information, not a missing key. The window fallback
    is therefore reached only by a gameweek the season does not have, which is
    exactly what an off-by-one in a caller's horizon looks like."""
    lookup = thresholds_from_priors({"bboost": {30: [4.0]}})
    assert threshold_with_source(lookup, "bboost", 1)[1] == "theta"
    bar, source = threshold_with_source(lookup, "bboost", 39)
    assert source == "flat: gameweek outside the calibrated window"
    assert bar is not None                  # the flat bar, whatever it is


def test_a_lookup_with_no_explain_is_unknown_and_never_raises():
    """A test's lambda, or an asset-built lookup from before v12."""
    bar, source = threshold_with_source(lambda chip, gw: 4.5, "bboost", 7)
    assert (bar, source) == (4.5, UNKNOWN_SOURCE)


# --- the wildcard verdict -------------------------------------------------

def _pool() -> pd.DataFrame:
    rows, code = [], 1
    for pos, n in [("GKP", 4), ("DEF", 9), ("MID", 10), ("FWD", 7)]:
        for i in range(n):
            rows.append({"code": code, "position": pos,
                         "team_code": (code % 6) + 1,
                         "cost": 40, "sell": 40,
                         "ep": {1: 1.0 + (code % 7) * 0.5}})
            code += 1
    return pd.DataFrame(rows)


def _state() -> SolveInput:
    return SolveInput(owned_codes=list(range(1, 16)), bank=200,
                      free_transfers=1, gws=[1])


def test_the_wildcard_verdict_reads_theta_when_it_is_handed_one(sentinels):
    """The bug this task exists for: with a priors asset in the run, the
    'Wildcard now' card used the flat 8.0 while the chip row above it used
    θ."""
    lookup = chip_thresholds_from_asset(_priors_covering_everything())
    out = wildcard_now_assessment(_pool(), _state(), thresholds=lookup, **CFG)
    assert out["threshold"] != SENTINEL_WC
    assert out["threshold_source"] == "theta"


def test_the_wildcard_verdict_with_no_lookup_is_the_shipped_one(sentinels):
    """The degradation rail: no lookup, the flat constant, and strictly
    greater — the comparison the function has always used."""
    out = wildcard_now_assessment(_pool(), _state(), **CFG)
    assert out["threshold"] == SENTINEL_WC
    assert out["threshold_source"].startswith("flat:")
    assert out["recommend"] is (out["gain_over_horizon"] > SENTINEL_WC)


def test_a_gain_exactly_on_theta_plays_the_wildcard():
    """``>=`` on the θ path, matching chip_plan and advise for every other
    chip. A wildcard that clears its bar exactly must not read differently
    from a bench boost that clears its bar exactly."""
    out = wildcard_now_assessment(
        _pool(), _state(),
        thresholds=lambda chip, gw: 0.0, **CFG)
    assert out["recommend"] is True
