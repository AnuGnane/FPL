"""v16 §5 — the note beside the grade on /api/review, and the tally."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import REPORTS
from gaffer.web.app import create_app
from tests.test_web_review import ROW


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    REPORTS.mkdir()
    (REPORTS / "decision_ledger.json").write_text(json.dumps({"gws": [ROW]}))
    return TestClient(create_app(), raise_server_exceptions=False)


def test_a_note_rides_on_its_gameweek_and_the_tally_on_the_summary(client):
    (REPORTS / "decisions.json").write_text(json.dumps(
        {"2": {"gw": 2, "reason": "injury", "text": "Rice was out",
               "at": "2026-09-01T10:00:00+00:00"}}))
    body = client.get("/api/review").json()
    assert body["gws"][0]["decision"] == {"reason": "injury", "text": "Rice was out",
                                          "at": "2026-09-01T10:00:00+00:00"}
    assert body["summary"]["by_reason"] == [
        {"reason": "injury", "count": 1, "mean_delta_pts": -7.0}]


def test_no_note_is_null_and_counts_under_none(client):
    body = client.get("/api/review").json()
    assert body["gws"][0]["decision"] is None
    assert body["summary"]["by_reason"] == [
        {"reason": "none", "count": 1, "mean_delta_pts": -7.0}]


def test_an_empty_ledger_is_still_the_empty_review(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    body = TestClient(create_app()).get("/api/review").json()
    assert body == {"gws": [], "summary": None}
