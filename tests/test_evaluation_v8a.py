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
