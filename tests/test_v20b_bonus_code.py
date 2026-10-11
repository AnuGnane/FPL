"""v20b's code, shipped off (holiday F-18; v20 spec §2 v20b "What").

``BONUS_SEES_ATTACK`` off is the pre-v20 head exactly: the same eight columns
and the same fit. On, the head reads thirteen columns, is fitted on
out-of-fold attacking output, and both prediction paths hand it the
attacking head's own ``e_goals``/``e_assists``. The frame is the head-half
script's shape: a finishing skill seen only through ``xg_r38`` drives goals,
and goals drive bonus.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gaffer.config import Config
from gaffer.models import components, train
from gaffer.models import predict as predict_mod
from gaffer.models.attacking import AttackingModel
from gaffer.models.components import (
    BONUS_ATTACK_FEATURES,
    BONUS_FEATURES,
    BonusModel,
)

ATTACK = ["xg_r38"]


def _frame(seasons: int = 3, gws: int = 6, players: int = 40,
           seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    positions = np.array(["GKP", "DEF", "MID", "FWD"] * (players // 4))
    skill = rng.uniform(0.0, 1.5, players) * (positions != "GKP")
    rows = []
    for s in range(seasons):
        for gw in range(1, gws + 1):
            goals = rng.poisson(skill)
            minutes = np.where(rng.random(players) < 0.9, 90, 0)
            goals = np.where(minutes > 0, goals, 0)
            for i in range(players):
                row = {"code": i, "season_idx": s, "gw": gw,
                       "team_code": i % 2,
                       "position": positions[i], "minutes": int(minutes[i]),
                       "goals": int(goals[i]), "assists": 0,
                       "bonus": float(min(goals[i] * 2, 3)),
                       "xg_r38": float(skill[i] + rng.normal(0, 0.02))}
                for col in BONUS_FEATURES:
                    row[col] = float(rng.normal())
                rows.append(row)
    return pd.DataFrame(rows)


@pytest.fixture
def arm_on(monkeypatch):
    monkeypatch.setattr(components, "BONUS_SEES_ATTACK", True)


def test_the_flag_ships_off():
    assert components.BONUS_SEES_ATTACK is False


def test_off_the_head_reads_the_eight_and_fits_as_before():
    df = _frame()
    head = BonusModel(min_season_idx=1).fit(df)
    old = BonusModel(feature_cols=BONUS_FEATURES, min_season_idx=1).fit(df)
    assert head.feature_cols == BONUS_FEATURES
    assert head.cols_ == BONUS_FEATURES
    assert np.array_equal(head.predict(df)["e_bonus"].to_numpy(),
                          old.predict(df)["e_bonus"].to_numpy())


def test_on_the_head_reads_thirteen_columns(arm_on):
    df = train.oof_attack(_frame(), 1, ATTACK)
    head = BonusModel(min_season_idx=1).fit(df)
    assert head.cols_ == BONUS_ATTACK_FEATURES
    assert len(head.cols_) == 13
    assert components.bonus_sees_attack(head)


def test_the_position_indicators_are_derived_with_gkp_the_base(arm_on):
    df = train.oof_attack(_frame(), 1, ATTACK)
    framed = BonusModel(min_season_idx=1)._frame(df)
    gk = framed["position"] == "GKP"
    assert (framed.loc[gk, ["pos_DEF", "pos_MID", "pos_FWD"]] == 0).all().all()
    assert (framed.loc[framed["position"] == "FWD", "pos_FWD"] == 1).all()
    assert "pos_DEF" not in df.columns   # the caller's frame is not touched


def test_oof_attack_predicts_each_window_season_from_the_others():
    df = _frame()
    out = train.oof_attack(df, 1, ATTACK)
    assert "e_goals" not in df.columns
    assert (out.loc[out["season_idx"] == 0, ["e_goals", "e_assists"]]
            == 0.0).all().all()
    for season in (1, 2):
        mask = df["season_idx"] == season
        want = (AttackingModel(ATTACK).fit(df[~mask]).predict(df[mask])
                ["e_goals"].to_numpy())
        assert np.allclose(out.loc[mask, "e_goals"].to_numpy(), want)


def test_oof_attack_leaves_a_lone_season_at_zero():
    df = _frame(seasons=1)
    out = train.oof_attack(df, 0, ATTACK)
    assert (out[["e_goals", "e_assists"]] == 0.0).all().all()


class _Stub:
    def __init__(self, **cols):
        self.cols = cols

    def fit(self, *a, **k):
        return self

    def predict(self, frame):
        return pd.DataFrame({c: [v] * len(frame)
                             for c, v in self.cols.items()})


class _Recorder:
    """A bonus head that records the frame it is handed."""

    def __init__(self, cols):
        self.cols_ = cols
        self.seen = None

    def predict(self, frame):
        self.seen = frame
        return pd.DataFrame({"e_bonus": [0.1] * len(frame)})


def _attacking_stub():
    class _Attack:
        def predict(self, frame):
            return pd.DataFrame({"e_goals": np.arange(len(frame)) * 0.1,
                                 "e_assists": np.arange(len(frame)) * 0.01})
    return _Attack()


def _simple_models(bonus):
    return {"minutes": _Stub(p_play=0.9, p60=0.8),
            "attacking": _attacking_stub(),
            "defcon": _Stub(p_defcon=0.5), "saves": _Stub(e_saves=1.0),
            "bonus": bonus}


def test_the_simple_path_hands_an_off_head_the_rows_untouched():
    rows = _frame(seasons=1, gws=1, players=4)
    bonus = _Recorder(BONUS_FEATURES)
    train.predict_components_simple(_simple_models(bonus), rows)
    assert "e_goals" not in bonus.seen.columns


def test_the_simple_path_hands_an_on_head_the_attacking_output():
    rows = _frame(seasons=1, gws=1, players=4)
    bonus = _Recorder(BONUS_ATTACK_FEATURES)
    comp = train.predict_components_simple(_simple_models(bonus), rows)
    assert np.allclose(bonus.seen["e_goals"].to_numpy(),
                       comp["e_goals"].to_numpy())
    assert np.allclose(bonus.seen["e_assists"].to_numpy(), [0, .01, .02, .03])


def _served(monkeypatch, bonus):
    keys = ("code", "season_idx", "gw", "opp_code")

    class _Keyed(_Stub):
        def predict(self, frame):
            out = super().predict(frame)
            for k in keys:
                if k in frame.columns:
                    out[k] = list(frame[k])
            return out

    models = {"minutes": _Keyed(p_play=0.9, p60=0.8, e_min=80.0),
              "team": _Keyed(p_cs=0.3, e_gc=1.2),
              "attacking": _attacking_stub(),
              "defcon": _Stub(p_defcon=0.5), "saves": _Stub(e_saves=1.0),
              "bonus": bonus}
    monkeypatch.setattr(predict_mod, "load_model", lambda name: models[name])
    monkeypatch.setattr(predict_mod, "attack_multipliers", lambda model: {})
    pred = pd.DataFrame({"code": [1, 2], "gw": [7, 7], "season_idx": [1, 1],
                         "team_code": [3, 4], "opp_code": [4, 3],
                         "position": ["MID", "DEF"], "home": [1, 0],
                         "was_home": [True, False],
                         "kickoff_time": ["x", "y"], "status": ["a", "a"],
                         "chance_of_playing": [100, 100]})
    team_future = pd.DataFrame({"code": [3, 4], "opp_code": [4, 3],
                                "gw": [7, 7], "season_idx": [1, 1],
                                "home": [1, 0]})
    players = pd.DataFrame({"code": [1, 2], "status": ["a", "a"],
                            "chance_of_playing": [100, 100]})
    return predict_mod.predict_components(pred, team_future, players,
                                         cfg=Config(entry_id=1, league_id=2))


def test_the_served_path_hands_an_off_head_the_rows_untouched(monkeypatch):
    bonus = _Recorder(BONUS_FEATURES)
    _served(monkeypatch, bonus)
    assert "e_goals" not in bonus.seen.columns


def test_the_served_path_hands_an_on_head_the_raw_attacking_output(
        monkeypatch):
    bonus = _Recorder(BONUS_ATTACK_FEATURES)
    _served(monkeypatch, bonus)
    assert np.allclose(bonus.seen["e_goals"].to_numpy(), [0.0, 0.1])
    assert np.allclose(bonus.seen["e_assists"].to_numpy(), [0.0, 0.01])


def _train_all(monkeypatch, df):
    for name in ("ThreeModeModel", "DefconModel", "SavesModel"):
        monkeypatch.setattr(train, name, lambda *a, **k: _Stub())
    monkeypatch.setattr(train, "build_team_model", lambda: _Stub())
    monkeypatch.setattr(train, "attacking_features", lambda: ATTACK)
    monkeypatch.setattr(train, "bonus_season_floor", lambda d: 1)
    tg = pd.DataFrame({"elo_diff": [0.0]})
    return train.train_all(df, tg, save=False, _fit_cal=False)


def test_train_all_off_fits_the_bonus_head_on_the_frame_itself(monkeypatch):
    df = _frame()
    models = _train_all(monkeypatch, df)
    want = BonusModel(min_season_idx=1).fit(df)
    assert models["bonus"].cols_ == BONUS_FEATURES
    assert np.array_equal(models["bonus"].predict(df)["e_bonus"].to_numpy(),
                          want.predict(df)["e_bonus"].to_numpy())


def test_train_all_on_fits_the_bonus_head_out_of_fold(monkeypatch, arm_on):
    df = _frame()
    models = _train_all(monkeypatch, df)
    want = BonusModel(min_season_idx=1).fit(train.oof_attack(df, 1, ATTACK))
    assert models["bonus"].cols_ == BONUS_ATTACK_FEATURES
    probe = train.oof_attack(df, 1, ATTACK)
    assert np.array_equal(
        models["bonus"].predict(probe)["e_bonus"].to_numpy(),
        want.predict(probe)["e_bonus"].to_numpy())
    assert "e_goals" not in df.columns
