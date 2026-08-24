import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import (COMPONENT_COLS, SolveState, pool_rows,
                              save_components, save_solve_state)
from gaffer.web.app import create_app

PLAYERS = pd.DataFrame([
    {"code": 100, "element": 7, "name": "Salah", "position": "MID",
     "team_id": 1, "team_code": 300, "now_cost": 130, "status": "a",
     "news": "", "chance_of_playing": None, "selected_by_percent": 45.0,
     "form": 5.0, "points_per_game": 6.0, "ep_next": 6.0,
     "price_change_percent": 10.0, "price_change_calibrating": False,
     "penalties_order": 1.0, "direct_freekicks_order": 1.0,
     "corners_and_indirect_freekicks_order": 2.0},
    {"code": 101, "element": 8, "name": "Bloke", "position": "DEF",
     "team_id": 2, "team_code": 301, "now_cost": 45, "status": "d",
     "news": "knock - 75%", "chance_of_playing": 75.0,
     "selected_by_percent": 5.0, "form": 1.0, "points_per_game": 2.0,
     "ep_next": 2.0, "price_change_percent": 0.0,
     "price_change_calibrating": False, "penalties_order": None,
     "direct_freekicks_order": None,
     "corners_and_indirect_freekicks_order": None},
])

TEAMS = pd.DataFrame([{"team_id": 1, "code": 300, "name": "Liverpool",
                       "short_name": "LIV"},
                      {"team_id": 2, "code": 301, "name": "Arsenal",
                       "short_name": "ARS"}])

FIXTURES = pd.DataFrame([
    {"gw": 3, "home_id": 1, "away_id": 2,
     "kickoff_time": "2026-09-12T14:00:00Z", "home_goals": None,
     "away_goals": None, "finished": False},
    {"gw": 4, "home_id": 2, "away_id": 1,
     "kickoff_time": "2026-09-19T14:00:00Z", "home_goals": None,
     "away_goals": None, "finished": False},
])


def _components():
    row = {c: 0.0 for c in COMPONENT_COLS}
    row.update({"code": 100, "element": 7, "name": "Salah", "position": "MID",
                "team_code": 300, "team_name": "Liverpool", "gw": 3,
                "opp_code": 301, "opp_name": "Arsenal", "was_home": True,
                "kickoff_time": "2026-09-12T14:00:00Z", "p_play": 0.95,
                "p60": 0.88, "e_goals": 0.42, "e_assists": 0.25,
                "p_cs": 0.31, "e_gc": 1.2, "p_cs_model": 0.25,
                "e_gc_model": 1.4, "odds_e_goals_against": 1.17,
                "odds_weight": 0.7, "pen_taker": 1.0, "setpiece_taker": 0.5,
                "ep_minutes": 1.83, "ep_goals": 2.0, "ep_assists": 0.71,
                "ep_cs": 0.27, "ep_bonus": 0.5, "ep_uncalibrated": 5.9,
                "cal_delta": 0.5, "ep": 6.4})
    return pd.DataFrame([row])[COMPONENT_COLS]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True, exist_ok=True)
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    TEAMS.to_parquet(tmp_path / "data/live/teams.parquet", index=False)
    FIXTURES.to_parquet(tmp_path / "data/live/fixtures_all.parquet",
                        index=False)
    pool = pool_rows(
        pd.DataFrame([{"code": 100, "position": "MID", "team_code": 300,
                       "cost": 130, "sell": 128},
                      {"code": 101, "position": "DEF", "team_code": 301,
                       "cost": 45, "sell": 45}]),
        PLAYERS, owned_codes=[100],
        ep_by={(100, 3): 6.4, (100, 4): 5.1, (101, 3): 2.0, (101, 4): 2.2},
        gws=[3, 4])
    save_solve_state(SolveState(
        gw=3, gws=[3, 4], deadline="2026-09-11T17:30:00Z",
        generated_at="2026-09-10T09:00:00Z", mode="weekly", bank=5,
        free_transfers=1, owned_codes=[100], lam=0.0,
        league_eo={100: 62.5}, avail_by_gw={3: [], 4: []},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4, "horizon": 2},
        pool=pool))
    save_components(_components(), 3)
    return TestClient(create_app())


def test_players_lists_the_candidate_pool_with_ep_and_context(client):
    rows = client.get("/api/players").json()
    assert [r["name"] for r in rows] == ["Salah", "Bloke"]   # ep_next desc
    salah = rows[0]
    assert salah["price"] == 13.0 and salah["ep_next"] == 6.4
    assert salah["ep_horizon"] == 11.5 and salah["league_eo"] == 62.5
    assert salah["team_name"] == "Liverpool" and salah["available"] is True
    assert salah["in_squad"] is True and salah["penalties_order"] == 1
    bloke = rows[1]
    assert bloke["available"] is False and bloke["news"] == "knock - 75%"


def test_players_filters_and_searches(client):
    assert [r["name"] for r in
            client.get("/api/players?position=DEF").json()] == ["Bloke"]
    assert [r["name"] for r in
            client.get("/api/players?team=300").json()] == ["Salah"]
    assert [r["name"] for r in
            client.get("/api/players?search=blo").json()] == ["Bloke"]
    assert [r["name"] for r in
            client.get("/api/players?sort=price").json()] == ["Salah",
                                                              "Bloke"]


def test_explain_returns_components_minutes_odds_and_next_fixtures(client):
    body = client.get("/api/players/100/explain").json()
    assert body["name"] == "Salah" and body["ep_next"] == 6.4
    fixture = body["fixtures"][0]
    assert fixture["opponent"] == "Arsenal" and fixture["home"] is True
    assert fixture["ep"] == 6.4
    parts = {c["label"]: c["points"] for c in fixture["components"]}
    assert parts["Attacking"] == 2.71          # goals 2.0 + assists 0.71
    assert parts["Minutes"] == 1.83
    assert fixture["minutes"]["p60"] == 0.88
    assert fixture["calibration_delta"] == 0.5
    assert fixture["odds"]["weight"] == 0.7
    assert fixture["odds"]["p_cs_model"] == 0.25
    assert fixture["odds"]["p_cs_blended"] == 0.31
    assert body["set_pieces"] == {"penalties": 1, "free_kicks": 1,
                                  "corners": 2}
    assert [f["opponent"] for f in body["next_fixtures"]] == ["Arsenal",
                                                              "Arsenal"]


def test_explain_for_a_player_with_no_components_is_a_readable_422(client):
    resp = client.get("/api/players/101/explain")
    assert resp.status_code == 422
    assert "101" in resp.json()["detail"]
