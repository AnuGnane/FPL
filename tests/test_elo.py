import pandas as pd

from gaffer.data.elo import compute_elo


def test_elo_winner_gains_loser_loses():
    fixtures = pd.DataFrame([
        {"season_idx": 0, "gw": 1, "kickoff_time": "2022-08-06T14:00:00Z",
         "home_code": 1, "away_code": 2, "home_goals": 3, "away_goals": 0},
    ])
    elo = compute_elo(fixtures)
    # pre-match ratings are recorded, both start at 1500
    pre = elo[(elo.code == 1) & (elo.gw == 1)]
    assert pre.iloc[0]["elo_pre"] == 1500
    assert elo.attrs["final"][1] > 1500 > elo.attrs["final"][2]


def test_elo_pre_is_prematch_not_postmatch():
    fixtures = pd.DataFrame([
        {"season_idx": 0, "gw": 1, "kickoff_time": "2022-08-06T14:00:00Z",
         "home_code": 1, "away_code": 2, "home_goals": 3, "away_goals": 0},
        {"season_idx": 0, "gw": 2, "kickoff_time": "2022-08-13T14:00:00Z",
         "home_code": 2, "away_code": 1, "home_goals": 0, "away_goals": 0},
    ])
    elo = compute_elo(fixtures)
    gw2_home = elo[(elo.code == 2) & (elo.gw == 2)].iloc[0]
    assert gw2_home["elo_pre"] < 1500        # team 2 lost gw1 before this match
