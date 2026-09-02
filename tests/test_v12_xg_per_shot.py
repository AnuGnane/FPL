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
                                      add_xg_per_shot,
                                      build_prediction_frame, feature_columns)


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


def test_a_nullable_column_still_gets_a_readable_indicator():
    """``Float64`` with ``pd.NA`` in it: ``np.isfinite`` over a masked array
    propagates the NA into the indicator, and an indicator that is itself
    missing tells LightGBM nothing about whether the 0.0 beside it was
    measured. Coerce to numpy float first."""
    frame = _frame([0.6], [4.0]).astype("Float64")
    frame.loc[0, "us_shots90_r5"] = pd.NA
    out = add_xg_per_shot(frame)
    assert out["us_npxg_per_shot_missing_r5"].iloc[0] == 1.0
    assert out["us_npxg_per_shot_r5"].iloc[0] == 0.0
    assert out["us_npxg_per_shot_missing_r3"].iloc[0] == 0.0


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


def _pred_hist() -> pd.DataFrame:
    """Two played matches for one forward, with Understat stats on them —
    ``tests/test_features.py::_us_rows`` plus the columns the prediction frame
    needs, which is the fixture the other build_prediction_frame tests use."""
    rows = pd.DataFrame([
        {"code": 1, "season_idx": 0, "gw": gw,
         "kickoff_time": f"2024-08-{10 + gw:02d}T14:00:00Z",
         "us_minutes": 90, "us_shots": shots, "us_key_passes": 1.0,
         "us_npxg": 0.6, "us_xgchain": 0.2, "us_xgbuildup": 0.1}
        for gw, shots in ((1, 4), (2, 2))])
    rows["position"] = "FWD"
    rows["team_code"] = 3
    rows["opp_code"] = 4
    rows["was_home"] = True
    rows["minutes"] = 90
    rows["goals"] = 1
    rows["assists"] = 0
    rows["starts"] = 1
    return rows


def _pred_future() -> pd.DataFrame:
    return pd.DataFrame([{"code": 1, "season_idx": 0, "gw": 3,
                          "position": "FWD", "team_code": 3, "opp_code": 4,
                          "was_home": True,
                          "kickoff_time": "2024-08-24T14:00:00Z"}])


def test_the_prediction_frame_builds_the_columns_too():
    """``attach_understat`` is the training path only. ``advise`` strips
    ``feature_columns()`` off the frame and re-derives through
    ``build_prediction_frame``, so a column built on one side and not the
    other is a serve-time KeyError."""
    out = build_prediction_frame(_pred_hist(), _pred_future())
    assert set(XG_PER_SHOT_FEATURES) <= set(out.columns)


def test_every_attacking_feature_exists_on_the_prediction_frame(monkeypatch):
    """With the arm on, ``AttackingModel.predict`` indexes the served frame by
    ``attacking_features()``; a name it cannot find raises before a single
    tree is walked. Scoped to the arm's own columns: this fixture passes no
    Elo frame, so ``team_elo`` and friends are legitimately absent from it and
    are the caller's job, not this feature's."""
    from gaffer.models import train as tr

    monkeypatch.setattr(tr, "xg_per_shot", lambda: True)
    out = build_prediction_frame(_pred_hist(), _pred_future())
    told = [c for c in tr.attacking_features() if c in XG_PER_SHOT_FEATURES]
    assert told == list(XG_PER_SHOT_FEATURES)
    assert [c for c in told if c not in out.columns] == []


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
