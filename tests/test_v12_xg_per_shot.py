"""Spec §3.5's feature: non-penalty xG per shot, per Understat window.

The spec writes it as ``us_npxg90 / us_shots90``. Neither column exists:
``add_understat_rolling`` produces ``us_npxg90_r{w}`` and ``us_shots90_r{w}``
for w in [3, 5, 10, 38] (engineer.py:857-879). Both are per-90 rates over the
*same* window, so their ratio is genuinely xG per shot at that window, and
there are four of them.

Zero with a missing indicator, per the spec, and the indicator is what makes
the zero readable: a player with no shots in the window has an undefined rate,
not a bad one, and LightGBM cannot tell a real 0.00 from a filled one without
being told.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from gaffer.features.engineer import (US_WINDOWS, XG_PER_SHOT_FEATURES,
                                      add_xg_per_shot, feature_columns)


def _frame(npxg, shots):
    cols = {}
    for w in US_WINDOWS:
        cols[f"us_npxg90_r{w}"] = npxg
        cols[f"us_shots90_r{w}"] = shots
    return pd.DataFrame(cols)


def test_the_ratio_is_built_for_every_understat_window():
    out = add_xg_per_shot(_frame([0.6], [4.0]))
    for w in US_WINDOWS:
        assert out[f"us_npxg_per_shot_r{w}"].iloc[0] == 0.15
        assert out[f"us_npxg_per_shot_missing_r{w}"].iloc[0] == 0.0


def test_no_shots_is_zero_with_the_indicator_raised():
    out = add_xg_per_shot(_frame([0.0], [0.0]))
    assert out["us_npxg_per_shot_r5"].iloc[0] == 0.0
    assert out["us_npxg_per_shot_missing_r5"].iloc[0] == 1.0


def test_a_null_window_is_missing_and_not_a_division_by_nothing():
    """A window with no minutes at all yields NaN from the rolling rate
    (engineer.py:912-913), which is 'we have no shot data', not 'no shots'."""
    out = add_xg_per_shot(_frame([np.nan], [np.nan]))
    assert out["us_npxg_per_shot_r5"].iloc[0] == 0.0
    assert out["us_npxg_per_shot_missing_r5"].iloc[0] == 1.0


def test_a_frame_with_no_understat_columns_still_gets_every_column():
    """The model's feature schema must not depend on whether the scrape ran —
    add_understat_rolling's own contract, inherited."""
    out = add_xg_per_shot(pd.DataFrame({"code": [1, 2]}))
    for col in XG_PER_SHOT_FEATURES:
        assert col in out.columns
        assert out[col].notna().all()


def test_the_columns_are_in_feature_columns_so_a_re_derive_strips_them():
    """``advise.py:548`` strips ``feature_columns()`` off the training frame
    before re-deriving; a column left behind would be a stale one."""
    cols = set(feature_columns())
    assert set(XG_PER_SHOT_FEATURES) <= cols


def test_the_attacking_model_is_told_only_when_the_flag_is_on(monkeypatch,
                                                              tmp_path):
    from gaffer.config import xg_per_shot
    from gaffer.models import train as tr

    off = tmp_path / "off.toml"
    off.write_text("[model]\nxg_per_shot = false\n")
    on = tmp_path / "on.toml"
    on.write_text("[model]\nxg_per_shot = true\n")
    assert xg_per_shot(off) is False
    assert xg_per_shot(on) is True

    monkeypatch.setattr(tr, "xg_per_shot", lambda: False)
    assert set(tr.attacking_features()) & set(XG_PER_SHOT_FEATURES) == set()
    monkeypatch.setattr(tr, "xg_per_shot", lambda: True)
    assert set(XG_PER_SHOT_FEATURES) <= set(tr.attacking_features())


def test_the_flag_defaults_off_and_survives_a_missing_file(tmp_path):
    from gaffer.config import xg_per_shot

    assert xg_per_shot(tmp_path / "nothing.toml") is False
    broken = tmp_path / "broken.toml"
    broken.write_text("[model\nxg_per_shot = true")
    assert xg_per_shot(broken) is False
