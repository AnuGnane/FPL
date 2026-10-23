"""scripts/c3_home_away.py, C3's home/away reading (holiday F-20).

A synthetic three-season frame where each player has a home scoring rate
and an unrelated away rate, and goals follow the rate closely. The control's
one rolling column is a noisy blend of the two, so only the branch's venue
splits can tell them apart.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from gaffer.data import store

sys.path.insert(0, "scripts")

import c3_home_away

ATTACK = ["xg_r10", "home"]


def _frame(seasons: int = 3, gws: int = 38, players: int = 120,
           seed: int = 0, same_rate: bool = False) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    positions = np.array(["GKP", "DEF", "MID", "FWD"] * (players // 4))
    rate_home = rng.uniform(0.0, 3.0, players)
    rate_away = rate_home if same_rate else rng.uniform(0.0, 3.0, players)
    rows = []
    for s in range(seasons):
        for gw in range(1, gws + 1):
            home = (np.arange(players) + gw) % 2
            rate = np.where(home == 1, rate_home, rate_away)
            minutes = np.where(rng.random(players) < 0.9, 90, 0)
            # Stochastic rounding rather than a Poisson draw: the rate stays
            # the larger part of a goal count's variance, so the test reads
            # the lever rather than the fit's noise.
            goals = np.where(minutes > 0,
                             np.floor(rate + rng.random(players)), 0)
            rows.extend(
                {
                    "code": i, "season_idx": s, "gw": gw,
                    "position": positions[i], "home": int(home[i]),
                    "minutes": int(minutes[i]), "goals": int(goals[i]),
                    "assists": 0, "xa": 0.0,
                    "total_points": int(2 * (minutes[i] > 0) + 4 * goals[i]),
                    "xg": float(rate[i] + rng.normal(0, 0.3))}
                for i in range(players))
    df = pd.DataFrame(rows).sort_values(["code", "season_idx", "gw"])
    # A noisy all-venue mean, as the engineered columns are: an exact
    # per-player constant would let the control's trees memorise each
    # player's venue rates through it and the home flag.
    df["xg_r10"] = (df.groupby("code")["xg"].shift(1)
                    .groupby(df["code"]).rolling(10, min_periods=1).mean()
                    .reset_index(level=0, drop=True))
    return df.reset_index(drop=True)


def test_a_rows_splits_read_only_its_earlier_matches_at_each_venue():
    df = pd.DataFrame({
        "code": [1] * 5, "season_idx": [0] * 5, "gw": [1, 2, 3, 4, 5],
        "home": [1, 0, 1, 0, 1], "xg": [1.0, 10.0, 3.0, 20.0, 5.0],
        "xa": 0.0, "goals": 0, "assists": 0})
    out = c3_home_away.add_venue_splits(df.sample(frac=1, random_state=0))
    assert out["gw"].tolist() == [1, 2, 3, 4, 5]
    home = out["xg_home_r5"].tolist()
    away = out["xg_away_r5"].tolist()
    assert np.isnan(home[0]) and home[1:] == [1.0, 1.0, 2.0, 2.0]
    assert np.isnan(away[0]) and np.isnan(away[1])
    assert away[2:] == [10.0, 10.0, 15.0]


def test_the_splits_stay_within_one_player():
    df = pd.DataFrame({
        "code": [1, 1, 2, 2], "season_idx": 0, "gw": [1, 2, 1, 2],
        "home": [1, 1, 1, 1], "xg": [4.0, 6.0, 100.0, 200.0],
        "xa": 0.0, "goals": 0, "assists": 0})
    out = c3_home_away.add_venue_splits(df)
    p2 = out[out["code"] == 2]["xg_home_r5"].tolist()
    assert np.isnan(p2[0]) and p2[1] == 100.0


def test_the_branch_reads_the_venue_rates_and_passes():
    out = c3_home_away.home_away_reading(_frame(), attack_cols=ATTACK)
    assert out["reason"] is None
    assert out["holdout_slots"] == 10 and out["n"] > 0
    assert out["cols_branch"] == out["cols_main"] + 8
    main, branch = out["main"], out["branch"]
    assert set(main) == {"all", "home", "away"}
    assert set(main["all"]) == set(c3_home_away.RETURN_CATEGORIES)
    assert (main["home"]["all"]["n"] + main["away"]["all"]["n"]
            == main["all"]["all"]["n"] == out["n"])
    assert (main["all"]["all"]["rmse"] - branch["all"]["all"]["rmse"]
            >= 0.002)
    assert out["verdict"] == "pass"


def test_splits_with_nothing_to_add_fail_on_overall_rmse():
    out = c3_home_away.home_away_reading(_frame(same_rate=True),
                                         attack_cols=ATTACK)
    assert out["verdict"].startswith("fail: ")
    assert "overall_rmse" in out["verdict"]


def _side(overall: float, buckets: dict[str, float | None]) -> dict:
    cats = {"all": {"rmse": overall, "n": 10}}
    cats.update({c: {"rmse": v, "n": 0 if v is None else 5}
                 for c, v in buckets.items()})
    return {"all": cats}


def test_the_verdict_names_a_bucket_that_rises_and_skips_an_empty_one():
    main = _side(1.000, {"zeros": 0.50, "blanks": 0.60, "tickers": 0.70,
                         "haulers": None})
    branch = _side(0.990, {"zeros": 0.51, "blanks": 0.604, "tickers": 0.60,
                           "haulers": 0.9})
    verdict, reason = c3_home_away._verdict(main, branch)
    assert verdict == "fail: rmse_zeros" and reason is None


def test_a_gain_just_short_of_the_bar_fails():
    flat = {"zeros": 0.5, "blanks": 0.5, "tickers": 0.5, "haulers": 0.5}
    verdict, _ = c3_home_away._verdict(_side(1.0, flat), _side(0.9985, flat))
    assert verdict == "fail: overall_rmse"


def test_too_few_slots_is_no_reading_with_its_reason():
    out = c3_home_away.home_away_reading(_frame(seasons=1, gws=12),
                                         attack_cols=ATTACK)
    assert out["n"] == 0 and out["verdict"] == "no reading"
    assert "too few gameweek slots" in out["reason"]


def test_a_missing_feature_frame_prints_the_line_not_a_traceback(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    assert c3_home_away.main() == 0
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert line.startswith("C3_HOME_AWAY ")
    payload = json.loads(line.removeprefix("C3_HOME_AWAY "))
    assert payload["n"] == 0 and payload["verdict"] == "no reading"
    assert "missing" in payload["reason"]


def test_an_unreadable_feature_frame_prints_the_line_not_a_traceback(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    (tmp_path / "history").mkdir()
    (tmp_path / "history" / "player_gw.parquet").write_bytes(b"not parquet")
    assert c3_home_away.main() == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1]
                         .removeprefix("C3_HOME_AWAY "))
    assert payload["verdict"] == "no reading"
    assert payload["reason"].startswith("feature frame unreadable")
