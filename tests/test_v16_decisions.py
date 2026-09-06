"""v16 §5 — the deviation note: store, refusals, the deadline rule, the tally."""
from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer import artifacts
from gaffer.decisions import (REASONS, TEXT_MAX, by_reason, load_decisions,
                              note_for, note_state, save_note)
from gaffer.web.app import create_app

NOW = pd.Timestamp("2026-09-05T12:00:00Z")


@pytest.fixture()
def reports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    artifacts.REPORTS.mkdir()
    return artifacts.REPORTS


def _advice(reports, gw, deadline):
    (reports / f"gw{gw}-advice.json").write_text(json.dumps(
        {"gw": gw, "deadline": deadline, "buys": [], "sells": []}))


def _ledger(reports, rows):
    (reports / "decision_ledger.json").write_text(json.dumps({"gws": rows}))


def _row(gw, delta):
    return {"gw": gw, "lanes": [{"lane": "transfers", "delta_pts": delta,
                                 "label": "Good" if delta > 0 else "Blunder"}]}


def test_the_eight_reasons_and_the_text_cap():
    assert REASONS == ("injury", "fixtures", "eye_test", "price", "chip",
                       "rival", "gut", "other")
    assert TEXT_MAX == 280


def test_an_absent_note_is_the_empty_shape(reports):
    assert note_for(4) == {"gw": 4, "reason": None, "text": "", "at": None}


def test_save_round_trips_and_stamps(reports):
    out = save_note(4, "injury", "Rice was 0% to play")
    assert out["reason"] == "injury" and out["text"] == "Rice was 0% to play"
    assert out["at"].endswith("+00:00")
    assert note_for(4) == out
    assert load_decisions() == {4: out}
    save_note(4, "gut", "")
    assert note_for(4)["reason"] == "gut" and len(load_decisions()) == 1


def test_a_corrupt_store_reads_as_empty(reports):
    (reports / "decisions.json").write_text("{not json")
    assert load_decisions() == {}


def test_save_refuses_a_bad_reason_and_long_text(reports):
    with pytest.raises(ValueError, match="reason"):
        save_note(4, "vibes", "")
    with pytest.raises(ValueError, match="280"):
        save_note(4, "gut", "x" * 281)


def test_state_before_the_deadline_open_after_and_graded_once_banked(reports):
    _advice(reports, 4, "2026-09-06T17:30:00Z")
    assert note_state(4, now=NOW)[0] == "before_deadline"
    assert note_state(4, now=pd.Timestamp("2026-09-07T12:00:00Z"))[0] == "open"
    _ledger(reports, [_row(4, -7)])
    state, deadline, grade = note_state(4, now=pd.Timestamp("2026-09-10T12:00:00Z"))
    assert state == "graded" and deadline == "2026-09-06T17:30:00Z"
    assert grade == {"lane": "transfers", "label": "Blunder", "delta_pts": -7}


def test_no_advice_and_no_snapshot_means_open(reports):
    assert note_state(9, now=NOW) == ("open", None, None)


def test_the_by_reason_tally(reports):
    save_note(2, "injury", "")
    save_note(3, "injury", "")
    save_note(4, "gut", "")
    ledger = [_row(1, 0), _row(2, -7), _row(3, 3), _row(4, 5),
              {"gw": 5, "lanes": [{"lane": "transfers", "delta_pts": None}]}]
    assert by_reason(ledger, load_decisions()) == [
        {"reason": "injury", "count": 2, "mean_delta_pts": -2.0},
        {"reason": "gut", "count": 1, "mean_delta_pts": 5.0},
        {"reason": "none", "count": 1, "mean_delta_pts": 0.0}]


# --- the routes -----------------------------------------------------------

@pytest.fixture()
def client(reports, monkeypatch):
    monkeypatch.setattr("gaffer.web.routers.decisions.upcoming_gw", lambda: 5)
    monkeypatch.setattr("gaffer.web.routers.decisions._now",
                        lambda: pd.Timestamp("2026-09-07T12:00:00Z"))
    return TestClient(create_app())


def test_get_is_never_a_404(client):
    body = client.get("/api/decisions/4").json()
    assert body == {"gw": 4, "reason": None, "text": "", "at": None,
                    "state": "open", "deadline": None, "grade": None}


def test_post_saves_and_get_reads_it_back(client, reports):
    _advice(reports, 4, "2026-09-06T17:30:00Z")
    resp = client.post("/api/decisions/4", json={"reason": "fixtures", "text": "easier run"})
    assert resp.status_code == 200, resp.text
    body = client.get("/api/decisions/4").json()
    assert body["reason"] == "fixtures" and body["text"] == "easier run"
    assert body["state"] == "open" and body["deadline"] == "2026-09-06T17:30:00Z"


@pytest.mark.parametrize("payload, constraint", [
    ({"reason": "vibes", "text": ""}, "unknown_reason"),
    ({"reason": "gut", "text": "x" * 281}, "text_too_long"),
])
def test_post_refuses_in_the_settings_shape(client, payload, constraint):
    resp = client.post("/api/decisions/4", json=payload)
    assert resp.status_code == 422
    assert resp.json()["detail"]["constraint"] == constraint
    assert resp.json()["detail"]["players"] == []


def test_post_refuses_a_gameweek_past_the_next_deadline(client):
    resp = client.post("/api/decisions/6", json={"reason": "gut", "text": ""})
    assert resp.status_code == 422
    assert resp.json()["detail"]["constraint"] == "future_gw"


def test_post_refuses_before_the_deadline_and_after_grading(client, reports):
    _advice(reports, 5, "2026-09-11T17:30:00Z")
    resp = client.post("/api/decisions/5", json={"reason": "gut", "text": ""})
    assert resp.status_code == 422 and resp.json()["detail"]["constraint"] == "not_open"
    _advice(reports, 4, "2026-09-06T17:30:00Z")
    _ledger(reports, [_row(4, 3)])
    resp = client.post("/api/decisions/4", json={"reason": "gut", "text": ""})
    assert resp.status_code == 422 and resp.json()["detail"]["constraint"] == "graded"
    body = client.get("/api/decisions/4").json()
    assert body["state"] == "graded" and body["grade"]["delta_pts"] == 3
