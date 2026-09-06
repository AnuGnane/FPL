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


ENTRY = {"summary_overall_points": 106, "current_event": 2,
         "leagues": {"classic": [
             {"id": 5, "name": "Focus FC League", "league_type": "x",
              "rank_count": 2, "entry_rank": 2, "entry_last_rank": 2},
             {"id": 9, "name": "Other League", "league_type": "x",
              "rank_count": 2, "entry_rank": 1, "entry_last_rank": 1},
             {"id": 314, "name": "Overall", "league_type": "s",
              "rank_count": 10_000_000, "entry_rank": 5, "entry_last_rank": 6},
         ], "h2h": []}}

OTHER_STANDINGS = {"standings": {"has_next": False, "results": [
    {"entry": 1, "entry_name": "You FC", "player_name": "Me", "rank": 1,
     "last_rank": 1, "total": 106, "event_total": 55},
    {"entry": 3, "entry_name": "Slow Coach", "player_name": "Sl",
     "rank": 2, "last_rank": 2, "total": 60, "event_total": 30},
]}}

SLOW_HISTORY = {"current": [{"event": 1, "points": 30, "total_points": 30},
                            {"event": 2, "points": 30, "total_points": 60}],
                "chips": []}


class FakeClient:
    def __init__(self):
        self.calls = []

    def get_entry(self, entry_id):
        return ENTRY

    def get_league_standings(self, league_id, page=1):
        self.calls.append((league_id, page))
        return OTHER_STANDINGS if league_id == 9 else STANDINGS

    def get_entry_history(self, entry_id):
        return {1: HISTORY, 2: RIVAL_HISTORY, 3: SLOW_HISTORY}[entry_id]

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
    from gaffer.config import serving_config

    monkeypatch.chdir(tmp_path)
    _artifacts(tmp_path)
    monkeypatch.setattr("gaffer.web.routers.league.fpl_client",
                        lambda: FakeClient())
    monkeypatch.setattr("gaffer.web.routers.league._OVERVIEW", {})
    serving_config.cache_clear()
    yield TestClient(create_app())
    serving_config.cache_clear()


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
    assert body["squad_gw"] == 2       # picks are public for finished GWs only
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


def test_the_focus_race_names_its_league_and_its_source(client):
    body = client.get("/api/league/race").json()
    assert body["league_name"] == "Focus FC League"
    assert body["focus"] is True and body["stance_source"] == "auto"


def test_a_manual_stance_shows_on_the_focus_race_at_once(client, tmp_path):
    from gaffer.config import LOCAL_OVERLAY, serving_config

    (tmp_path / LOCAL_OVERLAY).write_text('[league]\nstance = "defend"\n')
    serving_config.cache_clear()
    body = client.get("/api/league/race").json()
    assert body["lam"] == -0.5 and body["stance"] == "defend"
    assert body["stance_source"] == "manual"
    assert "ahead" in body["lam_explained"]


def test_another_private_league_computes_its_own_display_strategy(client):
    body = client.get("/api/league/race?league_id=9").json()
    assert body["league_id"] == 9 and body["league_name"] == "Other League"
    assert body["focus"] is False and body["stance_source"] == "auto"
    assert [r["name"] for r in body["standings"]] == ["You FC", "Slow Coach"]
    # 46 ahead of the only rival at GW3: z = 46 / (sigma * sqrt(36)) clears
    # the 0.25 deadband for any sigma the dial allows (8..30), so it defends.
    assert body["stance"] == "defend" and body["lam"] < 0
    assert body["gap"][-1]["gap"] == 46


def test_a_league_that_is_not_private_is_refused_by_id(client):
    resp = client.get("/api/league/race?league_id=314")
    assert resp.status_code == 422
    assert "314" in resp.json()["detail"]
    resp = client.get("/api/league/race?league_id=12345")
    assert resp.status_code == 422


def test_a_focus_that_is_not_private_is_still_served(tmp_path, monkeypatch):
    from gaffer.config import serving_config

    monkeypatch.chdir(tmp_path)
    _artifacts(tmp_path)
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 314\n')
    monkeypatch.setattr("gaffer.web.routers.league.fpl_client",
                        lambda: FakeClient())
    monkeypatch.setattr("gaffer.web.routers.league._OVERVIEW", {})
    serving_config.cache_clear()
    body = TestClient(create_app()).get("/api/league/race").json()
    assert body["league_id"] == 314 and body["league_name"] == "Overall"
    assert body["focus"] is True


def test_standings_page_until_my_row_is_in(tmp_path, monkeypatch):
    from gaffer.config import serving_config

    monkeypatch.chdir(tmp_path)
    _artifacts(tmp_path)
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 5\n')

    def row(entry, rank, total):
        return {"entry": entry, "entry_name": f"T{entry}", "player_name": "P",
                "rank": rank, "last_rank": rank, "total": total,
                "event_total": 1}

    page1 = [row(100 + i, i + 1, 500 - i) for i in range(50)]
    page2 = [row(200 + i, 51 + i, 400 - i) for i in range(49)] + [row(1, 100, 106)]
    page3 = [row(300 + i, 101 + i, 200 - i) for i in range(50)]
    pages = {1: page1, 2: page2, 3: page3}

    class Paged(FakeClient):
        def get_league_standings(self, league_id, page=1):
            self.calls.append((league_id, page))
            return {"standings": {"has_next": page < 3,
                                  "results": pages[page]}}

        def get_entry_history(self, entry_id):
            return HISTORY if entry_id == 1 else RIVAL_HISTORY

    fake = Paged()
    monkeypatch.setattr("gaffer.web.routers.league.fpl_client", lambda: fake)
    monkeypatch.setattr("gaffer.web.routers.league._OVERVIEW", {})
    serving_config.cache_clear()
    body = TestClient(create_app()).get("/api/league/race").json()
    # The overview asked league 5 for page 1 first; the race's own calls
    # are the last two, and page 3 is never fetched.
    assert fake.calls[-2:] == [(5, 1), (5, 2)]
    assert (5, 3) not in fake.calls
    assert any(r["is_you"] for r in body["standings"])
    assert len(body["standings"]) == 100


def test_rivals_and_rival_take_the_league_too(client):
    rivals = client.get("/api/league/rivals?league_id=9").json()
    assert [r["name"] for r in rivals] == ["Slow Coach"]
    detail = client.get("/api/league/rivals/3?league_id=9").json()
    assert detail["name"] == "Slow Coach"
    assert client.get("/api/league/rivals/3").status_code == 422
