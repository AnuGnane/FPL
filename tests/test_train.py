import pandas as pd
from gaffer.models.train import bonus_season_floor, evaluate_predictions


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
