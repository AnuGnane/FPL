"""Both availability reports on the wire, off the artifact already served.

``routers/quality.py:32-48`` does ``Quality(**stored)`` over
``reports/evaluation.json``. Undeclared keys are dropped by pydantic, silently
— which is exactly how ``news_shadow`` was written for a whole cycle and never
reached the page (``schemas.py:958-960`` records it). So the assertion that
matters here is not that the field exists; it is that a payload written by the
scorer survives the trip.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from gaffer.web.app import create_app

FLAG_LATENCY = {
    "run_at": "2026-09-05T10:00:00+00:00", "git_sha": "abc1234",
    "kind": "flag_latency", "available": True, "rows": 2, "note": None,
    "snap_dates": 15, "min_snap_dates": 14, "covered_gws": [3],
    "checked_covered_gws": [3],
    "histogram": [{"bucket": "1-2d", "started": 1, "missed": 1}],
    "late_flags": [{"gw": 3, "code": 7, "first_change": "2026-09-03",
                    "lead_days": 1.73, "from_status": "a",
                    "final_status": "i", "chance_of_playing": 0.0,
                    "started": True}],
    "changes": [{"gw": 3, "code": 7, "first_change": "2026-09-03",
                 "lead_days": 1.73, "from_status": "a", "final_status": "i",
                 "chance_of_playing": 0.0, "started": True}],
}

PRESSER = {
    "run_at": "2026-09-05T10:00:00+00:00", "git_sha": "abc1234",
    "kind": "presser_grades", "available": True, "rows": 4, "note": None,
    "verdicts_banked": 9, "graded_gws": [3], "absent_rows": 3,
    "confusion": [{"verdict": "ruled_out", "n": 4, "started": 1,
                   "not_started": 3}],
    "per_class": [{"verdict": "ruled_out", "n": 4, "precision": 0.75,
                   "recall": 1.0}],
    "by_source": [{"source": "premierinjuries", "rows": 4}],
    "recall_population": "verdict-carrying rows",
}


@pytest.fixture()
def served(tmp_path, monkeypatch):
    def install(payload: dict):
        from gaffer import evaluation

        path = tmp_path / "evaluation.json"
        path.write_text(json.dumps(payload))
        monkeypatch.setattr(evaluation, "EVALUATION_PATH", path)
        return TestClient(create_app())
    return install


def test_both_reports_reach_the_page(served):
    body = served({"flag_latency": FLAG_LATENCY,
                   "presser_grades": PRESSER}).get("/api/quality").json()
    assert body["flag_latency"]["late_flags"][0]["code"] == 7
    assert body["presser_grades"]["per_class"][0]["precision"] == 0.75


def test_the_raw_change_rows_stay_off_the_wire(served):
    """The artifact keeps every change row — it is the evidence behind the
    histogram and a reader may want their own bands over it. The wire does
    not: nothing on the page reads it, and it is the one field on either
    payload that grows without bound as the log fills, one row per player per
    status move per gameweek for a whole season. The disk file is where that
    belongs; ``/api/quality`` sends the two tables the page draws.
    """
    body = served({"flag_latency": FLAG_LATENCY}).get("/api/quality").json()
    assert "changes" not in body["flag_latency"]
    assert body["flag_latency"]["rows"] == 2      # the count still travels


def test_a_refusal_reaches_the_page_with_its_sentence(served):
    """The empty state is served, not withheld: spec §1 wants the page to say
    what it is waiting for, and the sentence is written by the scorer."""
    refusal = {**FLAG_LATENCY, "available": False, "rows": 0,
               "note": "3 of 14 snapshot days banked, and 0 covered "
                       "gameweek(s) graded.", "histogram": [],
               "late_flags": [], "changes": []}
    body = served({"flag_latency": refusal}).get("/api/quality").json()
    assert body["flag_latency"]["available"] is False
    assert "3 of 14" in body["flag_latency"]["note"]


def test_an_artifact_without_the_keys_is_unchanged(served):
    """Every already-banked artifact predates this cycle. Absent, not empty."""
    body = served({"current": None}).get("/api/quality").json()
    assert body["flag_latency"] is None
    assert body["presser_grades"] is None


def test_the_route_total_is_unchanged(served):
    """No route: both reports ride the endpoint that already reads this file.
    The absolute count lives in tests/test_v11_degradation.py and stays there;
    this is the by-name claim (v11 route-pin restructure)."""
    client = served({})
    paths = set(client.app.openapi()["paths"])
    assert "/api/quality" in paths
    assert not [p for p in paths if "latency" in p or "presser" in p]
