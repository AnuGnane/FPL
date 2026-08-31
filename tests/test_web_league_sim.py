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
     "last_rank": 2, "total": 170, "event_total": 55},
    {"entry": 2, "entry_name": "Ten Hag Hive", "player_name": "Riv",
     "rank": 1, "last_rank": 1, "total": 190, "event_total": 60}]}}

MY_PICKS = {"picks": [{"element": 7, "position": 1, "multiplier": 2},
                      {"element": 8, "position": 2, "multiplier": 1}]}
RIVAL_PICKS = {"picks": [{"element": 9, "position": 1, "multiplier": 2},
                         {"element": 8, "position": 2, "multiplier": 1}]}


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
    for code, element, ep in ((100, 7, 6.0), (101, 8, 3.0), (102, 9, 6.0)):
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
         "corners_and_indirect_freekicks_order": None},
        {"code": 102, "element": 9, "name": "Rival Ace", "position": "MID",
         "team_id": 3, "team_code": 302, "now_cost": 125, "status": "a",
         "news": "", "chance_of_playing": None, "selected_by_percent": 40.0,
         "form": 5.0, "points_per_game": 6.0, "ep_next": 6.0,
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


# --- the what-if panel -----------------------------------------------------


def test_no_pins_at_all_reproduces_the_sim_endpoint(client):
    """G3's rail: an empty what-if is the baseline, exactly, or the panel's
    deltas are measuring the panel rather than the pins."""
    base = client.get("/api/league/sim").json()
    body = client.post("/api/league/whatif", json={"pins": []}).json()
    assert body["p_win"] == base["p_win"]
    assert body["baseline_p_win"] == base["p_win"]
    assert body["delta_p_win"] == 0.0
    assert body["delta_rank"] == 0.0


def test_blanking_my_captain_costs_me_title_odds(client):
    body = client.post("/api/league/whatif",
                       json={"pins": [{"code": 100, "event": "blank"}]}).json()
    assert body["delta_p_win"] < 0.0
    assert body["p_win"] < body["baseline_p_win"]


def test_a_haul_by_my_captain_pays(client):
    body = client.post("/api/league/whatif",
                       json={"pins": [{"code": 100, "event": "haul"}]}).json()
    assert body["delta_p_win"] > 0.0


def test_scoring_a_player_at_his_forecast_is_close_to_no_event(client):
    """"score" means "he does what we already expect", so the delta is the
    variance removed and nothing else — a small number, not a swing."""
    base = client.get("/api/league/sim").json()
    body = client.post("/api/league/whatif",
                       json={"pins": [{"code": 100, "event": "score"}]}).json()
    assert abs(body["p_win"] - base["p_win"]) < 0.2


def test_the_table_names_every_entry_and_marks_me(client):
    body = client.post("/api/league/whatif", json={"pins": []}).json()
    assert [r["entry"] for r in body["table"]] == [2, 1]
    assert [r["is_you"] for r in body["table"]] == [False, True]
    assert sum(r["p_win"] for r in body["table"]) == pytest.approx(1.0,
                                                                  abs=0.01)


def test_a_captain_override_is_priced(client):
    body = client.post("/api/league/whatif",
                       json={"captain_override": 101}).json()
    assert body["delta_p_win"] < 0.0


def test_a_rival_captain_blank_helps(client):
    body = client.post("/api/league/whatif",
                       json={"rival_captain_blanks": 2}).json()
    assert body["delta_p_win"] >= 0.0


def test_an_unknown_code_is_reported_rather_than_silently_dropped(client):
    """A stale tab pinning a transferred-out player must be told, not
    humoured: a panel that answers a question it did not understand is worse
    than one that refuses."""
    body = client.post("/api/league/whatif",
                       json={"pins": [{"code": 999, "event": "blank"}]}).json()
    assert body["unknown_codes"] == [999]
    assert body["delta_p_win"] == 0.0


def test_an_unknown_event_name_is_a_422(client):
    res = client.post("/api/league/whatif",
                      json={"pins": [{"code": 100, "event": "hattrick"}]})
    assert res.status_code == 422
    assert "hattrick" in res.json()["detail"]


def test_the_whatif_reuses_the_cached_inputs_and_fetches_nothing(client,
                                                                 monkeypatch):
    calls = {"n": 0}

    def _counting():
        calls["n"] += 1
        return FakeClient()

    monkeypatch.setattr("gaffer.web.routers.league_sim.fpl_client", _counting)
    client.get("/api/league/sim")
    client.post("/api/league/whatif",
                json={"pins": [{"code": 100, "event": "blank"}]})
    assert calls["n"] == 1


def test_the_whatif_does_not_bank_a_history_row(client):
    """The sparkline is a record of the league, not of the user's fiddling."""
    from gaffer.league_sim import load_sim_history

    client.get("/api/league/sim")
    client.post("/api/league/whatif",
                json={"pins": [{"code": 100, "event": "blank"}]})
    assert len(load_sim_history()) == 1


def test_a_dead_api_is_a_422_here_too(client, monkeypatch):
    monkeypatch.setattr("gaffer.web.routers.league_sim.fpl_client",
                        lambda: FakeClient(dead=True))
    monkeypatch.setattr("gaffer.web.routers.league_sim._CACHE", {})
    res = client.post("/api/league/whatif", json={"pins": []})
    assert res.status_code == 422


# --- the projected table is the engine's own count -------------------------


TEN = {"standings": {"has_next": False, "results": (
    [{"entry": 1, "entry_name": "You FC", "player_name": "Me", "rank": 9,
      "last_rank": 9, "total": 200, "event_total": 55}]
    + [{"entry": i, "entry_name": f"Rival {i}", "player_name": f"R{i}",
        "rank": 11 - i, "last_rank": 11 - i, "total": 180 + 10 * i,
        "event_total": 55} for i in range(2, 11)])}}


class TenClient(FakeClient):
    """Ten entries on identical squads and a ladder of totals — the shape a
    mini-league has in March, and the one that exposed the folded column."""

    def get_league_standings(self, league_id, page=1):
        return TEN

    def get_entry_picks(self, entry_id, gw):
        return MY_PICKS


def test_the_whatif_table_is_the_engines_own_win_frequencies(client,
                                                             monkeypatch):
    """Not a renormalisation of ``p_beat``: every cell is the frequency the
    same scored matrix counted, so the panel and the headline cannot
    disagree about who is winning."""
    monkeypatch.setattr("gaffer.web.routers.league_sim.fpl_client",
                        lambda: TenClient())
    monkeypatch.setattr("gaffer.web.routers.league_sim._CACHE", {})
    body = client.post("/api/league/whatif", json={"pins": []}).json()
    from gaffer.web.routers.league_sim import _CACHE

    (sim, _inputs), = _CACHE.values()
    assert {r["entry"]: r["p_win"] for r in body["table"]} \
        == {int(k): v for k, v in sim.p_win_by_entry.items()}
    assert sum(r["p_win"] for r in body["table"]) == pytest.approx(1.0,
                                                                  abs=0.005)
    mine, = [r for r in body["table"] if r["is_you"]]
    assert mine["p_win"] == body["p_win"]


def test_the_leaders_row_is_not_a_pairwise_share(client, monkeypatch):
    """The reviewer's measurement, reproduced: the folded number the panel
    used to print is a long way from the counted one."""
    monkeypatch.setattr("gaffer.web.routers.league_sim.fpl_client",
                        lambda: TenClient())
    monkeypatch.setattr("gaffer.web.routers.league_sim._CACHE", {})
    body = client.post("/api/league/whatif", json={"pins": []}).json()
    from gaffer.web.routers.league_sim import _CACHE

    (sim, _inputs), = _CACHE.values()
    beats = {int(r["entry"]): float(r["p_beat"]) for r in sim.per_rival}
    losing = sum(1.0 - b for b in beats.values())
    leader = max(beats, key=lambda e: 1.0 - beats[e])
    folded = (1.0 - sim.p_win) * (1.0 - beats[leader]) / losing
    counted, = [r["p_win"] for r in body["table"] if r["entry"] == leader]
    assert counted > 0.2
    assert abs(folded - counted) > 0.1
