"""scripts/v20c_head.py, the clip's head half on walk-forward folds (holiday F-13).

A synthetic two-season history of four clubs where one never scores and one
scores freely, so the unclipped fit leaves v19g's band and the clip bites.
"""

from __future__ import annotations

import json
import sys

import pandas as pd

from gaffer.data import store
from gaffer.models import dixon_coles
from gaffer.models.team import build_team_gw

sys.path.insert(0, "scripts")

import v20c_head  # noqa: E402 — scripts/ is not a package; the path insert must come first

# Club 4 never scores; club 1 scores freely; 2 and 3 are ordinary.
GOALS = {1: 4, 2: 1, 3: 1, 4: 0}
PAIRINGS = [((1, 2), (3, 4)), ((1, 3), (2, 4)), ((1, 4), (2, 3))]


def _fixtures(seasons: int = 2, gws: int = 38) -> pd.DataFrame:
    rows = []
    start = pd.Timestamp("2024-08-01", tz="UTC")
    for s in range(seasons):
        for gw in range(1, gws + 1):
            for home, away in PAIRINGS[gw % len(PAIRINGS)]:
                if gw % 2:
                    home, away = away, home
                rows.append({
                    "season_idx": s, "gw": gw,
                    "kickoff_time": start + pd.Timedelta(days=7 * (s * gws + gw)),
                    "home_code": home, "away_code": away,
                    # Varied by gw so the fit is not degenerate.
                    "home_goals": GOALS[home] + (gw % 3 == 0),
                    "away_goals": GOALS[away] + (gw % 5 == 0)})
    return pd.DataFrame(rows)


def test_the_clip_bites_on_the_extreme_club_and_the_line_is_scored():
    out = v20c_head.head_reading(build_team_gw(_fixtures()))
    # Three folds after the first: two seasons, two halves each.
    assert out["folds"] == 3 and out["n"] > 0
    assert out["n_extreme"] > 0 and out["clip_bit"] > 0
    for side in ("off", "on"):
        for subset in ("all", "extreme"):
            assert set(out[side][subset]) == {"logloss", "brier", "mae_egc"}
    assert out["verdict"] == "pass" or out["verdict"].startswith("fail: ")
    assert out["reason"] is None


def test_the_module_bound_is_restored_after_the_reading(monkeypatch):
    monkeypatch.setattr(dixon_coles, "MU_BOUNDS", (0.1, 9.0))
    v20c_head.head_reading(build_team_gw(_fixtures()))
    assert dixon_coles.MU_BOUNDS == (0.1, 9.0)


def test_the_off_side_matches_an_unclipped_predict():
    tg = build_team_gw(_fixtures())
    frame = v20c_head.fold_predictions(tg)
    played = tg.dropna(subset=["ga"])
    before = played[played["season_idx"] == 0]
    current = played[(played["season_idx"] == 1) & (played["gw"] <= 19)]
    model = dixon_coles.DixonColesModel().fit(before)
    ref = model.predict(current)
    fold = frame[frame["_fold"] == 2]
    assert fold["p_cs_off"].tolist() == ref["p_cs"].tolist()
    assert fold["e_gc_off"].tolist() == ref["e_gc"].tolist()


def test_a_history_with_one_fold_is_no_reading():
    out = v20c_head.head_reading(build_team_gw(_fixtures(seasons=1, gws=19)))
    assert out["n"] == 0 and out["verdict"] == "no reading"


def test_a_missing_history_prints_the_line_and_no_traceback(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    assert v20c_head.main() == 0
    payload = json.loads(capsys.readouterr().out.removeprefix("V20C_HEAD "))
    assert payload["n"] == 0 and "no fixture history" in payload["reason"]


def test_a_history_missing_a_column_prints_the_line_and_no_traceback(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    (tmp_path / "history").mkdir()
    _fixtures().drop(columns=["away_goals"]).to_parquet(
        tmp_path / v20c_head.HISTORY_PATH)
    assert v20c_head.main() == 0
    payload = json.loads(capsys.readouterr().out.removeprefix("V20C_HEAD "))
    assert payload["n"] == 0 and "unreadable" in payload["reason"]


def _frame(p_on_extreme: float, e_on_extreme: float) -> pd.DataFrame:
    # Row 0 is extreme unclipped (p_cs 0.99 on a match that conceded twice);
    # row 1 is ordinary and unmoved by the clip.
    return pd.DataFrame({"cs": [0.0, 1.0], "ga": [2.0, 0.0],
                         "p_cs_off": [0.99, 0.5], "e_gc_off": [0.01, 0.8],
                         "p_cs_on": [p_on_extreme, 0.5],
                         "e_gc_on": [e_on_extreme, 0.8], "_fold": [1, 1]})


def test_a_clip_that_helps_only_the_extreme_rows_passes(monkeypatch):
    monkeypatch.setattr(v20c_head, "fold_predictions",
                        lambda tg: _frame(0.80, 0.25))
    out = v20c_head.head_reading(build_team_gw(_fixtures(seasons=1)))
    assert out["n_extreme"] == 1 and out["clip_bit"] == 1
    assert out["verdict"] == "pass"


def test_a_clip_that_costs_the_goals_mean_fails_on_that_row(monkeypatch):
    monkeypatch.setattr(v20c_head, "fold_predictions",
                        lambda tg: _frame(0.80, 0.0))
    out = v20c_head.head_reading(build_team_gw(_fixtures(seasons=1)))
    assert out["verdict"] == "fail: overall_mae_egc"
