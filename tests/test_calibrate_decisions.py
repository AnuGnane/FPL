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


# --- the calibrator --------------------------------------------------------

import pandas as pd

from gaffer.calibrate_decisions import (PHASE_BOUNDS, best_single_transfer,
                                        phase_of, run_calibration,
                                        write_priors)


def test_phase_bounds_split_the_season_into_thirds():
    assert PHASE_BOUNDS == {"early": (1, 12), "mid": (13, 25),
                            "late": (26, 38)}


def test_phase_of_maps_a_gameweek_to_its_third():
    assert phase_of(1) == "early" and phase_of(12) == "early"
    assert phase_of(13) == "mid" and phase_of(25) == "mid"
    assert phase_of(26) == "late" and phase_of(38) == "late"


def test_phase_of_clamps_out_of_range_gameweeks():
    assert phase_of(0) == "early" and phase_of(99) == "late"


def test_best_single_transfer_is_the_gain_over_making_none():
    """The surplus the lambda DP consumes: what one free transfer buys."""
    from gaffer.optimize.milp import SolveInput
    from tests.test_milp import _owned_state
    from tests.test_v4c_degradation import GOLDEN_KW, golden_pool

    pool = golden_pool()
    state = _owned_state(pool)
    gain = best_single_transfer(pool, state, **GOLDEN_KW)
    assert gain >= 0.0


def test_best_single_transfer_of_a_perfect_squad_is_zero():
    """No upgrade available, no surplus. A negative number here would poison
    the DP with 'transfers are bad'."""
    from gaffer.optimize.milp import SolveInput
    from tests.test_v4c_degradation import GOLDEN_KW, golden_pool

    pool = golden_pool()
    best = pool.sort_values("code")
    by_pos = {}
    for r in best.itertuples():
        by_pos.setdefault(r.position, []).append(int(r.code))
    # Own the highest-EP legal 15 already.
    owned = (by_pos["GKP"][-2:] + by_pos["DEF"][-5:] + by_pos["MID"][-5:]
             + by_pos["FWD"][-3:])
    state = SolveInput(owned_codes=owned, bank=0, free_transfers=1, gws=[1])
    assert best_single_transfer(pool, state, **GOLDEN_KW) >= 0.0


def test_write_priors_round_trips_through_the_asset_schema(tmp_path):
    payload = {
        "version": 1, "generated_at": "2026-08-25T00:00:00Z",
        "seasons": ["2023-24"],
        "transfer_surplus": {"early": [1.0], "mid": [2.0], "late": [3.0]},
        "chip_surplus": {"wildcard": {"5": [4.0]}, "bboost": {},
                         "3xc": {}, "freehit": {}},
    }
    dest = tmp_path / "decision_priors.json"
    write_priors(payload, dest)
    import json
    assert json.loads(dest.read_text())["transfer_surplus"]["mid"] == [2.0]


def test_write_priors_refuses_a_payload_missing_a_required_key(tmp_path):
    """A half-written asset is worse than none: it would silently produce a
    lambda table from three samples."""
    with pytest.raises(ValueError) as exc:
        write_priors({"version": 1}, tmp_path / "x.json")
    assert "transfer_surplus" in str(exc.value)


def test_write_priors_refuses_an_empty_transfer_distribution(tmp_path):
    with pytest.raises(ValueError):
        write_priors({"version": 1, "generated_at": "x", "seasons": [],
                      "transfer_surplus": {"early": [], "mid": [], "late": []},
                      "chip_surplus": {}}, tmp_path / "x.json")


def test_run_calibration_produces_the_asset_schema(monkeypatch):
    """Driven off a stubbed weekly walk so the schema is tested without a
    multi-hour replay."""
    import gaffer.calibrate_decisions as cal

    def fake_walk(season, **kw):
        return ([{"gw": g, "surplus": 1.0 + g % 3} for g in range(1, 39)],
                [{"gw": g, "chip": c, "gain": 2.0}
                 for g in range(1, 39)
                 for c in ("wildcard", "bboost", "3xc", "freehit")])

    monkeypatch.setattr(cal, "walk_season", fake_walk)
    out = run_calibration(["2023-24", "2024-25"])
    assert out["version"] == 1
    assert out["seasons"] == ["2023-24", "2024-25"]
    assert len(out["transfer_surplus"]["early"]) == 24   # 12 gws x 2 seasons
    assert set(out["chip_surplus"]) == {"wildcard", "bboost", "3xc",
                                        "freehit"}
    assert out["chip_surplus"]["bboost"]["7"] == [2.0, 2.0]


def test_run_calibration_survives_a_season_that_cannot_be_replayed(
        monkeypatch):
    import gaffer.calibrate_decisions as cal

    def flaky(season, **kw):
        if season == "2023-24":
            raise RuntimeError("no history for that season")
        return ([{"gw": 5, "surplus": 2.0}], [])

    monkeypatch.setattr(cal, "walk_season", flaky)
    out = run_calibration(["2023-24", "2024-25"])
    assert out["seasons"] == ["2024-25"]
    assert out["transfer_surplus"]["early"] == [2.0]
