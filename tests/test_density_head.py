"""scripts/density_head.py, ``density_pub_7d``'s head half (holiday F-32).

A synthetic three-season frame where a player plays almost always in a quiet
week and about half the time in a congested one, so fixture density is the
signal and the control's one column is flat. The real ``ThreeModeModel``
fits both sides; the frames are small enough to keep the file quick.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from gaffer.data import store
from gaffer.features.engineer import DENSITY_FEATURES
from gaffer.models.train import MINUTES_FEATURES

sys.path.insert(0, "scripts")

import density_head

CONTROL = ["flat"]
"""A constant: the control can learn the base rate and nothing else, so a
noise column's per-row overfit cannot swamp the lever."""


def _frame(seasons: int = 3, gws: int = 20, players: int = 60, seed: int = 0,
           signal: bool = True, congested_share: float = 0.4) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(seasons):
        for gw in range(1, gws + 1):
            dens = np.where(rng.random(players) < congested_share, 2, 1)
            rate = np.where((dens >= 2) & signal, 0.5, 0.95)
            played = rng.random(players) < rate
            rows.extend(
                {"code": i, "season_idx": s, "gw": gw,
                 "minutes": 90 if played[i] else 0,
                 "starts": int(played[i]),
                 "flat": 0.0,
                 "density_pub_7d": float(dens[i]),
                 "density_pub_missing": 0}
                for i in range(players))
    return pd.DataFrame(rows)


def test_the_density_columns_are_the_two_the_engineer_builds():
    assert density_head.DENSITY_FEATURES == ["density_pub_7d",
                                             "density_pub_missing"]
    assert not set(DENSITY_FEATURES) & set(MINUTES_FEATURES)


def test_the_default_branch_is_the_control_plus_both_density_columns(monkeypatch):
    seen = []

    class _Head:
        def __init__(self, cols):
            seen.append(list(cols))

        def fit(self, df):
            return self

        def predict(self, df):
            out = df[["code", "season_idx", "gw"]].copy()
            out["p_play"], out["e_min"] = 0.8, 70.0
            return out

    monkeypatch.setattr(density_head, "ThreeModeModel", _Head)
    df = _frame(players=10)
    for col in MINUTES_FEATURES:
        df[col] = 0.0
    out = density_head.density_reading(df)
    assert seen == [MINUTES_FEATURES, MINUTES_FEATURES + DENSITY_FEATURES]
    assert out["branch_cols"] == MINUTES_FEATURES + DENSITY_FEATURES
    assert "density_pub_7d" in out["branch_cols"]
    assert "density_pub_7d" not in out["control_cols"]


def test_density_that_carries_the_signal_passes():
    out = density_head.density_reading(
        _frame(), control_cols=CONTROL,
        branch_cols=CONTROL + DENSITY_FEATURES)
    assert out["reason"] is None
    assert out["n"] == 10 * 60 and out["n_train"] == 50 * 60
    assert 0 < out["n_congested"] < out["n"]
    gain = out["control"]["all"]["log_loss"] - out["branch"]["all"]["log_loss"]
    assert gain >= density_head.LOG_GAIN
    assert (out["branch"]["congested"]["log_loss"]
            <= out["control"]["congested"]["log_loss"])
    assert out["verdict"] == "pass"


def test_density_that_carries_nothing_fails_on_log_loss():
    out = density_head.density_reading(
        _frame(signal=False), control_cols=CONTROL,
        branch_cols=CONTROL + DENSITY_FEATURES)
    assert out["verdict"].startswith("fail: ")
    assert "log_loss" in out["verdict"]


def test_the_congested_subset_is_density_at_or_above_two():
    rows = pd.DataFrame({"density_pub_7d": [0.0, 1.0, 2.0, 3.0, np.nan]})
    assert density_head.congested(rows).tolist() == [False, False, True,
                                                     True, False]


def test_a_holdout_with_no_congested_row_is_no_reading_with_its_reason():
    out = density_head.density_reading(
        _frame(congested_share=0.0, players=20), control_cols=CONTROL,
        branch_cols=CONTROL + DENSITY_FEATURES)
    assert out["n_congested"] == 0 and out["verdict"] == "no reading"
    assert "density_pub_7d >= 2" in out["reason"]
    assert out["control"]["congested"]["log_loss"] is None


def test_the_verdict_fails_a_worse_congested_subset_even_with_an_overall_gain():
    control = {"all": {"log_loss": 0.30}, "congested": {"log_loss": 0.40}}
    branch = {"all": {"log_loss": 0.29}, "congested": {"log_loss": 0.41}}
    assert density_head._verdict(control, branch) == ("fail: congested", None)


def test_the_line_carries_its_keys():
    out = density_head.density_reading(
        _frame(players=20), control_cols=CONTROL,
        branch_cols=CONTROL + DENSITY_FEATURES)
    assert set(out) == {"n", "n_train", "n_congested", "holdout_slots",
                        "control_cols", "branch_cols", "control", "branch",
                        "verdict", "reason"}
    for side in ("control", "branch"):
        assert set(out[side]) == {"all", "congested"}
        assert set(out[side]["all"]) == {"log_loss", "brier", "mae_min"}
    assert set(out) == set(density_head._empty("x"))


def test_a_frame_without_the_density_columns_is_no_reading():
    df = _frame(players=10).drop(columns=["density_pub_missing"])
    out = density_head.density_reading(df, control_cols=CONTROL)
    assert out["n"] == 0 and out["verdict"] == "no reading"
    assert "density_pub_missing" in out["reason"]


def test_too_few_slots_is_no_reading_with_its_reason():
    out = density_head.density_reading(_frame(seasons=1, gws=12, players=10),
                                       control_cols=CONTROL)
    assert out["n"] == 0 and "too few gameweek slots" in out["reason"]


def test_a_missing_feature_frame_prints_the_line_not_a_traceback(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    assert density_head.main() == 0
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert line.startswith("DENSITY_HEAD ")
    payload = json.loads(line.removeprefix("DENSITY_HEAD "))
    assert payload["n"] == 0 and payload["verdict"] == "no reading"
    assert "missing" in payload["reason"]


def test_an_unreadable_feature_frame_prints_the_line_not_a_traceback(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    (tmp_path / "history").mkdir()
    (tmp_path / "history" / "player_gw.parquet").write_bytes(b"not parquet")
    assert density_head.main() == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1]
                         .removeprefix("DENSITY_HEAD "))
    assert payload["verdict"] == "no reading"
    assert payload["reason"].startswith("feature frame unreadable")
