import pandas as pd
from gaffer.advise import future_fixture_frame, chips_available_for


def test_future_fixture_frame_one_row_per_player_fixture():
    fixtures = pd.DataFrame([
        {"gw": 2, "home_id": 1, "away_id": 2, "kickoff_time": "2026-08-28T19:00:00Z"},
        {"gw": 3, "home_id": 2, "away_id": 1, "kickoff_time": "2026-09-04T19:00:00Z"},
    ])
    players = pd.DataFrame([
        {"code": 10, "element": 5, "name": "A", "position": "MID",
         "team_id": 1, "team_code": 100},
        {"code": 11, "element": 6, "name": "B", "position": "DEF",
         "team_id": 2, "team_code": 200},
    ])
    teams = pd.DataFrame([{"team_id": 1, "code": 100}, {"team_id": 2, "code": 200}])
    ff = future_fixture_frame(fixtures, players, teams, gws=[2, 3],
                              season_idx=4)
    assert len(ff) == 4                       # 2 players x 2 fixtures
    row = ff[(ff.code == 10) & (ff.gw == 2)].iloc[0]
    assert row["was_home"] == True and row["opp_code"] == 200
    row3 = ff[(ff.code == 10) & (ff.gw == 3)].iloc[0]
    assert row3["was_home"] == False


def test_chips_available_for_splits_the_season_in_halves():
    used = {3: "wildcard", 8: "3xc", 25: "bboost"}
    # First half: the two chips already played in GW3/GW8 are gone, the rest
    # remain — a second-half chip does not consume a first-half one.
    assert chips_available_for(used, 10) == ["freehit", "bboost"]
    # Boundary: GW19 is still the first half, GW20 is the second.
    assert chips_available_for(used, 19) == ["freehit", "bboost"]
    # Second half: the first-half chips are back, only GW25's bboost is spent.
    assert chips_available_for(used, 20) == ["wildcard", "freehit", "3xc"]
