"""``GET /api/review`` — the banked ledger and its season summary.

Never an error. An unreviewed season is not a failure state, it is the state
every season starts in, so the empty ledger is a 200 with an empty body and
the hub shows a "run review" button rather than a retry.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import REPORTS
from gaffer.web.app import create_app

ROW = {
    "gw": 2, "reviewed_at": "2026-09-01T09:00:00+00:00", "no_advice": False,
    "post_deadline": False, "my_points": 61, "official_points": 61,
    "official_gross": 65, "hits": 1, "reconciled": True, "chip": None,
    "model_chip": "bboost", "points_on_bench": 5, "our_bench_points": 5,
    "model_points": 68, "accuracy": 89,
    "pwin_n": 2000, "pwin_seed": 20260831, "pwin_granularity_pp": 0.05,
    "hindsight": {"points": 74, "xi": [1, 2, 3], "captain": 3, "gap": 13},
    "misses": [{"code": 16, "name": "Guehi", "over": "Blank", "gain": 15}],
    "notices": [],
    "lanes": [
        {"lane": "transfers", "delta_pts": -7, "delta_pwin": -0.3,
         "label": "Blunder", "aligned": False, "mine": "no move",
         "model": "Blank->Guehi", "note": None},
        {"lane": "captaincy", "delta_pts": 4, "delta_pwin": 0.2,
         "label": "Brilliant", "aligned": False, "mine": "Salah",
         "model": "Haaland", "note": None},
        {"lane": "bench", "delta_pts": 0, "delta_pwin": 0.0,
         "label": "Aligned", "aligned": True, "mine": "A, B", "model": "A, B",
         "note": None},
        {"lane": "chip", "delta_pts": None, "delta_pwin": None,
         "label": None, "aligned": False, "mine": "none", "model": "wildcard",
         "note": "a wildcard or free hit changes the squad"},
    ],
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app(), raise_server_exceptions=False)


def _ledger(rows):
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "decision_ledger.json").write_text(json.dumps({"gws": rows}))


def test_an_unreviewed_season_is_an_empty_two_hundred(client):
    """Not a 422. The page shows an empty state with a Review button; a
    retry button would be telling the user to retry something that worked."""
    response = client.get("/api/review")
    assert response.status_code == 200
    assert response.json() == {"gws": [], "summary": None}


def test_the_ledger_comes_back_row_for_row(client):
    _ledger([ROW])
    body = client.get("/api/review").json()
    assert [r["gw"] for r in body["gws"]] == [2]
    assert body["gws"][0]["accuracy"] == 89
    assert [lane["lane"] for lane in body["gws"][0]["lanes"]] \
        == ["transfers", "captaincy", "bench", "chip"]


def test_a_null_lane_survives_serialisation_as_null(client):
    """The one thing the schema must not do is coerce an ungraded lane to
    zero on its way through pydantic (spec G2)."""
    _ledger([ROW])
    chip = client.get("/api/review").json()["gws"][0]["lanes"][3]
    assert chip["delta_pts"] is None
    assert chip["label"] is None


def test_the_summary_is_computed_from_the_banked_rows(client):
    _ledger([ROW])
    summary = client.get("/api/review").json()["summary"]
    assert summary["lanes"]["transfers"]["pts"] == -7
    assert summary["hindsight_gap"] == 13
    assert summary["reconciled_gws"] == 1


def test_the_misses_and_the_hindsight_eleven_ride_along(client):
    _ledger([ROW])
    row = client.get("/api/review").json()["gws"][0]
    assert row["misses"][0]["name"] == "Guehi"
    assert row["hindsight"]["gap"] == 13


def test_a_corrupt_ledger_is_an_empty_state_not_a_five_hundred(client):
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "decision_ledger.json").write_text("{ not json")
    response = client.get("/api/review")
    assert response.status_code == 200
    assert response.json()["gws"] == []


def test_a_row_missing_half_its_fields_still_renders(client):
    """Ledgers written by an older build must not take the page down: every
    field but the gameweek has a default."""
    _ledger([{"gw": 1}])
    body = client.get("/api/review").json()
    assert body["gws"][0]["gw"] == 1
    assert body["gws"][0]["lanes"] == []
    assert body["gws"][0]["accuracy"] is None
