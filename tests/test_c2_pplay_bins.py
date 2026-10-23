"""scripts/c2_pplay_bins.py, C2's reading on the minutes head (holiday F-17).

The verdict tests stub the minutes head with one that stretches a known
play rate towards the extremes, so its top bin is over-confident in every
season and an isotonic step fitted out of fold can only pull it back. One
test runs the real ``ThreeModeModel`` for the line's shape alone.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd
import pytest

from gaffer.data import store

sys.path.insert(0, "scripts")

import c2_pplay_bins


def _frame(seasons: int = 3, gws: int = 20, players: int = 300,
           seed: int = 0) -> pd.DataFrame:
    """Three kinds of player on a grid of true rates; each plays an exact
    share of every season's gameweeks in a random order. The share is exact
    per season, so the half-season holdout sits close to each rate rather
    than on it, well inside the bar's margins at this seed."""
    rng = np.random.default_rng(seed)
    rate = np.resize([0.35, 0.6, 0.9], players)
    rows = []
    for s in range(seasons):
        played = np.zeros((gws, players), dtype=bool)
        for i in range(players):
            played[rng.permutation(gws)[:round(rate[i] * gws)], i] = True
        for gw in range(1, gws + 1):
            for i in range(players):
                rows.append({"code": i, "season_idx": s, "gw": gw,
                             "minutes": 90 if played[gw - 1, i] else 0,
                             "starts": int(played[gw - 1, i]),
                             "rate": float(rate[i]),
                             "noise": float(rng.normal())})
    return pd.DataFrame(rows)


class _Stretched:
    """A stand-in head: ``p_play`` is the true rate pushed outwards in log
    odds, so a 0.9 regular reads about 0.99."""

    def __init__(self, cols, stretch: float = 2.0):
        self.stretch = stretch

    def fit(self, df):
        return self

    def predict(self, df):
        p = df["rate"].to_numpy()
        logit = np.log(p / (1 - p)) * self.stretch
        out = df[["code", "season_idx", "gw"]].copy()
        out["p_play"] = 1 / (1 + np.exp(-logit))
        return out


@pytest.fixture
def stretched(monkeypatch):
    monkeypatch.setattr(c2_pplay_bins, "ThreeModeModel", _Stretched)


def test_an_over_confident_top_bin_is_pulled_back_and_the_step_passes(
        stretched):
    out = c2_pplay_bins.pplay_reading(_frame(), feature_cols=["rate"])
    assert out["reason"] is None
    assert out["holdout_slots"] == 10 and out["oof_folds"] == 3
    assert out["n"] == 10 * 300 and out["n_train"] == 50 * 300
    top = out["bins"][-1]
    assert top["bin"] == "0.9-1.0" and top["n"] > 0
    assert top["raw"] - top["observed"] > 0.03
    assert abs(top["step"] - top["observed"]) < top["raw"] - top["observed"]
    assert out["raw"]["log_loss"] - out["step"]["log_loss"] >= 0.001
    assert out["step"]["brier"] < out["raw"]["brier"]
    assert sum(b["n"] for b in out["bins"]) == out["n"]
    assert out["verdict"] == "pass"


def test_a_calibrated_head_gains_nothing_and_fails_on_log_loss(
        monkeypatch):
    monkeypatch.setattr(c2_pplay_bins, "ThreeModeModel",
                        lambda cols: _Stretched(cols, stretch=1.0))
    out = c2_pplay_bins.pplay_reading(_frame(), feature_cols=["rate"])
    assert out["verdict"].startswith("fail: ")
    assert "log_loss" in out["verdict"]


def test_the_verdict_names_a_widening_bin():
    bins = [{"bin": "0.0-0.1", "n": 0, "raw": None, "step": None,
             "observed": None},
            {"bin": "0.8-0.9", "n": 50, "raw": 0.85, "step": 0.80,
             "observed": 0.86},
            {"bin": "0.9-1.0", "n": 50, "raw": 0.95, "step": 0.91,
             "observed": 0.91}]
    verdict, reason = c2_pplay_bins._verdict(0.30, 0.29, bins)
    assert verdict == "fail: bin_0.8-0.9" and reason is None


def test_one_training_season_has_no_step_and_says_why(stretched):
    out = c2_pplay_bins.pplay_reading(_frame(seasons=1, gws=20),
                                      feature_cols=["rate"])
    assert out["oof_folds"] == 0 and out["step"] is None
    assert out["raw"]["log_loss"] is not None
    assert out["verdict"] == "no reading"
    assert "out-of-fold" in out["reason"]


def test_the_real_minutes_head_prints_a_full_line():
    out = c2_pplay_bins.pplay_reading(_frame(players=60),
                                      feature_cols=["rate", "noise"])
    assert out["reason"] is None and out["oof_folds"] == 3
    assert len(out["bins"]) == 10
    assert sum(b["n"] for b in out["bins"]) == out["n"] == 600
    assert set(out["step"]) == {"log_loss", "brier", "at_bound"}


def test_too_few_slots_is_no_reading_with_its_reason():
    out = c2_pplay_bins.pplay_reading(_frame(seasons=1, gws=12),
                                      feature_cols=["rate"])
    assert out["n"] == 0 and out["verdict"] == "no reading"
    assert "too few gameweek slots" in out["reason"]


def test_a_missing_feature_frame_prints_the_line_not_a_traceback(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    assert c2_pplay_bins.main() == 0
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert line.startswith("C2_PPLAY ")
    payload = json.loads(line.removeprefix("C2_PPLAY "))
    assert payload["n"] == 0 and payload["verdict"] == "no reading"
    assert "missing" in payload["reason"]


def test_an_unreadable_feature_frame_prints_the_line_not_a_traceback(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    (tmp_path / "history").mkdir()
    (tmp_path / "history" / "player_gw.parquet").write_bytes(b"not parquet")
    assert c2_pplay_bins.main() == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1]
                         .removeprefix("C2_PPLAY "))
    assert payload["verdict"] == "no reading"
    assert payload["reason"].startswith("feature frame unreadable")


class _Recording(_Stretched):
    """``_Stretched`` that records the seasons and slots each fit saw and
    refuses to predict a season it was fitted on, outside the outer fit."""

    fits: list = []

    def fit(self, df):
        self.seen = set(df["season_idx"].unique())
        self.slots = set(zip(df["season_idx"], df["gw"]))
        _Recording.fits.append(self)
        return self

    def predict(self, df):
        self.predicted = set(df["season_idx"].unique())
        return super().predict(df)


def test_each_fold_predicts_a_season_it_never_fitted_on(monkeypatch):
    _Recording.fits = []
    monkeypatch.setattr(c2_pplay_bins, "ThreeModeModel", _Recording)
    c2_pplay_bins.pplay_reading(_frame(players=30), feature_cols=["rate"])
    outer, *folds = _Recording.fits
    assert max(outer.slots) == (2, 10)
    assert len(folds) == 3
    for fold in folds:
        assert fold.predicted.isdisjoint(fold.seen)


def test_a_holdout_across_a_season_boundary_is_fit_calibrations_last_ten_slots(
        stretched):
    df = _frame(seasons=3, gws=6, players=30)
    out = c2_pplay_bins.pplay_reading(df, feature_cols=["rate"])
    assert out["n_train"] == 8 * 30 and out["n"] == 10 * 30
    _, hold = c2_pplay_bins.split_holdout(df)
    slots = sorted(set(zip(df["season_idx"], df["gw"])))
    assert set(zip(hold["season_idx"], hold["gw"])) == set(slots[-10:])


def test_the_step_never_reaches_zero_or_one(stretched):
    out = c2_pplay_bins.pplay_reading(_frame(), feature_cols=["rate"])
    assert out["step"]["at_bound"] == 0
    assert all(c2_pplay_bins.STEP_BOUND <= b["step"]
               <= 1 - c2_pplay_bins.STEP_BOUND
               for b in out["bins"] if b["n"])
