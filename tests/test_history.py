import pandas as pd

from gaffer.data.history import merged_gw_to_canonical


def test_merged_gw_to_canonical_maps_and_joins_code():
    merged = pd.DataFrame(
        [
            {
                "element": 5,
                "name": "A. Player",
                "position": "GK",
                "team": "Arsenal",
                "round": 3,
                "GW": 3,
                "minutes": 90,
                "starts": 1,
                "total_points": 6,
                "goals_scored": 0,
                "assists": 0,
                "clean_sheets": 1,
                "goals_conceded": 0,
                "saves": 4,
                "bonus": 0,
                "bps": 22,
                "yellow_cards": 0,
                "red_cards": 0,
                "own_goals": 0,
                "penalties_missed": 0,
                "penalties_saved": 0,
                "expected_goals": 0.0,
                "expected_assists": 0.0,
                "expected_goal_involvements": 0.0,
                "expected_goals_conceded": 0.5,
                "value": 50,
                "selected": 5000,
                "opponent_team": 2,
                "was_home": True,
                "kickoff_time": "2022-08-27T14:00:00Z",
            }
        ]
    )
    players_raw = pd.DataFrame([{"id": 5, "code": 777}])
    teams = pd.DataFrame([{"id": 2, "code": 91}, {"id": 1, "code": 3}])
    out = merged_gw_to_canonical(
        merged, players_raw, teams, season="2022-23", season_idx=0
    )
    r = out.iloc[0]
    assert r["code"] == 777 and r["position"] == "GKP" and r["opp_code"] == 91
    assert pd.isna(r["defcon"])  # column absent pre-2025/26 -> NaN, not crash
    # set-piece orders are a live-only snapshot; history backfills them as NA
    assert pd.isna(r["penalties_order"])
    assert pd.isna(r["direct_freekicks_order"])
    assert pd.isna(r["corners_and_indirect_freekicks_order"])


def test_merged_gw_to_canonical_drops_assistant_manager_rows():
    """2024-25 vaastav rows carry position "AM" (Assistant-Manager chip)."""
    merged = pd.DataFrame(
        [
            {"element": 5, "position": "MID", "round": 3, "opponent_team": 2},
            {"element": 9, "position": "AM", "round": 3, "opponent_team": 2},
        ]
    )
    players_raw = pd.DataFrame([{"id": 5, "code": 777}, {"id": 9, "code": 888}])
    teams = pd.DataFrame([{"id": 2, "code": 91}])
    out = merged_gw_to_canonical(
        merged, players_raw, teams, season="2024-25", season_idx=2
    )
    assert list(out["code"]) == [777]
