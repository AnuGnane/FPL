"""scripts/v20b_head.py, the bonus head's head half (holiday F-15).

A synthetic three-season frame where a latent finishing skill, seen only by
the attacking head's column, drives goals and goals drive bonus. The control
reads only noise, so the branch's attacking columns carry the signal.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from gaffer.data import store

sys.path.insert(0, "scripts")

import v20b_head  # noqa: E402 — scripts/ is not a package; the path insert must come first

ATTACK = ["xg_r38"]


def _frame(seasons: int = 3, gws: int = 38, players: int = 120,
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
            bonus = np.clip(goals * 2, 0, 3)
            for i in range(players):
                rows.append({
                    "code": i, "season_idx": s, "gw": gw,
                    "position": positions[i], "minutes": int(minutes[i]),
                    "goals": int(goals[i]), "assists": 0,
                    "bonus": float(bonus[i]),
                    "xg_r38": float(skill[i] + rng.normal(0, 0.02)),
                    "home": int(rng.random() < 0.5),
                    "elo_diff": float(rng.normal(0, 50))})
    return pd.DataFrame(rows)


def test_the_branch_sees_the_attacking_signal_and_passes():
    out = v20b_head.head_reading(_frame(), attack_cols=ATTACK)
    assert out["reason"] is None
    assert out["holdout_slots"] == 10 and out["n"] > 0
    # Lever check: the branch carries the five extra columns.
    assert out["cols_branch"] == out["cols_main"] + 5
    # The held-out season's training part alone holds 2000 appearances, so
    # the bonus window is that one season and gets one out-of-fold refit.
    assert out["oof_folds"] == 1
    assert out["corr_egoals_ebonus"] > 0.5
    assert out["branch"]["corr"] - out["main"]["corr"] >= 0.05
    assert set(out["main"]["corr_by_position"]) == {"GKP", "DEF", "MID", "FWD"}
    assert out["verdict"] == "pass"


def test_a_branch_no_better_than_the_control_fails_on_overall_corr():
    # The control already reads the skill through one of its own eight
    # features, so the branch's attacking columns add nothing it lacks.
    df = _frame()
    df["bonus_r38"] = df["xg_r38"]
    out = v20b_head.head_reading(df, attack_cols=ATTACK)
    assert out["verdict"].startswith("fail: ")
    assert "overall_corr" in out["verdict"]


def test_the_verdict_names_a_falling_position_and_a_moved_level():
    main = {"corr": 0.30, "level": 0.0,
            "corr_by_position": {"GKP": None, "DEF": 0.20, "MID": 0.3,
                                 "FWD": 0.3}}
    branch = {"corr": 0.40, "level": 0.03,
              "corr_by_position": {"GKP": 0.1, "DEF": 0.17, "MID": 0.4,
                                   "FWD": 0.3}}
    verdict, reason = v20b_head._verdict(main, branch)
    assert verdict == "fail: corr_DEF, level" and reason is None


def test_a_position_the_branch_cannot_read_fails():
    side = {"corr": 0.30, "level": 0.0,
            "corr_by_position": {"GKP": None, "DEF": 0.2, "MID": 0.3,
                                 "FWD": 0.3}}
    branch = {**side, "corr": 0.40,
              "corr_by_position": {**side["corr_by_position"], "FWD": None}}
    assert v20b_head._verdict(side, branch)[0] == "fail: corr_FWD"


def test_too_few_slots_is_no_reading_with_its_reason():
    out = v20b_head.head_reading(_frame(seasons=1, gws=12), attack_cols=ATTACK)
    assert out["n"] == 0 and out["verdict"] == "no reading"
    assert "too few gameweek slots" in out["reason"]


def test_a_missing_feature_frame_prints_the_line_not_a_traceback(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    assert v20b_head.main() == 0
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert line.startswith("V20B_HEAD ")
    payload = json.loads(line.removeprefix("V20B_HEAD "))
    assert payload["n"] == 0 and payload["verdict"] == "no reading"
    assert "missing" in payload["reason"]


def test_an_unreadable_feature_frame_prints_the_line_not_a_traceback(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    (tmp_path / "history").mkdir()
    (tmp_path / "history" / "player_gw.parquet").write_bytes(b"not parquet")
    assert v20b_head.main() == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1]
                         .removeprefix("V20B_HEAD "))
    assert payload["verdict"] == "no reading"
    assert payload["reason"].startswith("feature frame unreadable")
