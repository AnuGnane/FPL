import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import SolveState, pool_rows, save_solve_state
from gaffer.web.app import create_app

STANDINGS = {"standings": {"has_next": False, "results": [
    {"entry": 1, "entry_name": "You FC", "player_name": "Me", "rank": 2,
     "last_rank": 2, "total": 106, "event_total": 55},
    {"entry": 2, "entry_name": "Ten Hag Hive", "player_name": "Riv",
     "rank": 1, "last_rank": 1, "total": 190, "event_total": 60},
]}}

HISTORY = {"current": [{"event": 1, "points": 51, "total_points": 51},
                       {"event": 2, "points": 55, "total_points": 106}],
           "chips": [{"event": 2, "name": "bboost"}]}

RIVAL_HISTORY = {"current": [{"event": 1, "points": 90, "total_points": 90},
                             {"event": 2, "points": 100,
                              "total_points": 190}],
                 "chips": []}

PICKS = {"picks": [{"element": 7, "position": 1, "multiplier": 2},
                   {"element": 8, "position": 2, "multiplier": 1}],
         "entry_history": {"bank": 5, "value": 1013, "total_points": 190,
                           "points": 100}}


class FakeClient:
    def get_league_standings(self, league_id, page=1):
        return STANDINGS

    def get_entry_history(self, entry_id):
        return HISTORY if entry_id == 1 else RIVAL_HISTORY

    def get_entry_picks(self, entry_id, gw):
        return PICKS

    def get_event_status(self):
        return {"status": [], "leagues": "updated"}


def _artifacts(tmp_path):
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 5\n')
    players = pd.DataFrame([
        {"code": 100, "element": 7, "name": "Salah", "position": "MID",
         "team_id": 1, "team_code": 300, "now_cost": 130, "status": "a",
         "news": "", "chance_of_playing": None, "selected_by_percent": 45.0,
         "form": 5.0, "points_per_game": 6.0, "ep_next": 6.0,
         "price_change_percent": 10.0, "price_change_calibrating": False,
         "penalties_order": 1.0, "direct_freekicks_order": 1.0,
         "corners_and_indirect_freekicks_order": 2.0},
        {"code": 101, "element": 8, "name": "Dud", "position": "DEF",
         "team_id": 2, "team_code": 301, "now_cost": 45, "status": "a",
         "news": "", "chance_of_playing": None, "selected_by_percent": 5.0,
         "form": 1.0, "points_per_game": 2.0, "ep_next": 2.0,
         "price_change_percent": 0.0, "price_change_calibrating": False,
         "penalties_order": None, "direct_freekicks_order": None,
         "corners_and_indirect_freekicks_order": None},
    ])
    (tmp_path / "data" / "live").mkdir(parents=True, exist_ok=True)
    players.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    save_solve_state(SolveState(
        gw=3, gws=[3], deadline="2026-09-11T17:30:00Z",
        generated_at="2026-09-10T09:00:00Z", mode="weekly", bank=5,
        free_transfers=1, owned_codes=[100], lam=0.4, league_eo={100: 62.5},
        avail_by_gw={3: ["wildcard"]},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4, "horizon": 1},
        pool=pool_rows(
            pd.DataFrame([{"code": 100, "position": "MID", "team_code": 300,
                           "cost": 130, "sell": 128}]),
            players, [100], {(100, 3): 6.4}, [3])))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _artifacts(tmp_path)
    monkeypatch.setattr("gaffer.web.routers.league.fpl_client",
                        lambda: FakeClient())
    return TestClient(create_app())


def test_race_has_standings_trajectory_gap_and_lambda(client):
    body = client.get("/api/league/race").json()
    names = [row["name"] for row in body["standings"]]
    assert names == ["Ten Hag Hive", "You FC"]      # sorted by total desc
    you = [row for row in body["standings"] if row["is_you"]]
    assert len(you) == 1 and you[0]["total"] == 106
    trajectory = {t["name"]: t["points"] for t in body["trajectory"]}
    assert [p["total"] for p in trajectory["You FC"]] == [51, 106]
    assert [g["gap"] for g in body["gap"]] == [-39, -84]
    assert body["win_probability"][0]["name"] == "Ten Hag Hive"
    assert 0.0 <= body["win_probability"][0]["p_win"] <= 1.0
    assert body["lam"] == 0.4 and body["stance"] == "chase"
    assert "differentials" in body["lam_explained"]


def test_race_without_a_league_id_says_so(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _artifacts(tmp_path)
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 0\n')
    resp = TestClient(create_app()).get("/api/league/race")
    assert resp.status_code == 422
    assert "league_id" in resp.json()["detail"]


def test_race_surfaces_a_dead_api_as_a_retriable_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _artifacts(tmp_path)

    class Dead(FakeClient):
        def get_league_standings(self, league_id, page=1):
            raise RuntimeError("connection refused")

    monkeypatch.setattr("gaffer.web.routers.league.fpl_client",
                        lambda: Dead())
    resp = TestClient(create_app()).get("/api/league/race")
    assert resp.status_code == 422
    assert "FPL API" in resp.json()["detail"]


def test_rivals_list_summarises_every_entry_but_you(client):
    rows = client.get("/api/league/rivals").json()
    assert [r["entry"] for r in rows] == [2]
    row = rows[0]
    assert row["name"] == "Ten Hag Hive" and row["total"] == 190
    assert row["overlap"] == 1          # code 100 (Salah) is in your squad too
    assert row["differentials"] == 1    # code 101 is theirs, not yours


def test_rival_detail_lists_the_squad_captain_chips_and_overlap(client):
    body = client.get("/api/league/rivals/2").json()
    assert body["entry"] == 2 and body["name"] == "Ten Hag Hive"
    assert body["team_value"] == 101.8          # (value 1013 + bank 5) / 10
    assert body["captain"]["name"] == "Salah"
    assert body["chips_used"] == []
    squad = {p["name"] for p in body["squad"]}
    assert squad == {"Salah", "Dud"}
    assert [p["name"] for p in body["shared"]] == ["Salah"]
    assert [p["name"] for p in body["their_differentials"]] == ["Dud"]
    assert body["your_differentials"] == []
    assert body["live_points"] is None           # no gameweek in progress


def test_rival_detail_for_an_unknown_entry_is_a_readable_422(client):
    resp = client.get("/api/league/rivals/999")
    assert resp.status_code == 422
    assert "999" in resp.json()["detail"]
