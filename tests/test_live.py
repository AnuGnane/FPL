import pandas as pd

from gaffer.data import store
from gaffer.data.live import CANONICAL_COLS, history_to_rows, refresh_live

SUMMARY = {
    "history": [
        {
            "element": 10,
            "round": 1,
            "minutes": 90,
            "starts": 1,
            "total_points": 9,
            "goals_scored": 1,
            "assists": 0,
            "clean_sheets": 1,
            "goals_conceded": 0,
            "saves": 0,
            "bonus": 2,
            "bps": 30,
            "yellow_cards": 0,
            "red_cards": 0,
            "own_goals": 0,
            "penalties_missed": 0,
            "penalties_saved": 0,
            "expected_goals": "0.45",
            "expected_assists": "0.10",
            "expected_goal_involvements": "0.55",
            "expected_goals_conceded": "0.30",
            "defensive_contribution": 2,
            "tackles": 3,
            "recoveries": 6,
            "clearances_blocks_interceptions": 7,
            "value": 55,
            "selected": 100000,
            "opponent_team": 3,
            "was_home": True,
            "kickoff_time": "2026-08-21T19:00:00Z",
        }
    ]
}

PLAYER_META = {"code": 999, "name": "Testman", "position": "DEF", "team_code": 8}
TEAM_ID_TO_CODE = {3: 14}


def test_history_to_rows_maps_canonical():
    rows = history_to_rows(
        SUMMARY, PLAYER_META, TEAM_ID_TO_CODE, season="2026-27", season_idx=4
    )
    df = pd.DataFrame(rows)
    assert set(CANONICAL_COLS) <= set(df.columns)
    r = df.iloc[0]
    assert r["code"] == 999 and r["gw"] == 1 and r["opp_code"] == 14
    assert r["xg"] == 0.45 and r["defcon"] == 2 and r["cbi"] == 7


class FakeClient:
    """Stands in for FPLClient: one player, two GWs, one of them provisional."""

    BOOTSTRAP = {
        "events": [
            {"id": 1, "data_checked": True},
            {"id": 2, "data_checked": False},
        ],
        "elements": [
            {
                "code": 999,
                "id": 10,
                "web_name": "Testman",
                "element_type": 2,
                "team": 3,
                "team_code": 8,
                "now_cost": 55,
            }
        ],
        "teams": [{"id": 3, "code": 14, "name": "Chelsea", "short_name": "CHE"}],
    }

    def get_bootstrap(self):
        return self.BOOTSTRAP

    def get_element_summary(self, element):
        base = dict(SUMMARY["history"][0])
        gw2 = dict(base, round=2, total_points=5)
        return {"history": [base, gw2]}


def test_refresh_live_drops_unchecked_gws(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    df = refresh_live(FakeClient(), season="2026-27", season_idx=4, sleep_s=0)
    assert df["gw"].tolist() == [1]
    saved = store.load("live/player_gw.parquet")
    assert saved["gw"].tolist() == [1]
    assert list(saved.columns) == CANONICAL_COLS
    assert saved.iloc[0]["element"] == 10 and saved.iloc[0]["opp_code"] == 14
