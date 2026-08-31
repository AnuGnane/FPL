"""``/api/confidence`` and the sensitivity card's noise comparison.

Both are read paths on pages that already work, so neither may ever fail: an
unreviewed season, a corrupt ledger and a clone with no reports directory all
come back as a 200 whose sentence says so.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import SolveState, save_components, save_solve_state
from gaffer.web.app import create_app

GW = 5

COMPONENTS = pd.DataFrame([
    {"code": 11, "element": 1, "name": "Saka", "position": "MID",
     "team_code": 3, "team_name": "Arsenal", "gw": GW, "opp_code": 4,
     "opp_name": "City", "was_home": 1.0, "kickoff_time": None,
     "p_play": 0.95, "p60": 0.9, "ep": 5.0},
    {"code": 22, "element": 2, "name": "Sub", "position": "FWD",
     "team_code": 4, "team_name": "City", "gw": GW, "opp_code": 3,
     "opp_name": "Arsenal", "was_home": 0.0, "kickoff_time": None,
     "p_play": 0.3, "p60": 0.1, "ep": 1.5},
])

POOL = pd.DataFrame([
    {"code": 11, "name": "Saka", "position": "MID", "team_code": 3,
     "cost": 100, "sell": 100, "owned": True, "gw": GW, "ep_raw": 5.0},
    {"code": 22, "name": "Sub", "position": "FWD", "team_code": 4,
     "cost": 60, "sell": 60, "owned": False, "gw": GW, "ep_raw": 1.5},
])

SENSITIVITY = {
    "gw": GW, "k": 40, "completed": 40, "failures": 0, "seed": 7,
    "horizon": 1, "generated_at": "2026-08-31T09:00:00Z", "frequencies": [],
    "modal": {"count": 30, "buys": [{"code": 11, "name": "Saka"}],
              "sells": [], "captain": None, "hits": 0, "value": 60.0},
    "runner_up": {"count": 10, "buys": [{"code": 22, "name": "Sub"}],
                  "sells": [], "captain": None, "hits": 0, "value": 59.4},
    "margin": 0.6, "verdict": "…"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    save_components(COMPONENTS, GW)
    save_solve_state(SolveState(
        gw=GW, gws=[GW], deadline="2026-09-01T11:00:00Z",
        generated_at="2026-08-31T09:00:00Z", mode="weekly", bank=0,
        free_transfers=1, owned_codes=[11], lam=0.0, league_eo={},
        avail_by_gw={GW: []},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.0, "horizon": 1, "hit_cost": 4,
             "max_transfers": 2, "bank_weight": 0.0},
        pool=POOL))
    return TestClient(create_app())


def _ledger(tmp_path, rows):
    (tmp_path / "reports/decision_ledger.json").write_text(
        json.dumps({"gws": rows}))


def test_an_unreviewed_season_is_a_200_saying_so(client):
    body = client.get("/api/confidence").json()
    assert body["captain"]["tier"] == "early"
    assert body["captain"]["graded"] == 0
    assert "too early" in body["captain"]["text"].lower()


def test_a_corrupt_ledger_is_an_unreviewed_one(client, tmp_path):
    (tmp_path / "reports/decision_ledger.json").write_text("{not json")
    assert client.get("/api/confidence").json()["captain"]["tier"] == "early"


def test_a_graded_season_quotes_its_counts(client, tmp_path):
    _ledger(tmp_path, [
        {"gw": g, "lanes": [{"lane": "captaincy", "delta_pts": -2,
                             "aligned": False}]}
        for g in range(1, 6)])
    body = client.get("/api/confidence").json()
    assert body["captain"]["tier"] == "backed"
    assert "5 of 5" in body["captain"]["text"]


# --- the sensitivity noise comparison ---------------------------------

def test_the_report_carries_the_noise_on_the_players_that_separate_the_plans(
        client, tmp_path):
    """A6: quadrature over the symmetric difference, on the *estimation* σ.

    Deliberately not the band's σ, and this test is where the two part
    company. A band prices what a player might score; a margin between two
    plans solved off the same board can only be threatened by forecast error,
    so folding football's variance in here would inflate every comparison into
    a coin flip. The assertion below fails if this line ever quietly starts
    reading ``band_for``.
    """
    import math

    from gaffer.uncertainty import (band_for, estimation_sigma_for,
                                    xmins_by_player_gw)

    (tmp_path / f"reports/sensitivity_gw{GW}.json").write_text(
        json.dumps(SENSITIVITY))
    body = client.get("/api/sensitivity").json()
    xm = xmins_by_player_gw(COMPONENTS)
    cells = ((11, 5.0), (22, 1.5))
    want = math.sqrt(sum(estimation_sigma_for(ep, xm[(code, GW)]) ** 2
                         for code, ep in cells))
    assert body["decision_sigma"] == pytest.approx(round(want, 3))
    banded = math.sqrt(sum(band_for(ep, xm[(code, GW)]).sigma ** 2
                           for code, ep in cells))
    assert body["decision_sigma"] < banded / 2


def test_no_runner_up_is_no_comparison(client, tmp_path):
    payload = {**SENSITIVITY, "runner_up": None, "margin": None}
    (tmp_path / f"reports/sensitivity_gw{GW}.json").write_text(
        json.dumps(payload))
    assert client.get("/api/sensitivity").json()["decision_sigma"] is None


def test_no_components_file_is_no_comparison(client, tmp_path):
    (tmp_path / f"reports/sensitivity_gw{GW}.json").write_text(
        json.dumps(SENSITIVITY))
    (tmp_path / f"reports/components_gw{GW}.parquet").unlink()
    body = client.get("/api/sensitivity")
    assert body.status_code == 200
    assert body.json()["decision_sigma"] is None


def test_the_rest_of_the_sensitivity_payload_is_untouched(client, tmp_path):
    (tmp_path / f"reports/sensitivity_gw{GW}.json").write_text(
        json.dumps(SENSITIVITY))
    body = client.get("/api/sensitivity").json()
    assert body["available"] is True
    assert body["margin"] == pytest.approx(0.6)
    assert body["modal"]["count"] == 30
