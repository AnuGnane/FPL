import random

import pandas as pd
from gaffer.models.train import (bonus_season_floor, evaluate_predictions,
                                 fit_calibration, train_all)
from gaffer.assets import load_bootstrap_sample
from gaffer.data.bootstrap import scoring_table
from gaffer.models.attacking import ATTACK_FEATURES
from gaffer.models.components import (BONUS_FEATURES, DEFCON_FEATURES,
                                      SAVES_FEATURES)
from gaffer.models.team import TEAM_FEATURES
from gaffer.models.train import MINUTES_FEATURES


def _frame(rows_by_season: dict[int, int], minutes: int = 90) -> pd.DataFrame:
    """Appearance rows per season_idx."""
    return pd.DataFrame([{"season_idx": s, "minutes": minutes}
                         for s, n in rows_by_season.items() for _ in range(n)])


def test_bonus_floor_reaches_back_a_season_when_the_newest_is_thin():
    # A brand-new season with one gameweek played cannot train a bonus model
    # on its own; the floor drops to include the season before it.
    df = _frame({3: 5000, 4: 100})
    assert bonus_season_floor(df) == 3


def test_bonus_floor_stays_on_the_newest_season_once_it_is_deep_enough():
    df = _frame({3: 5000, 4: 3000})
    assert bonus_season_floor(df) == 4


def test_bonus_floor_falls_back_to_the_oldest_season_on_a_tiny_frame():
    # Nothing clears the threshold — use everything rather than crash.
    df = _frame({1: 50, 2: 50})
    assert bonus_season_floor(df) == 1


def test_bonus_floor_counts_only_appearances():
    # 5000 rows in the newest season, but nobody played: they teach the bonus
    # model nothing, so the floor must still reach back.
    df = pd.concat([_frame({3: 5000}), _frame({4: 5000}, minutes=0)])
    assert bonus_season_floor(df) == 3


def test_evaluate_beats_worse_baseline():
    truth = pd.DataFrame({
        "code": [1, 2, 3, 4], "gw": [10] * 4,
        "total_points": [2.0, 6.0, 12.0, 0.0],
        "minutes": [90, 90, 90, 0],
    })
    good = pd.DataFrame({"code": [1, 2, 3, 4], "gw": [10] * 4,
                         "ep": [2.5, 5.0, 10.0, 0.5]})
    bad = pd.DataFrame({"code": [1, 2, 3, 4], "gw": [10] * 4,
                        "ep": [8.0, 1.0, 2.0, 6.0]})
    m_good = evaluate_predictions(good, truth)
    m_bad = evaluate_predictions(bad, truth)
    assert m_good["mae_starters"] < m_bad["mae_starters"]
    assert m_good["captain_pts"] >= m_bad["captain_pts"]


POSITIONS = ["GKP", "DEF", "MID", "FWD"]

_PLAYER_FEATURES = sorted(set(MINUTES_FEATURES) | set(ATTACK_FEATURES)
                          | set(DEFCON_FEATURES) | set(SAVES_FEATURES)
                          | set(BONUS_FEATURES))


def _player_frame(seasons=(0, 1), gws=8, players=24) -> pd.DataFrame:
    """Synthetic player-gameweek frame with every column train_all touches.

    Values are deterministic-random: the models only have to *fit*, not be
    any good, but each classifier needs both classes present.
    """
    rng = random.Random(11)
    rows = []
    for season in seasons:
        for gw in range(1, gws + 1):
            for p in range(players):
                pos = POSITIONS[p % 4]
                played = (p + gw) % 5 != 0
                minutes = rng.choice([60, 75, 90]) if played else 0
                row = {
                    "code": 1000 + p,
                    "element": 1000 + p,
                    "season_idx": season,
                    "gw": gw,
                    "position": pos,
                    "team_code": p % 6,
                    "minutes": minutes,
                    "goals": rng.choice([0, 0, 0, 1]) if played else 0,
                    "assists": rng.choice([0, 0, 0, 1]) if played else 0,
                    "saves": rng.randint(0, 5) if played and pos == "GKP" else 0,
                    "bonus": rng.choice([0, 0, 1, 3]) if played else 0,
                    "tackles": float(rng.randint(0, 8)),
                    "cbi": float(rng.randint(0, 9)),
                    "recoveries": float(rng.randint(0, 10)),
                    "yc_r38": 0.1,
                    "rc_r38": 0.01,
                    "total_points": rng.randint(0, 12) if played else 0,
                }
                for col in _PLAYER_FEATURES:
                    row.setdefault(col, rng.random() * 3)
                row["home"] = (p + gw) % 2
                row["minutes"] = minutes
                rows.append(row)
    return pd.DataFrame(rows)


def _team_frame(seasons=(0, 1), gws=8, teams=6) -> pd.DataFrame:
    rng = random.Random(23)
    rows = []
    for season in seasons:
        for gw in range(1, gws + 1):
            for t in range(teams):
                row = {"season_idx": season, "gw": gw, "code": t,
                       "opp_code": (t + 1) % teams,
                       "cs": (t + gw) % 2, "ga": rng.randint(0, 3)}
                for col in TEAM_FEATURES:
                    row.setdefault(col, rng.random() * 2)
                row["home"] = (t + gw) % 2
                rows.append(row)
    return pd.DataFrame(rows)


def test_train_all_fits_calibration_out_of_sample():
    models = train_all(_player_frame(), _team_frame(), save=False)
    assert "calibration" in models
    # A tiny synthetic holdout is below CalibrationModel.MIN_ROWS, so the
    # model is very likely unfitted (identity); the contract under test is
    # that it is present and that apply() works.
    ep = pd.Series([2.0, 4.0])
    pos = pd.Series(["MID", "FWD"])
    out = models["calibration"].apply(ep, pos)
    assert list(out.index) == [0, 1]
    assert len(out) == 2


def test_fit_calibration_on_a_single_season_is_unfitted():
    df = _player_frame(seasons=(0,))
    tg = _team_frame(seasons=(0,))
    cal = fit_calibration(df, tg, scoring_table(load_bootstrap_sample()))
    assert cal.by_pos == {}
