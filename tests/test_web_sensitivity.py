"""``GET /api/sensitivity`` — the banked report, or an honest empty card."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from gaffer.web.app import create_app

REPORT = {
    "gw": 5, "k": 20, "completed": 20, "failures": 0, "seed": 20260830,
    "horizon": 3, "wall_s": 141.2, "generated_at": "2026-08-31T09:00:00+00:00",
    "notice": None,
    "frequencies": [
        {"kind": "buy", "code": 23, "gw": 5, "label": "buy", "name": "Salah",
         "count": 17, "frequency": 0.85},
        {"kind": "captain", "code": 23, "gw": 5, "label": "captain",
         "name": "Salah", "count": 20, "frequency": 1.0}],
    "modal": {"count": 17, "buys": [{"code": 23, "name": "Salah",
                                     "position": "MID"}],
              "sells": [], "captain": {"code": 23, "name": "Salah",
                                       "position": "MID"},
              "chip": None, "hits": 0, "value": 210.4},
    "runner_up": {"count": 3, "buys": [], "sells": [],
                  "captain": {"code": 9, "name": "Haaland",
                              "position": "FWD"},
                  "chip": None, "hits": 0, "value": 210.0},
    "margin": 0.4,
    "verdict": "Salah appears in 17/20 re-solves; holding is within 0.4 "
               "expected points",
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text('[fpl]\nentry_id = 1\n'
                                          'league_id = 5\n')
    (tmp_path / "reports").mkdir()
    return TestClient(create_app())


def test_no_report_is_an_empty_card_not_a_404(client):
    body = client.get("/api/sensitivity").json()
    assert body["available"] is False
    assert body["frequencies"] == []
    assert body["verdict"] is None


def test_a_banked_report_is_served_whole(client, tmp_path):
    (tmp_path / "reports/solve_state_gw5.json").write_text("{}")
    (tmp_path / "reports/solve_state_gw5.parquet").write_bytes(b"")
    (tmp_path / "reports/sensitivity_gw5.json").write_text(json.dumps(REPORT))
    body = client.get("/api/sensitivity").json()
    assert body["available"] is True
    assert body["gw"] == 5 and body["completed"] == 20
    assert body["margin"] == 0.4
    assert body["frequencies"][0]["name"] == "Salah"
    assert body["modal"]["captain"]["name"] == "Salah"
    assert "17/20" in body["verdict"]


def test_a_report_for_an_older_gameweek_is_not_shown_as_this_weeks(client,
                                                                  tmp_path):
    """Last week's robustness is not this week's, and a stale card is worse
    than no card."""
    (tmp_path / "reports/solve_state_gw6.json").write_text("{}")
    (tmp_path / "reports/solve_state_gw6.parquet").write_bytes(b"")
    (tmp_path / "reports/sensitivity_gw5.json").write_text(json.dumps(REPORT))
    body = client.get("/api/sensitivity").json()
    assert body["available"] is False
    assert body["gw"] == 6
    assert "GW6" in body["notice"]


def test_a_corrupt_report_is_an_empty_card(client, tmp_path):
    (tmp_path / "reports/solve_state_gw5.json").write_text("{}")
    (tmp_path / "reports/solve_state_gw5.parquet").write_bytes(b"")
    (tmp_path / "reports/sensitivity_gw5.json").write_text("{not json")
    assert client.get("/api/sensitivity").json()["available"] is False


def test_an_explicit_gameweek_can_be_asked_for(client, tmp_path):
    (tmp_path / "reports/sensitivity_gw5.json").write_text(json.dumps(REPORT))
    body = client.get("/api/sensitivity?gw=5").json()
    assert body["available"] is True and body["gw"] == 5
