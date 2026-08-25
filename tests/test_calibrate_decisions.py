import json

import pytest

from gaffer.assets import (DECISION_PRIORS, decision_priors_exist,
                           load_decision_priors)


def test_the_asset_is_shipped_in_the_package():
    assert decision_priors_exist() is True


def test_the_asset_has_the_documented_schema():
    priors = load_decision_priors()
    assert set(priors) >= {"version", "seasons", "transfer_surplus",
                           "chip_surplus"}
    assert priors["version"] == 1


def test_transfer_surplus_is_keyed_by_season_phase():
    priors = load_decision_priors()
    assert set(priors["transfer_surplus"]) == {"early", "mid", "late"}
    for samples in priors["transfer_surplus"].values():
        assert isinstance(samples, list)


def test_chip_surplus_is_keyed_by_chip_then_by_gameweek_string():
    priors = load_decision_priors()
    assert set(priors["chip_surplus"]) == {"wildcard", "bboost", "3xc",
                                           "freehit"}
    for by_gw in priors["chip_surplus"].values():
        assert isinstance(by_gw, dict)
        for key in by_gw:
            assert key.isdigit(), key


def test_the_asset_is_valid_json_on_disk():
    from importlib.resources import files

    raw = files("gaffer.assets").joinpath(DECISION_PRIORS).read_text()
    assert isinstance(json.loads(raw), dict)


def test_loading_when_the_asset_is_absent_returns_none(monkeypatch):
    """The whole degradation rail for lambda and theta hangs off this."""
    import gaffer.assets as assets_mod

    monkeypatch.setattr(assets_mod, "DECISION_PRIORS", "not-a-file.json")
    assert assets_mod.decision_priors_exist() is False
    assert assets_mod.load_decision_priors() is None


# --- what the two consumers do with an absent asset ------------------------

def test_lambda_from_absent_priors_is_an_empty_lookup():
    from gaffer.optimize.ft_value import lambda_from_priors

    lam = lambda_from_priors(None)
    assert lam.empty is True
    assert lam(2, 20) == 0.0


def test_lambda_from_priors_with_no_samples_is_also_empty():
    from gaffer.optimize.ft_value import lambda_from_priors

    assert lambda_from_priors(
        {"transfer_surplus": {"early": [], "mid": [], "late": []}}).empty


def test_lambda_from_priors_builds_a_table_from_real_samples():
    from gaffer.optimize.ft_value import lambda_from_priors

    lam = lambda_from_priors(
        {"transfer_surplus": {"early": [0.5, 2.0, 5.0],
                              "mid": [0.5, 2.0], "late": [1.0]}})
    assert lam.empty is False
    assert lam(1, 30) > lam(5, 30)
    assert lam(2, 30) > lam(2, 3)


def test_thresholds_from_absent_priors_are_the_flat_constants():
    from gaffer.optimize.chip_policy import thresholds_from_priors
    from gaffer.optimize.chips import CHIP_PLAY_THRESHOLD

    from gaffer.optimize.chip_policy import chip_thresholds_from_asset

    lookup = chip_thresholds_from_asset(None)
    assert lookup("bboost", 7) == CHIP_PLAY_THRESHOLD


def test_thresholds_from_a_real_asset_vary_by_week():
    from gaffer.optimize.chip_policy import chip_thresholds_from_asset

    lookup = chip_thresholds_from_asset(
        {"chip_surplus": {"bboost": {str(t): [3.0, 9.0]
                                     for t in range(1, 39)}}})
    assert lookup("bboost", 5) > lookup("bboost", 18)
    assert lookup("bboost", 19) == 0.0
