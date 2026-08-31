"""``/api/league/sim`` and ``/api/league/whatif``.

The pattern is ``tests/test_web_league.py``'s: a FakeClient, artifacts written
into a tmp path, and every failure a readable 422 rather than a 500.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import (COMPONENT_COLS, SolveState, pool_rows,
                              save_components, save_solve_state)
from gaffer.data import store
from gaffer.web.app import create_app

STANDINGS = {"standings": {"has_next": False, "results": [
    {"entry": 1, "entry_name": "You FC", "player_name": "Me", "rank": 2,
     "last_rank": 2, "total": 106, "event_total": 55},
    {"entry": 2, "entry_name": "Ten Hag Hive", "player_name": "Riv",
     "rank": 1, "last_rank": 1, "total": 190, "event_total": 60}]}}

MY_PICKS = {"picks": [{"element": 7, "position": 1, "multiplier": 2},
                      {"element": 8, "position": 2, "multiplier": 1}]}
RIVAL_PICKS = {"picks": [{"element": 8, "position": 1, "multiplier": 2}]}


class FakeClient:
    def __init__(self, dead=False):
        self.dead = dead

    def get_league_standings(self, league_id, page=1):
        if self.dead:
            raise RuntimeError("FPL is down")
        return STANDINGS

    def get_entry_picks(self, entry_id, gw):
        if self.dead:
            raise RuntimeError("FPL is down")
        return MY_PICKS if entry_id == 1 else RIVAL_PICKS


def _comp() -> pd.DataFrame:
    rows = []
    for code, element, ep in ((100, 7, 6.0), (101, 8, 3.0)):
        row = {c: float("nan") for c in COMPONENT_COLS}
        row.update({"code": code, "element": element, "gw": 3, "ep": ep,
                    "p_play": 0.9, "p60": 0.8, "name": "x", "position": "MID",
                    "team_code": 1, "team_name": "T", "opp_code": 2,
                    "opp_name": "O", "was_home": True,
                    "kickoff_time": "2026-09-12T14:00:00Z"})
        rows.append(row)
    return pd.DataFrame(rows, columns=COMPONENT_COLS)


def _artifacts(tmp_path):
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 5\n\n[league]\nsim_n = 200\n')
    players = pd.DataFrame([
        {"code": 100, "element": 7, "name": "Salah", "position": "MID",
         "team_id": 1, "team_code": 300, "now_cost": 130, "status": "a",
         "news": "", "chance_of_playing": None, "selected_by_percent": 45.0,
         "form": 5.0, "points_per_game": 6.0, "ep_next": 6.0,
         "price_change_percent": 0.0, "price_change_calibrating": False,
         "penalties_order": 1.0, "direct_freekicks_order": None,
         "corners_and_indirect_freekicks_order": None},
        {"code": 101, "element": 8, "name": "Dud", "position": "DEF",
         "team_id": 2, "team_code": 301, "now_cost": 45, "status": "a",
         "news": "", "chance_of_playing": None, "selected_by_percent": 5.0,
         "form": 1.0, "points_per_game": 2.0, "ep_next": 2.0,
         "price_change_percent": 0.0, "price_change_calibrating": False,
         "penalties_order": None, "direct_freekicks_order": None,
         "corners_and_indirect_freekicks_order": None}])
    (tmp_path / "data" / "live").mkdir(parents=True, exist_ok=True)
    players.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    save_components(_comp(), 3)
    save_solve_state(SolveState(
        gw=3, gws=[3], deadline="2026-09-11T17:30:00Z",
        generated_at="2026-09-10T09:00:00Z", mode="weekly", bank=5,
        free_transfers=1, owned_codes=[100], lam=0.0, league_eo={100: 62.5},
        avail_by_gw={3: []},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4, "horizon": 1},
        pool=pool_rows(
            pd.DataFrame([{"code": 100, "position": "MID", "team_code": 300,
                           "cost": 130, "sell": 128}]),
            players, [100], {(100, 3): 6.4}, [3])))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr("gaffer.data.field.RAW_FIELD",
                        tmp_path / "data/raw/field")
    _artifacts(tmp_path)
    monkeypatch.setattr("gaffer.web.routers.league_sim.fpl_client",
                        lambda: FakeClient())
    monkeypatch.setattr("gaffer.web.routers.league_sim._CACHE", {})
    return TestClient(create_app())


def test_the_sim_endpoint_answers_a_league_shaped_payload(client):
    body = client.get("/api/league/sim").json()
    assert body["gw"] == 3
    assert 0.0 <= body["p_win"] <= 1.0
    assert body["p_top3"] >= body["p_win"]
    assert [r["entry"] for r in body["per_rival"]] == [2]
    assert list(body["margin_quantiles"]) == ["p05", "p25", "p50", "p75",
                                              "p95"]


def test_the_payload_says_how_it_was_produced(client):
    body = client.get("/api/league/sim").json()
    assert body["n"] == 200          # from [league] sim_n in the fixture
    assert body["seed"] > 0
    assert body["rival_drift"] == 0.5
    assert body["entries"] == 2


def test_the_field_is_reported_as_absent_when_nothing_is_banked(client):
    body = client.get("/api/league/sim").json()
    assert body["field_rate"] is None
    assert "field" in (body["notice"] or "").lower()


def test_a_repeat_call_is_served_from_the_cache(client, monkeypatch):
    """The MC is cheap but not free, and the League hub, the What-if tab and
    This Week's chip all want the same answer within a second of each other."""
    calls = {"n": 0}

    def _counting():
        calls["n"] += 1
        return FakeClient()

    monkeypatch.setattr("gaffer.web.routers.league_sim.fpl_client", _counting)
    first = client.get("/api/league/sim").json()
    second = client.get("/api/league/sim").json()
    assert calls["n"] == 1
    assert first["p_win"] == second["p_win"]


def test_the_run_is_banked_in_the_history_the_sparkline_reads(client):
    from gaffer.league_sim import load_sim_history

    body = client.get("/api/league/sim").json()
    banked = load_sim_history()
    assert [r["gw"] for r in banked] == [3]
    assert banked[0]["p_win"] == body["p_win"]
    assert [h["gw"] for h in body["history"]] == [3]


def test_the_legacy_parametric_numbers_ride_along(client):
    """Spec §3: the old ``win_probability`` output stays in the payload,
    marked legacy, until the UI has fully switched."""
    body = client.get("/api/league/sim").json()
    assert [p["name"] for p in body["legacy_win_probability"]] \
        == ["Ten Hag Hive"]


def test_a_dead_api_is_a_422_not_a_500(client, monkeypatch):
    monkeypatch.setattr("gaffer.web.routers.league_sim.fpl_client",
                        lambda: FakeClient(dead=True))
    monkeypatch.setattr("gaffer.web.routers.league_sim._CACHE", {})
    res = client.get("/api/league/sim")
    assert res.status_code == 422
    assert "retry" in res.json()["detail"].lower()


def test_no_league_id_is_a_422(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    _artifacts(tmp_path)
    (tmp_path / "config.toml").write_text('[fpl]\nentry_id = 1\nleague_id = 0\n')
    monkeypatch.setattr("gaffer.web.routers.league_sim._CACHE", {})
    res = TestClient(create_app()).get("/api/league/sim")
    assert res.status_code == 422
    assert "league_id" in res.json()["detail"]


def test_no_advice_on_disk_is_a_422(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    (tmp_path / "config.toml").write_text('[fpl]\nentry_id = 1\nleague_id = 5\n')
    monkeypatch.setattr("gaffer.web.routers.league_sim._CACHE", {})
    res = TestClient(create_app()).get("/api/league/sim")
    assert res.status_code == 422
    assert "advise" in res.json()["detail"]
