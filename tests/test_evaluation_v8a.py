"""F3: the trichotomy made legible to the measurement layer.

Zeros RMSE says an arm helped. It does not say *where* — whether P(start)
sharpened or the points model absorbed the change downstream. These readouts
are what make every G1 arm's effect attributable at the mode level.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from gaffer.evaluation import start_truth


def test_the_start_truth_prefers_the_recorded_starts_column():
    hold = pd.DataFrame({"starts": [1.0, 0.0, 1.0], "minutes": [90, 20, 5]})
    assert list(start_truth(hold)) == [1.0, 0.0, 1.0]


def test_a_season_without_starts_falls_back_to_the_sixty_minute_rule():
    """``starts`` predates part of the archive. A hole there would blank the
    metric for a whole season, and 60+ minutes is a start in all but a
    handful of cases — the same inference ``_mode_rate_parts`` makes."""
    hold = pd.DataFrame({"minutes": [90.0, 20.0, 61.0]})
    assert list(start_truth(hold)) == [1.0, 0.0, 1.0]


def test_a_missing_start_is_filled_from_the_minutes_row_by_row():
    hold = pd.DataFrame({"starts": [1.0, np.nan, np.nan],
                         "minutes": [90.0, 90.0, 10.0]})
    assert list(start_truth(hold)) == [1.0, 1.0, 0.0]


def test_the_head_block_names_p_start(monkeypatch):
    """``evaluate_current`` is a full refit and far too slow for a unit test,
    so the contract asserted here is the source's: the heads block scores the
    mode probability, not another function of p_play."""
    import inspect

    from gaffer.evaluation import evaluate_current

    src = inspect.getsource(evaluate_current)
    assert 'predict_modes(hold)' in src
    assert '"p_start": head_metrics(' in src
    assert 'start_truth(hold)' in src


# --- the zeros diagnostic's mode cut ---------------------------------------

from gaffer.zeros_diagnostic import (start_reliability,  # noqa: E402
                                     format_diagnostic, zeros_report)


def _scored() -> pd.DataFrame:
    rng = np.random.default_rng(5)
    n = 200
    p = rng.uniform(0.0, 1.0, n)
    return pd.DataFrame({
        "code": np.arange(n), "gw": 10,
        "ep": p * 4.0, "total_points": (rng.uniform(size=n) < p) * 5.0,
        "minutes": (rng.uniform(size=n) < p) * 90.0,
        "starts": (rng.uniform(size=n) < p).astype(float),
        "season_start_share": rng.uniform(size=n),
        "minutes_r5": rng.uniform(size=n) * 90.0,
        "p_dnp": 1.0 - p, "p_start": p})


def test_the_curve_reports_predicted_against_observed_per_bin():
    out = start_reliability(_scored())
    assert out and all({"decile", "n", "pred", "obs"} <= set(r) for r in out)
    assert all(0.0 <= r["pred"] <= 1.0 for r in out)


def test_a_frame_without_the_mode_probability_reports_no_curve():
    assert start_reliability(_scored().drop(columns=["p_start"])) == []


def test_every_stratum_carries_its_own_curve():
    payload = zeros_report(_scored())
    assert set(payload["start_reliability"]) == set(payload["strata"]) - {
        "flagged"}


def test_the_printed_report_names_the_start_curve():
    payload = zeros_report(_scored())
    payload["run_at"], payload["git_sha"] = "now", "abc"
    text = format_diagnostic(payload)
    assert "p_start calibration" in text
