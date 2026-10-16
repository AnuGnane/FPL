"""The top-bin ``p_play`` step, shipped off (holiday F-81, ROADMAP candidate 4).

A synthetic frame of three kinds of player, a minutes head fitted on it, and
stand-in heads for the rest, so ``predict_components_simple`` is read with
the flag off (exactly today's columns) and on (the step applied, monotone in
the raw and inside its bounds).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gaffer.models import minutes as minutes_mod
from gaffer.models import train
from gaffer.models.minutes import (
    STEP_BOUND,
    ThreeModeModel,
    apply_pplay_step,
    fit_pplay_step,
)

COLS = ["rate"]


def _frame(seasons: int = 3, gws: int = 12, players: int = 60,
           seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rate = np.resize([0.3, 0.6, 0.95], players)
    rows = []
    for s in range(seasons):
        for gw in range(1, gws + 1):
            for i in range(players):
                played = rng.random() < rate[i]
                rows.append({"code": i, "season_idx": s, "gw": gw,
                             "position": "MID", "team_code": 1,
                             "minutes": 90 if played else 0,
                             "starts": int(played), "rate": float(rate[i])})
    return pd.DataFrame(rows)


class _Head:
    def __init__(self, cols):
        self.cols = cols

    def predict(self, rows):
        return pd.DataFrame({c: np.full(len(rows), 0.1) for c in self.cols})


@pytest.fixture(scope="module")
def fitted():
    df = _frame()
    head = ThreeModeModel(COLS).fit(df)
    models = {"minutes": head,
              "attacking": _Head(["e_goals", "e_assists"]),
              "defcon": _Head(["p_defcon"]), "saves": _Head(["e_saves"]),
              "bonus": _Head(["e_bonus"])}
    return df, models, fit_pplay_step(df, COLS)


def test_the_step_is_monotone_in_the_raw_and_inside_its_bounds(fitted):
    _, _, step = fitted
    raw = np.linspace(0.0, 1.0, 201)
    out = step.predict(raw)
    assert np.all(np.diff(out) >= 0)
    assert out.min() >= STEP_BOUND and out.max() <= 1 - STEP_BOUND


def test_a_frame_of_one_season_has_no_step():
    assert fit_pplay_step(_frame(seasons=1), COLS) is None


def test_applying_the_step_caps_p60_at_the_stepped_p_play(fitted):
    df, models, step = fitted
    mp = models["minutes"].predict(df.head(30))
    out = apply_pplay_step(step, mp)
    assert (out["p60"] <= out["p_play"] + 1e-12).all()
    assert out["e_min"].equals(mp["e_min"])


def test_off_the_simple_path_is_todays_even_with_a_step_in_the_dict(
        fitted, monkeypatch):
    df, models, step = fitted
    monkeypatch.setattr(train, "PPLAY_TOP_BIN_STEP", False)
    rows = df.head(30)
    plain = train.predict_components_simple(models, rows)
    keyed = train.predict_components_simple({**models, "pplay_step": step},
                                            rows)
    pd.testing.assert_frame_equal(plain, keyed)
    raw = models["minutes"].predict(rows)["p_play"].to_numpy()
    np.testing.assert_array_equal(plain["p_play"].to_numpy(), raw)


def test_on_the_simple_path_applies_the_step(fitted, monkeypatch):
    df, models, step = fitted
    monkeypatch.setattr(train, "PPLAY_TOP_BIN_STEP", True)
    rows = df.head(30)
    out = train.predict_components_simple({**models, "pplay_step": step},
                                          rows)
    raw = models["minutes"].predict(rows)["p_play"].to_numpy()
    np.testing.assert_allclose(out["p_play"].to_numpy(), step.predict(raw))
    order = np.argsort(raw, kind="stable")
    assert np.all(np.diff(out["p_play"].to_numpy()[order]) >= 0)
    assert out["p_play"].between(STEP_BOUND, 1 - STEP_BOUND).all()


def test_the_flag_ships_off():
    assert train.PPLAY_TOP_BIN_STEP is False


def test_train_all_fits_a_step_only_when_on(monkeypatch):
    calls = []
    monkeypatch.setattr(train, "fit_pplay_step",
                        lambda df, cols: calls.append(cols) or "step")
    for name in ("build_team_model", "AttackingModel", "DefconModel",
                 "SavesModel", "BonusModel", "ThreeModeModel"):
        monkeypatch.setattr(train, name, lambda *a, **k: _Fits())
    monkeypatch.setattr(train, "bonus_season_floor", lambda df: 0)
    monkeypatch.setattr(train, "attacking_features", lambda: COLS)
    tg = pd.DataFrame({"elo_diff": [0.0]})
    monkeypatch.setattr(train, "PPLAY_TOP_BIN_STEP", False)
    off = train.train_all(_frame(seasons=2, gws=2, players=3), tg,
                          save=False, _fit_cal=False)
    assert "pplay_step" not in off and not calls
    monkeypatch.setattr(train, "PPLAY_TOP_BIN_STEP", True)
    on = train.train_all(_frame(seasons=2, gws=2, players=3), tg,
                         save=False, _fit_cal=False)
    assert on["pplay_step"] == "step" and calls == [train.MINUTES_FEATURES]


class _Fits:
    def fit(self, *_):
        return self


def test_the_reading_script_shares_the_models_definitions():
    import sys

    sys.path.insert(0, "scripts")
    import c2_pplay_bins

    assert c2_pplay_bins.STEP_BOUND is minutes_mod.STEP_BOUND
    assert c2_pplay_bins.out_of_fold is minutes_mod.out_of_fold
