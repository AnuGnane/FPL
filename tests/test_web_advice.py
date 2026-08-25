"""Fixture artifacts are built inline, the way the rest of the suite does it:
a real advice JSON, a real solve state, and a two-row events table."""

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import SolveState, pool_rows, save_solve_state
from gaffer.web.app import create_app
from gaffer.web.routers.advice import with_positions

PAST = "2026-08-01T17:30:00Z"
FUTURE = "2099-09-18T17:30:00Z"

ADVICE = {
    "gw": 3, "deadline": PAST,
    "buys": [{"code": 100, "name": "Salah", "ep": 6.4, "tag": "cover"}],
    "sells": [{"code": 101, "name": "Dud", "ep": 1.9}], "hits": 0,
    "xi": [{"code": 100, "name": "Salah", "ep": 6.4}],
    "bench": [{"code": 101, "name": "Dud", "ep": 1.9}],
    "captain": {"code": 100, "name": "Salah", "ep": 6.4},
    "vice": {"code": 101, "name": "Dud", "ep": 1.9},
    "captain_options": [], "chip_table": [{"chip": "bboost", "gw": 4,
                                           "gain": 6.1}],
    "wildcard_now": None, "alternatives": [], "threats": [],
    "price_alerts": [], "expected_pts": 61.5, "plan_by_gw": [],
    "strategy": {"lam": 0.25, "gap": 84, "weeks_left": 36,
                 "stance": "chase", "rival_name": "Ten Hag Hive"},
    "win_probs": [{"name": "Ten Hag Hive", "total": 190, "p_win": 0.41}],
    "mode": "weekly",
}


def _write_artifacts(root, deadlines=(PAST, FUTURE)):
    """GW3's deadline is ``deadlines[0]`` and GW4's is ``deadlines[1]``, so the
    default pair puts the advice a gameweek behind the clock."""
    (root / "reports").mkdir(exist_ok=True)
    (root / "reports" / "gw3-advice.json").write_text(
        json.dumps({**ADVICE, "deadline": deadlines[0]}))
    pool = pool_rows(
        pd.DataFrame([{"code": 100, "position": "MID", "team_code": 300,
                       "cost": 130, "sell": 128}]),
        pd.DataFrame([{"code": 100, "name": "Salah"}]),
        owned_codes=[100], ep_by={(100, 3): 6.4, (100, 4): 5.1}, gws=[3, 4])
    save_solve_state(SolveState(
        gw=3, gws=[3, 4], deadline=deadlines[0],
        generated_at="2026-09-10T09:00:00Z", mode="weekly", bank=12,
        free_transfers=2, owned_codes=[100], lam=0.25, league_eo={100: 62.5},
        avail_by_gw={3: ["wildcard", "bboost"], 4: ["wildcard", "bboost"]},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4, "horizon": 2},
        pool=pool))
    events = pd.DataFrame([{"gw": 3, "deadline_time": deadlines[0],
                            "is_current": False, "is_next": True,
                            "finished": False, "data_checked": False},
                           {"gw": 4, "deadline_time": deadlines[1],
                            "is_current": False, "is_next": False,
                            "finished": False, "data_checked": False}])
    (root / "data" / "live").mkdir(parents=True, exist_ok=True)
    events.to_parquet(root / "data" / "live" / "events.parquet", index=False)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_artifacts(tmp_path)
    return TestClient(create_app())


def test_latest_returns_the_saved_advice_with_staleness(client):
    body = client.get("/api/advice/latest").json()
    assert body["gw"] == 3
    assert body["advice"]["captain"]["name"] == "Salah"
    assert body["staleness"]["advice_gw"] == 3
    assert body["staleness"]["generated_at"] == "2026-09-10T09:00:00Z"
    # GW3's deadline has passed and GW4's has not, so the next deadline is
    # GW4 and the advice is a gameweek behind.
    assert body["staleness"]["stale"] is True
    assert body["staleness"]["current_gw"] == 4
    assert body["staleness"]["deadline_passed"] is True
    assert "GW4" in body["staleness"]["reason"]


def test_fresh_advice_is_not_flagged_stale(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    soon = pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=2)
    _write_artifacts(tmp_path, deadlines=(soon.isoformat(),
                                          (soon + pd.Timedelta(days=9))
                                          .isoformat()))
    body = TestClient(create_app()).get("/api/advice/latest").json()
    assert body["staleness"]["stale"] is False
    assert body["staleness"]["deadline_passed"] is False
    assert body["staleness"]["current_gw"] == 3


def test_latest_without_any_run_explains_what_to_do(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    resp = TestClient(create_app()).get("/api/advice/latest")
    assert resp.status_code == 422
    assert "gaffer advise" in resp.json()["detail"]


def test_rerun_queues_a_job(client, monkeypatch):
    ran = []
    monkeypatch.setattr("gaffer.web.routers.advice.run_train_and_advise",
                        lambda: ran.append(True) or {"gw": 4})
    resp = client.post("/api/advice/rerun")
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    for _ in range(500):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            break
    assert job["status"] == "done", job["error"]
    assert job["result"] == {"gw": 4}


def test_rerun_beyond_the_queue_cap_is_429(client, monkeypatch):
    import threading

    gate = threading.Event()
    monkeypatch.setattr("gaffer.web.routers.advice.run_train_and_advise",
                        lambda: gate.wait(2))
    for _ in range(6):                       # 1 running + 5 queued
        assert client.post("/api/advice/rerun").status_code == 202
    resp = client.post("/api/advice/rerun")
    assert resp.status_code == 429
    assert "queued" in resp.json()["detail"]
    gate.set()


# --- backfilling artifacts written before positions were saved --------------


def test_with_positions_fills_missing_positions_from_the_solve_state():
    """Advice JSON written by an older `gaffer advise` has no ``position``,
    and the user must not have to re-run to get a pitch."""
    pool = pd.DataFrame([{"code": 100, "position": "MID"},
                         {"code": 101, "position": "DEF"}])
    payload = with_positions(
        {"xi": [{"code": 100, "name": "Salah", "ep": 6.4}],
         "bench": [{"code": 101, "name": "Dud", "ep": 1.9}],
         "buys": [], "sells": [],
         "captain": {"code": 100, "name": "Salah", "ep": 6.4},
         "vice": {"code": 101, "name": "Dud", "ep": 1.9},
         "expected_pts": 61.5},
        pool)
    assert payload["xi"][0]["position"] == "MID"
    assert payload["bench"][0]["position"] == "DEF"
    assert payload["captain"]["position"] == "MID"
    assert payload["vice"]["position"] == "DEF"
    assert payload["expected_pts"] == 61.5          # nothing else disturbed


def test_with_positions_leaves_a_complete_payload_untouched():
    pool = pd.DataFrame([{"code": 100, "position": "MID"}])
    given = {"xi": [{"code": 100, "name": "Salah", "ep": 6.4,
                     "position": "FWD"}]}
    assert with_positions(given, pool)["xi"][0]["position"] == "FWD"


def test_with_positions_survives_a_code_the_pool_never_saw():
    pool = pd.DataFrame([{"code": 100, "position": "MID"}])
    out = with_positions({"xi": [{"code": 999, "name": "Ghost", "ep": 0.0}]},
                         pool)
    assert out["xi"][0]["position"] == ""


def test_latest_serves_positions_for_an_advice_json_without_them(client):
    """The fixture advice JSON above carries no positions at all."""
    xi = client.get("/api/advice/latest").json()["advice"]["xi"]
    assert [p["position"] for p in xi] == ["MID"]


# --- how much of the season the model has seen ------------------------------


def _write_player_gw(root, gws):
    (root / "data" / "live").mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"season": "2026-27", "season_idx": 4, "gw": g,
                   "code": 100, "total_points": 4} for g in gws],
                 columns=["season", "season_idx", "gw", "code",
                          "total_points"]).to_parquet(
        root / "data" / "live" / "player_gw.parquet", index=False)


def test_staleness_flags_a_season_with_no_ingested_gameweeks(client):
    """The real bug: advise ran before FPL finalized GW1, so nothing of this
    season is on disk and the next deadline is GW4."""
    body = client.get("/api/advice/latest").json()
    assert body["staleness"]["data_through_gw"] is None
    assert "GW1-GW3" in body["staleness"]["data_warning"]
    assert "gaffer advise" in body["staleness"]["data_warning"]


def test_staleness_is_computed_from_the_parquet_not_the_advice_json(client,
                                                                    tmp_path):
    """The stored advice is old and says nothing; a fresh ingest still shows
    through the API without re-running anything."""
    _write_player_gw(tmp_path, [1, 2, 3])
    body = client.get("/api/advice/latest").json()
    assert body["staleness"]["data_through_gw"] == 3
    assert body["staleness"]["data_warning"] is None


def test_staleness_warns_when_only_the_last_gameweek_is_missing(client,
                                                               tmp_path):
    _write_player_gw(tmp_path, [1, 2])
    body = client.get("/api/advice/latest").json()
    assert body["staleness"]["data_through_gw"] == 2
    assert body["staleness"]["data_warning"].startswith(
        "model has no data for GW3 ")


def test_the_advice_endpoint_passes_scenario_fields_through_untouched():
    """AdviceLatest.advice is dict[str, Any] by design, so the v4c fields need
    no schema change — but 'by design' should be a test, not a belief."""
    from gaffer.web.schemas import AdviceLatest

    payload = {
        "gw": 7, "mode": "weekly", "deadline": "2026-10-03T10:00:00Z",
        "advice": {"gw": 7, "buys": [{"code": 1, "frequency": 0.85}],
                   "move_frequencies": [{"kind": "buy", "code": 1, "gw": 7,
                                         "label": "buy", "count": 34,
                                         "frequency": 0.85}],
                   "raw_optimum_agrees": True,
                   "scenarios": {"n": 40, "completed": 39, "seed": 1}},
        "staleness": {"advice_gw": 7, "current_gw": 7,
                      "generated_at": "2026-10-01T00:00:00Z",
                      "deadline": "2026-10-03T10:00:00Z",
                      "deadline_passed": False, "stale": False,
                      "reason": ""},
    }
    out = AdviceLatest(**payload)
    assert out.advice["raw_optimum_agrees"] is True
    assert out.advice["scenarios"]["completed"] == 39
    assert out.advice["buys"][0]["frequency"] == 0.85
