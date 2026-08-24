import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import SolveState, pool_rows, save_solve_state
from gaffer.web.app import create_app

TEAMS = pd.DataFrame([{"team_id": 1, "code": 300, "name": "Liverpool",
                       "short_name": "LIV"},
                      {"team_id": 2, "code": 301, "name": "Arsenal",
                       "short_name": "ARS"}])

FIXTURES_ALL = pd.DataFrame([
    {"gw": 2, "home_id": 1, "away_id": 2,
     "kickoff_time": "2026-09-05T14:00:00Z", "home_goals": 2.0,
     "away_goals": 0.0, "finished": True},
    {"gw": 3, "home_id": 2, "away_id": 1,
     "kickoff_time": "2026-09-12T14:00:00Z", "home_goals": None,
     "away_goals": None, "finished": False},
])

FINISHED = pd.DataFrame([{"season_idx": 4, "gw": 2,
                          "kickoff_time": "2026-09-05T14:00:00Z",
                          "home_code": 300, "away_code": 301,
                          "home_goals": 2, "away_goals": 0}])

OWNED_POOL = pd.DataFrame([{"code": 100, "position": "MID",
                            "team_code": 300, "cost": 130, "sell": 128}])

PLAYERS = pd.DataFrame([{"code": 100, "element": 7, "name": "Salah",
                         "position": "MID", "team_id": 1, "team_code": 300,
                         "now_cost": 130, "status": "a", "news": "",
                         "chance_of_playing": None,
                         "selected_by_percent": 45.0, "form": 5.0,
                         "points_per_game": 6.0, "ep_next": 6.0,
                         "price_change_percent": 0.0,
                         "price_change_calibrating": False,
                         "penalties_order": 1.0,
                         "direct_freekicks_order": None,
                         "corners_and_indirect_freekicks_order": None}])

PLAYER_GW = pd.DataFrame([
    {"code": 100, "gw": 2, "total_points": 12, "minutes": 90, "value": 129},
    {"code": 100, "gw": 3, "total_points": 5, "minutes": 90, "value": 130},
])

ADVICE = {"gw": 2, "deadline": "2026-09-04T17:30:00Z", "buys": [],
          "sells": [], "hits": 0,
          "xi": [{"code": 100, "name": "Salah", "ep": 6.0}], "bench": [],
          "captain": {"code": 100, "name": "Salah", "ep": 6.0},
          "vice": {"code": 100, "name": "Salah", "ep": 6.0},
          "captain_options": [], "chip_table": [], "wildcard_now": None,
          "alternatives": [], "threats": [], "price_alerts": [],
          "expected_pts": 12.0, "plan_by_gw": [], "strategy": None,
          "win_probs": [], "mode": "weekly"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 5\n')
    live = tmp_path / "data" / "live"
    live.mkdir(parents=True, exist_ok=True)
    TEAMS.to_parquet(live / "teams.parquet", index=False)
    PLAYERS.to_parquet(live / "players.parquet", index=False)
    FIXTURES_ALL.to_parquet(live / "fixtures_all.parquet", index=False)
    FINISHED.to_parquet(live / "fixtures.parquet", index=False)
    PLAYER_GW.to_parquet(live / "player_gw.parquet", index=False)
    pd.DataFrame([{"gw": 3, "deadline_time": "2026-09-11T17:30:00Z",
                   "is_current": False, "is_next": True, "finished": False,
                   "data_checked": False}]).to_parquet(
        live / "events.parquet", index=False)
    (tmp_path / "reports").mkdir(exist_ok=True)
    (tmp_path / "reports" / "gw2-advice.json").write_text(json.dumps(ADVICE))
    (tmp_path / "reports" / "health.json").write_text(json.dumps(
        {"gw": 2, "mae_starters": 1.4, "captain_actual": 12,
         "advice_pts": None, "actual_pts": None}))
    (tmp_path / "models").mkdir(exist_ok=True)
    (tmp_path / "models" / "minutes.meta.json").write_text(json.dumps(
        {"saved_at": "2026-09-10T08:00:00+00:00", "rows": 113000,
         "auc_p60": 0.81}))
    (tmp_path / "logs").mkdir(exist_ok=True)
    (tmp_path / "logs" / "advise.log").write_text(
        "Trained on 113000 rows.\nReport: reports/gw3-report.html\n")
    save_solve_state(SolveState(
        gw=3, gws=[3, 4], deadline="2026-09-11T17:30:00Z",
        generated_at="2026-09-10T09:00:00Z", mode="weekly", bank=5,
        free_transfers=1, owned_codes=[100], lam=0.0, league_eo={},
        avail_by_gw={3: ["bboost"], 4: ["bboost"]},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4, "horizon": 2},
        pool=pool_rows(OWNED_POOL, PLAYERS, [100],
                       {(100, 3): 6.4, (100, 4): 5.1}, [3, 4])))
    return TestClient(create_app())


def test_chip_plan_scores_every_available_chip_week(client, monkeypatch):
    monkeypatch.setattr(
        "gaffer.web.routers.meta.evaluate_chips",
        lambda pool, state, **kw: pd.DataFrame(
            [{"chip": "bboost", "gw": 3, "gain": 4.0, "per_week": 4.0},
             {"chip": "bboost", "gw": 4, "gain": 9.5, "per_week": 9.5}]))
    body = client.get("/api/chips/plan").json()
    assert body["gw"] == 3
    bb = body["chips"][0]
    assert bb["chip"] == "bboost" and bb["best_gw"] == 4
    assert bb["play_now_delta"] == -5.5
    # the payload says how wide the window was, and prices it per week
    assert bb["weeks_scored"] == 2 and bb["best_gain_per_week"] == 9.5


def _full_squad_state(drop_owned: int | None = None):
    """A 20-man pool, 15 of them owned, free hit available in GW3."""
    rows, code = [], 1
    for pos, n in [("GKP", 2), ("DEF", 6), ("MID", 7), ("FWD", 5)]:
        for _ in range(n):
            rows.append({"code": code, "position": pos,
                         "team_code": code % 8, "cost": 50, "sell": 50})
            code += 1
    owned = [1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 16, 17, 18]
    frame = pd.DataFrame(rows)
    if drop_owned is not None:
        frame = frame[frame["code"] != drop_owned]
    players = pd.DataFrame({"code": frame["code"],
                            "name": [f"P{c}" for c in frame["code"]]})
    ep_by = {(int(c), g): 2.0 for c in frame["code"] for g in (3, 4)}
    save_solve_state(SolveState(
        gw=3, gws=[3, 4], deadline="2026-09-11T17:30:00Z",
        generated_at="2026-09-10T09:00:00Z", mode="weekly", bank=0,
        free_transfers=1, owned_codes=owned, lam=0.0, league_eo={},
        avail_by_gw={3: ["freehit"], 4: []},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4, "horizon": 2},
        pool=pool_rows(frame, players, owned, ep_by, [3, 4])))


def test_chip_plan_on_an_infeasible_saved_state_is_a_readable_422(client):
    # An owned player missing from the saved pool shrinks the free-hit budget
    # below the price of any legal fifteen, so the from-scratch solve fails.
    _full_squad_state(drop_owned=1)
    resp = client.get("/api/chips/plan")
    assert resp.status_code == 422
    assert "gaffer advise" in resp.json()["detail"]


def test_chip_plan_on_an_older_solve_state_is_a_readable_422(client,
                                                             tmp_path):
    meta = tmp_path / "reports" / "solve_state_gw3.json"
    payload = json.loads(meta.read_text())
    payload["opt"].pop("hit_cost")
    meta.write_text(json.dumps(payload))
    resp = client.get("/api/chips/plan")
    assert resp.status_code == 422
    assert "gaffer advise" in resp.json()["detail"]


def test_history_pairs_expected_with_actual_once_a_gw_resolves(client):
    body = client.get("/api/history").json()
    run = body["runs"][0]
    assert run["gw"] == 2 and run["expected_pts"] == 12.0
    # XI is Salah alone, captained: 12 + 12.
    assert run["actual_pts"] == 24
    assert run["captain"] == "Salah"
    prices = {p["name"]: p["points"] for p in body["prices"]}
    assert [pt["price"] for pt in prices["Salah"]] == [12.9, 13.0]
    assert body["backtests"] == []


def test_health_reports_freshness_models_logs_and_inventory(client):
    body = client.get("/api/health").json()
    sources = {s["source"]: s for s in body["data"]}
    assert sources["player_gw"]["present"] is True
    assert sources["odds"]["present"] is False
    assert body["models"][0]["name"] == "minutes"
    assert body["models"][0]["saved_at"] == "2026-09-10T08:00:00+00:00"
    assert body["models"][0]["metrics"] == {"rows": 113000, "auc_p60": 0.81}
    assert body["odds_key_present"] is False
    assert body["launchd"]["last_line"] == "Report: reports/gw3-report.html"
    names = [item["name"] for item in body["artifacts"]]
    assert "reports/gw2-advice.json" in names


def test_ticker_grades_every_team_over_the_window(client):
    body = client.get("/api/fixtures/ticker?weeks=2").json()
    assert body["gws"] == [3]
    assert body["source"] == "elo"           # no odds file on disk
    liverpool = next(t for t in body["teams"] if t["name"] == "Liverpool")
    cell = liverpool["cells"][0]
    assert cell["opponent"] == "ARS" and cell["home"] is False
    assert 0.0 <= cell["difficulty"] <= 1.0
    # Arsenal host the return fixture, and one Elo update (a 2-0 loss, so at
    # most K=20 either way) cannot outweigh the 60-point home advantage — so
    # Liverpool away is the harder half, and the two halves complement.
    arsenal = next(t for t in body["teams"] if t["name"] == "Arsenal")
    assert arsenal["cells"][0]["home"] is True
    assert cell["difficulty"] > arsenal["cells"][0]["difficulty"]
    assert round(cell["difficulty"] + arsenal["cells"][0]["difficulty"], 3) \
        == 1.0


def test_data_refresh_queues_a_job(client, monkeypatch):
    monkeypatch.setattr("gaffer.web.routers.meta.run_data_refresh",
                        lambda: {"rows": 7})
    resp = client.post("/api/data/refresh")
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    for _ in range(500):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            break
    assert job["status"] == "done", job["error"]
    assert job["result"] == {"rows": 7}
