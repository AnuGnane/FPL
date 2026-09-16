"""v19e §2.1 — ``/api/advice/diff?a=&b=``: one gameweek's newest plan against
another's, through the same comparison and the same never-an-error contract
as the one-parameter strip. The route pin does not move: it is the same
path."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from gaffer.web.app import create_app


def _advice(gw, captain, buys, pts):
    return {"gw": gw, "buys": buys, "sells": [], "expected_pts": pts,
            "captain": {"code": captain, "name": f"P{captain}"}}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports/gw4-advice.json").write_text(json.dumps(
        _advice(4, 11, [{"code": 1, "name": "P1"}], 58.0)))
    (tmp_path / "reports/gw5-advice.json").write_text(json.dumps(
        _advice(5, 12, [{"code": 2, "name": "P2"}], 61.5)))
    return TestClient(create_app())


def test_two_gameweeks_are_compared_newest_plan_against_newest_plan(client):
    body = client.get("/api/advice/diff?a=4&b=5").json()
    assert body["available"] is True
    assert (body["gw_from"], body["gw_to"], body["gw"]) == (4, 5, 5)
    assert body["captain_from"]["code"] == 11
    assert body["captain_to"]["code"] == 12
    assert [p["code"] for p in body["buys_added"]] == [2]
    assert [p["code"] for p in body["buys_dropped"]] == [1]
    assert body["expected_pts_delta"] == pytest.approx(3.5)


def test_a_without_b_is_the_one_parameter_path(client):
    """The strip must never be an error, so a half-given pair falls back to
    "this gameweek against its previous run" rather than a 422."""
    response = client.get("/api/advice/diff?a=4")
    assert response.status_code == 200
    body = response.json()
    assert body["gw_from"] is None and body["gw_to"] is None


def test_a_gameweek_with_no_plan_is_unavailable_not_an_error(client):
    body = client.get("/api/advice/diff?a=3&b=5").json()
    assert body["available"] is False
    assert (body["gw_from"], body["gw_to"]) == (3, 5)


def test_the_same_gameweek_strip_is_unchanged(client):
    """No history directory, so a first run: the old answer, byte for byte in
    the fields that existed before v19e."""
    body = client.get("/api/advice/diff?gw=5").json()
    assert body["available"] is False and body["gw"] == 5
    assert body["gw_from"] is None
