"""Offline calibration of the scenario-noise σ table (spec §2).

No network and no training here: the expensive half (``residual_rows``) is
exercised by the orchestrator's real run, and everything this suite touches is
the arithmetic that turns residuals into an asset.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gaffer.calibrate_noise import (EP_EDGES, MIN_CELL_OBS, REQUIRED_KEYS,
                                    SIGMA_MAX, XMINS_EDGES, fit_sigmas,
                                    write_noise)

FIXTURE = Path(__file__).parent / "data" / "scenario_noise.json"


def _rows(n_per_cell: int = 200, seed: int = 0) -> pd.DataFrame:
    """Synthetic residuals: two EP bins x two xMins bins, with a deliberately
    thin cell that has to pool up to its EP marginal."""
    rng = np.random.default_rng(seed)
    rows = []
    for ep, x, sigma, n in ((1.0, 10.0, 3.0, n_per_cell),
                            (1.0, 85.0, 0.5, n_per_cell),
                            (5.0, 85.0, 4.0, n_per_cell),
                            (5.0, 10.0, 4.0, 5)):
        for _ in range(n):
            rows.append({"code": 1, "gw": 5, "ep": ep, "xmins": x,
                         "points": ep + float(rng.normal(0.0, sigma))})
    return pd.DataFrame(rows)


def test_fit_sigmas_fits_a_sigma_per_populated_cell():
    out = fit_sigmas(_rows())
    assert out["sigma"]["0_0"] == pytest.approx(3.0, abs=0.6)
    assert out["sigma"]["0_3"] == pytest.approx(0.5, abs=0.2)
    assert out["sigma"]["3_3"] == pytest.approx(4.0, abs=0.9)


def test_a_thin_cell_is_left_out_so_serving_pools_it_up():
    """Five observations is not a standard deviation. The cell is recorded in
    ``obs`` — the count is evidence — but not in ``sigma``, so
    ``sigma_for`` falls through to the EP marginal."""
    out = fit_sigmas(_rows())
    assert out["obs"]["3_0"] == 5
    assert "3_0" not in out["sigma"]
    assert "3" in out["ep_marginal"]


def test_the_nailedness_property_survives_the_fit():
    """The heuristic's whole purpose was that nailed players do not flip
    between sims. The table has to reproduce it from the data rather than be
    assumed to."""
    out = fit_sigmas(_rows())
    assert out["sigma"]["0_3"] < out["sigma"]["0_0"]


def test_the_global_sigma_is_always_there_as_the_last_resort():
    out = fit_sigmas(_rows())
    assert out["global"] > 0.0
    assert out["rows"] == len(_rows())


def test_fit_sigmas_carries_the_edges_it_was_fitted_on():
    out = fit_sigmas(_rows())
    assert out["ep_edges"] == EP_EDGES
    assert out["xmins_edges"] == XMINS_EDGES
    assert out["min_cell_obs"] == MIN_CELL_OBS


def test_the_top_xmins_bin_is_reachable_by_a_real_xmins_value():
    """``bin_index`` returns the largest edge a value clears, so an edge above
    what ``xmins_by_player_gw`` can produce leaves the last bin permanently
    empty. The live ceiling is ~84.8 — 85 was unreachable, 80 is where the
    nailed population actually sits."""
    from gaffer.calibrate_noise import bin_index

    assert XMINS_EDGES[-1] == 80.0
    assert bin_index(84.8, XMINS_EDGES) == len(XMINS_EDGES) - 1


def test_rows_with_no_xmins_are_dropped_rather_than_binned_at_zero():
    """A player with no minutes prediction is not a player expected to play
    zero minutes, and binning him as one would poison the 0-30 cell."""
    rows = _rows()
    rows.loc[:9, "xmins"] = float("nan")
    out = fit_sigmas(rows)
    assert out["rows"] == len(rows) - 10


# --- the asset writer -------------------------------------------------------

def _payload() -> dict:
    return json.loads(FIXTURE.read_text())


def test_write_noise_round_trips_the_fixture(tmp_path):
    dest = write_noise(_payload(), tmp_path / "scenario_noise.json")
    assert json.loads(dest.read_text())["sigma"]["0_0"] == 0.9


def test_write_noise_refuses_a_payload_missing_a_required_key(tmp_path):
    for key in REQUIRED_KEYS:
        payload = _payload()
        payload.pop(key)
        with pytest.raises(ValueError, match=key):
            write_noise(payload, tmp_path / "x.json")


def test_write_noise_refuses_a_non_finite_sigma(tmp_path):
    payload = _payload()
    payload["sigma"]["0_0"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        write_noise(payload, tmp_path / "x.json")


def test_write_noise_refuses_a_non_positive_sigma(tmp_path):
    payload = _payload()
    payload["sigma"]["0_0"] = 0.0
    with pytest.raises(ValueError, match="positive"):
        write_noise(payload, tmp_path / "x.json")


def test_write_noise_refuses_an_absurd_sigma(tmp_path):
    payload = _payload()
    payload["sigma"]["0_0"] = SIGMA_MAX + 1.0
    with pytest.raises(ValueError, match="below"):
        write_noise(payload, tmp_path / "x.json")


def test_write_noise_refuses_a_table_with_no_sigmas_at_all(tmp_path):
    """An empty table is worse than none: the loader would read it, find
    nothing, and fall through cell by cell for the whole sweep."""
    payload = _payload()
    payload["sigma"] = {}
    payload["ep_marginal"] = {}
    with pytest.raises(ValueError, match="no fitted"):
        write_noise(payload, tmp_path / "x.json")


def test_the_fixture_is_readable_by_the_serving_lookup():
    """The write side and the read side agree about the shape. This is the
    only place they meet before the orchestrator's real run."""
    from gaffer.optimize.scenarios import sigma_for

    table = _payload()
    assert sigma_for(table, 1.0, 10.0) == 0.9
    assert sigma_for(table, 4.5, 85.0) == 3.6
    assert sigma_for(table, 7.0, 85.0) == 4.8      # marginal
    assert sigma_for(table, 7.0, 20.0) == 4.8      # marginal again
