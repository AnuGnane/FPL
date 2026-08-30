"""v7b Q3: the composite sigma table, sqrt(sigma_est^2 + floor^2)."""

import math

import pytest

from gaffer.calibrate_noise import composite_table, write_noise
from gaffer.optimize import scenarios as sc

BASE = {
    "version": 1, "generated_at": "2026-08-30T00:00:00+00:00",
    "git_sha": "deadbee", "season": "2025-26", "source": "estimation",
    "ep_edges": [0.0, 2.0, 3.0, 4.0, 6.0],
    "xmins_edges": [0.0, 30.0, 60.0, 80.0],
    "sigma": {"0_0": 0.018, "1_1": 0.1396},
    "obs": {"0_0": 18310, "1_1": 900},
    "ep_marginal": {"0": 0.0252, "3": 0.2784},
    "ep_marginal_obs": {"0": 19982, "3": 1364},
    "global": 0.0692, "rows": 29338, "min_cell_obs": 100,
    "dropped_zero_cells": 0, "k": 5, "seeds": [7, 17, 27, 37, 47],
}


def test_every_sigma_is_the_quadrature_sum():
    out = composite_table(BASE, 0.6)
    assert out["sigma"]["0_0"] == pytest.approx(math.hypot(0.018, 0.6))
    assert out["sigma"]["1_1"] == pytest.approx(math.hypot(0.1396, 0.6))
    assert out["ep_marginal"]["3"] == pytest.approx(math.hypot(0.2784, 0.6))
    assert out["global"] == pytest.approx(math.hypot(0.0692, 0.6))


def test_everything_that_is_not_a_sigma_is_copied_untouched():
    out = composite_table(BASE, 0.6)
    for key in ("ep_edges", "xmins_edges", "obs", "ep_marginal_obs",
                "rows", "min_cell_obs", "season", "k", "seeds"):
        assert out[key] == BASE[key]
    assert out["composite_floor"] == 0.6
    assert out["derived_from"] == "estimation"


def test_the_source_stays_estimation_so_serving_does_not_refuse_it(monkeypatch):
    # scenario_noise() returns None for any other source, which would
    # silently demote a composite arm to the heuristic.
    out = composite_table(BASE, 1.0)
    assert out["source"] == "estimation"
    monkeypatch.setattr(sc, "load_scenario_noise", lambda: out)
    sc.scenario_noise.cache_clear()
    try:
        assert sc.scenario_noise() is out
    finally:
        sc.scenario_noise.cache_clear()


def test_a_zero_floor_is_the_identity_on_every_sigma():
    out = composite_table(BASE, 0.0)
    assert out["sigma"] == BASE["sigma"]
    assert out["ep_marginal"] == BASE["ep_marginal"]
    assert out["global"] == BASE["global"]


def test_the_input_payload_is_not_mutated():
    composite_table(BASE, 1.0)
    assert BASE["sigma"]["0_0"] == 0.018
    assert "composite_floor" not in BASE


def test_a_negative_floor_is_refused():
    with pytest.raises(ValueError, match="floor"):
        composite_table(BASE, -0.1)


def test_a_non_estimation_payload_is_refused():
    with pytest.raises(ValueError, match="estimation"):
        composite_table({**BASE, "source": "residual"}, 0.6)


def test_the_result_passes_the_asset_validator(tmp_path):
    dest = write_noise(composite_table(BASE, 1.0),
                       tmp_path / "composite.json")
    assert dest.exists()


def test_the_cli_writes_a_named_asset_per_floor(tmp_path, monkeypatch):
    import json
    import sys

    src = tmp_path / "est.json"
    src.write_text(json.dumps(BASE))
    sys.path.insert(0, "scripts")
    import v7b_composite

    monkeypatch.chdir(tmp_path)
    dest = v7b_composite.main([str(src), "0.6"])
    assert dest.name == "scenario_noise_composite_0.6.json"
    written = json.loads(dest.read_text())
    assert written["composite_floor"] == 0.6
    assert written["source"] == "estimation"
    assert written["sigma"]["0_0"] == pytest.approx(math.hypot(0.018, 0.6))
