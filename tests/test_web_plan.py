"""GET /api/plan/{gw} — the already-solved horizon out of the advice artifact.

No solver runs here and none may: the endpoint reads what `gaffer advise`
already wrote (spec §6.1).
"""

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import SolveState, pool_rows, save_solve_state
from gaffer.web.app import create_app

ADVICE = {
    "gw": 5, "deadline": "2099-09-18T17:30:00Z",
    "buys": [{"code": 100, "name": "Salah", "position": "MID", "ep": 6.4}],
    "sells": [{"code": 101, "name": "Dud", "position": "DEF", "ep": 1.9}],
    "hits": 1,
    "xi": [{"code": 100, "name": "Salah", "position": "MID", "ep": 6.4}],
    "bench": [], "captain": {"code": 100, "name": "Salah", "position": "MID",
                             "ep": 6.4},
    "vice": {"code": 101, "name": "Dud", "position": "DEF", "ep": 1.9},
    "captain_options": [],
    "chip_table": [{"chip": "bboost", "gw": 6, "gain": 8.2, "play_now": True}],
    "wildcard_now": None, "alternatives": [], "threats": [],
    "price_alerts": [], "expected_pts": 61.5,
    "plan_by_gw": [
        {"gw": 5, "hits": 1, "expected_pts": 61.5,
         "buys": [{"code": 100, "name": "Salah", "position": "MID", "ep": 6.4}],
         "sells": [{"code": 101, "name": "Dud", "position": "DEF", "ep": 1.9}]},
        {"gw": 6, "hits": 0, "expected_pts": 58.0, "buys": [], "sells": []},
    ],
    "mode": "weekly",
}


def _write(root):
    (root / "reports").mkdir(exist_ok=True)
    (root / "reports" / "gw5-advice.json").write_text(json.dumps(ADVICE))
    pool = pool_rows(
        pd.DataFrame([
            {"code": 100, "position": "MID", "team_code": 300, "cost": 130,
             "sell": 128},
            {"code": 101, "position": "DEF", "team_code": 301, "cost": 45,
             "sell": 44},
        ]),
        pd.DataFrame([{"code": 100, "name": "Salah"},
                      {"code": 101, "name": "Dud"}]),
        owned_codes=[101], ep_by={(100, 5): 6.4, (101, 5): 1.9,
                                  (100, 6): 6.0, (101, 6): 1.8},
        gws=[5, 6])
    save_solve_state(SolveState(
        gw=5, gws=[5, 6], deadline="2099-09-18T17:30:00Z",
        generated_at="2026-08-29T09:00:00Z", mode="weekly", bank=12,
        free_transfers=1, owned_codes=[101], lam=0.0, league_eo={},
        avail_by_gw={5: ["bboost"], 6: ["bboost"]},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4, "horizon": 2},
        pool=pool))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(tmp_path)
    return TestClient(create_app(), raise_server_exceptions=False)


def test_one_column_per_horizon_gameweek(client):
    body = client.get("/api/plan/5").json()
    assert body["gw"] == 5
    assert [w["gw"] for w in body["weeks"]] == [5, 6]
    assert body["generated_at"] == "2026-08-29T09:00:00Z"


def test_moves_carry_prices_from_the_saved_pool(client):
    week = client.get("/api/plan/5").json()["weeks"][0]
    assert week["buys"][0] == {"code": 100, "name": "Salah",
                               "position": "MID", "ep": 6.4, "price": 13.0}
    # A sell is priced at what you get for it, not at what it costs to buy.
    assert week["sells"][0]["price"] == 4.4


def test_hits_are_priced_explicitly(client):
    weeks = client.get("/api/plan/5").json()["weeks"]
    assert weeks[0]["hits"] == 1 and weeks[0]["hit_cost"] == 4
    assert weeks[1]["hits"] == 0 and weeks[1]["hit_cost"] == 0


def test_the_recommended_chip_lands_on_its_own_gameweek(client):
    weeks = client.get("/api/plan/5").json()["weeks"]
    assert weeks[0]["chip"] is None
    assert weeks[1]["chip"] == "bboost"


def test_captain_and_vice_are_the_head_weeks_only(client):
    weeks = client.get("/api/plan/5").json()["weeks"]
    assert weeks[0]["captain"]["name"] == "Salah"
    assert weeks[0]["vice"]["name"] == "Dud"
    # plan_by_gw records no armband for later weeks and re-deriving one would
    # mean re-solving, which this endpoint never does (spec §6.1).
    assert weeks[1]["captain"] is None and weeks[1]["vice"] is None


def test_a_gameweek_with_no_advice_is_a_friendly_404_not_a_500(client):
    resp = client.get("/api/plan/9")
    assert resp.status_code == 404
    assert "gaffer advise" in resp.json()["detail"]


def test_a_cold_clone_is_a_404_not_a_500(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app(), raise_server_exceptions=False)
    resp = client.get("/api/plan/5")
    assert resp.status_code == 404
    assert "gaffer advise" in resp.json()["detail"]


def test_an_advice_payload_with_no_plan_by_gw_still_answers(tmp_path,
                                                            monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(tmp_path)
    (tmp_path / "reports" / "gw5-advice.json").write_text(
        json.dumps({**ADVICE, "plan_by_gw": []}))
    client = TestClient(create_app(), raise_server_exceptions=False)
    body = client.get("/api/plan/5").json()
    assert body["weeks"] == []


# --- artifact drift ---------------------------------------------------------
#
# The advice JSON on disk was written by whatever version of `gaffer advise`
# last ran, which need not be this one. Five reads here took its shape on
# trust, and each was a 500 on a timeline that should have degraded a field and
# drawn the rest.


def _with(tmp_path, monkeypatch, advice):
    monkeypatch.chdir(tmp_path)
    _write(tmp_path)
    (tmp_path / "reports" / "gw5-advice.json").write_text(json.dumps(advice))
    return TestClient(create_app(), raise_server_exceptions=False)


def test_a_captain_with_no_code_drops_the_armband_not_the_timeline(
        tmp_path, monkeypatch):
    client = _with(tmp_path, monkeypatch,
                   {**ADVICE, "captain": {"name": "Salah"}})
    resp = client.get("/api/plan/5")
    assert resp.status_code == 200
    weeks = resp.json()["weeks"]
    assert weeks[0]["captain"] is None
    assert weeks[0]["vice"]["name"] == "Dud"        # the rest is unharmed
    assert len(weeks) == 2


def test_a_captain_that_is_not_a_dict_is_ignored(tmp_path, monkeypatch):
    client = _with(tmp_path, monkeypatch, {**ADVICE, "captain": "Salah"})
    body = client.get("/api/plan/5").json()
    assert body["weeks"][0]["captain"] is None


def test_a_non_numeric_hits_count_reads_as_none_taken(tmp_path, monkeypatch):
    plan = [{**ADVICE["plan_by_gw"][0], "hits": "one"},
            ADVICE["plan_by_gw"][1]]
    client = _with(tmp_path, monkeypatch, {**ADVICE, "plan_by_gw": plan})
    resp = client.get("/api/plan/5")
    assert resp.status_code == 200
    assert resp.json()["weeks"][0]["hits"] == 0
    assert resp.json()["weeks"][0]["hit_cost"] == 0


def test_a_non_numeric_ep_on_a_move_reads_as_zero(tmp_path, monkeypatch):
    plan = [{**ADVICE["plan_by_gw"][0],
             "buys": [{"code": 100, "name": "Salah", "ep": "lots"}]},
            ADVICE["plan_by_gw"][1]]
    client = _with(tmp_path, monkeypatch, {**ADVICE, "plan_by_gw": plan})
    resp = client.get("/api/plan/5")
    assert resp.status_code == 200
    assert resp.json()["weeks"][0]["buys"][0]["ep"] == 0.0


def test_a_move_with_no_code_is_dropped_not_fatal(tmp_path, monkeypatch):
    plan = [{**ADVICE["plan_by_gw"][0],
             "buys": [{"name": "Nameless"},
                      {"code": 100, "name": "Salah", "ep": 6.4}]},
            ADVICE["plan_by_gw"][1]]
    client = _with(tmp_path, monkeypatch, {**ADVICE, "plan_by_gw": plan})
    resp = client.get("/api/plan/5")
    assert resp.status_code == 200
    buys = resp.json()["weeks"][0]["buys"]
    assert [b["name"] for b in buys] == ["Salah"]


def test_a_plan_by_gw_written_as_a_dict_is_read_by_its_values(tmp_path,
                                                               monkeypatch):
    """An older writer keyed the horizon by gameweek. Iterating that yields
    the string keys, and `"5".get(...)` is an AttributeError, not a plan."""
    plan = {"5": ADVICE["plan_by_gw"][0], "6": ADVICE["plan_by_gw"][1]}
    client = _with(tmp_path, monkeypatch, {**ADVICE, "plan_by_gw": plan})
    resp = client.get("/api/plan/5")
    assert resp.status_code == 200
    assert [w["gw"] for w in resp.json()["weeks"]] == [5, 6]


def test_a_plan_entry_that_is_not_a_dict_is_skipped(tmp_path, monkeypatch):
    plan = ["nonsense", ADVICE["plan_by_gw"][1]]
    client = _with(tmp_path, monkeypatch, {**ADVICE, "plan_by_gw": plan})
    resp = client.get("/api/plan/5")
    assert resp.status_code == 200
    assert [w["gw"] for w in resp.json()["weeks"]] == [6]


def test_a_chip_row_with_a_null_gameweek_is_ignored(tmp_path, monkeypatch):
    chips = [{"chip": "bboost", "gw": None, "play_now": True},
             {"chip": "freehit", "gw": 6, "play_now": True}]
    client = _with(tmp_path, monkeypatch, {**ADVICE, "chip_table": chips})
    resp = client.get("/api/plan/5")
    assert resp.status_code == 200
    weeks = resp.json()["weeks"]
    assert weeks[1]["chip"] == "freehit"


def test_a_chip_table_that_is_not_a_list_costs_only_the_chips(tmp_path,
                                                              monkeypatch):
    client = _with(tmp_path, monkeypatch, {**ADVICE, "chip_table": "bboost"})
    resp = client.get("/api/plan/5")
    assert resp.status_code == 200
    assert all(w["chip"] is None for w in resp.json()["weeks"])


def test_a_non_numeric_hit_cost_falls_back_to_four(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(tmp_path)
    state = json.loads(
        (tmp_path / "reports" / "solve_state_gw5.json").read_text())
    state["opt"]["hit_cost"] = "four"
    (tmp_path / "reports" / "solve_state_gw5.json").write_text(
        json.dumps(state))
    client = TestClient(create_app(), raise_server_exceptions=False)
    resp = client.get("/api/plan/5")
    assert resp.status_code == 200
    assert resp.json()["weeks"][0]["hit_cost"] == 4


def test_a_plan_entry_with_no_gameweek_is_skipped(tmp_path, monkeypatch):
    plan = [{"hits": 0, "buys": [], "sells": []}, ADVICE["plan_by_gw"][1]]
    client = _with(tmp_path, monkeypatch, {**ADVICE, "plan_by_gw": plan})
    resp = client.get("/api/plan/5")
    assert resp.status_code == 200
    assert [w["gw"] for w in resp.json()["weeks"]] == [6]
