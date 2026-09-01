"""``GET /api/model/calibration`` — the report at the web boundary.

Spec §4 asks for the route on "the model router". There is no ``/api/model``
router: the Model hub's evaluation surface is ``routers/quality.py``, which
already holds the disk-only contract and the ``load_evaluation`` seam, and its
prefix is ``/api`` — so a handler declared ``/model/calibration`` there serves
exactly the path named.

The one behaviour worth stating up front is the 200-with-empty. ``/api/quality``
answers a missing artifact with a 422 and that is right for a page whose whole
content is the artifact. This card renders *beside* populated ones, where a 422
is indistinguishable from a broken endpoint, so an absent key is an empty
payload carrying the sentence that says what to run. A corrupt artifact is
still the 422: that one really is broken.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from gaffer.evaluation import EVALUATION_PATH, save_evaluation
from gaffer.web.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app())


def _head(status: str = "scored") -> dict:
    if status == "insufficient":
        return {"status": "insufficient", "n": 4, "brier": None,
                "log_loss": None, "reliability": []}
    return {"status": "scored", "n": 40, "brier": 0.1234, "log_loss": 0.4,
            "reliability": [{"n": 40, "pred": 0.8, "obs": 0.75}]}


def _payload() -> dict:
    return {
        "run_at": "2026-09-01T00:00:00Z", "git_sha": "abc1234",
        "season": "2025-26",
        "gameweeks": [{"gw": 1, "n": 40,
                       "heads": {"p_play": _head(),
                                 "p_cs": _head("insufficient")}}],
        "cumulative": {"p_play": _head()},
        "omitted": {"p_start": "not banked"},
        "excluded": [{"gw": 2, "reason": "written after kickoff"}],
        "missing": [3],
        "note": None,
    }


def test_no_artifact_at_all_is_a_200_with_an_empty_payload(client):
    """Not /api/quality's 422 — see this module's docstring."""
    response = client.get("/api/model/calibration")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert "gaffer evaluate --calibration" in body["note"]
    assert body["gameweeks"] == []


def test_an_artifact_without_the_key_is_the_same_200_with_empty(client):
    """The common state for the first weeks after this ships."""
    save_evaluation("current", {"run_at": "x"})
    body = client.get("/api/model/calibration").json()
    assert body["available"] is False
    assert "gaffer evaluate --calibration" in body["note"]


def test_a_populated_key_round_trips(client):
    save_evaluation("calibration", _payload())
    body = client.get("/api/model/calibration").json()
    assert body["available"] is True
    assert body["season"] == "2025-26"
    row = body["gameweeks"][0]
    assert row["gw"] == 1 and row["n"] == 40
    assert row["heads"]["p_play"]["brier"] == 0.1234
    assert row["heads"]["p_play"]["reliability"][0]["obs"] == 0.75
    assert body["cumulative"]["p_play"]["status"] == "scored"


def test_an_insufficient_head_survives_the_schema(client):
    """The assertion that catches a ``float`` where the payload has ``None`` —
    the failure mode CurrentEvaluation's undeclared odds_blend_weight already
    demonstrated, where a field silently never reached the page."""
    save_evaluation("calibration", _payload())
    head = client.get("/api/model/calibration").json()[
        "gameweeks"][0]["heads"]["p_cs"]
    assert head["status"] == "insufficient"
    assert head["brier"] is None and head["log_loss"] is None
    assert head["reliability"] == []


def test_the_refusals_all_reach_the_client(client):
    """omitted/excluded/missing are the honesty of the report; a schema that
    drops them turns a partial grading into a complete-looking one."""
    save_evaluation("calibration", _payload())
    body = client.get("/api/model/calibration").json()
    assert body["omitted"] == {"p_start": "not banked"}
    assert body["excluded"] == [{"gw": 2, "reason": "written after kickoff"}]
    assert body["missing"] == [3]


def test_a_corrupt_artifact_is_the_routers_re_run_the_cli_answer(client):
    EVALUATION_PATH.parent.mkdir(exist_ok=True)
    EVALUATION_PATH.write_text("{not json")
    response = client.get("/api/model/calibration")
    assert response.status_code == 422
    assert "gaffer evaluate" in response.json()["detail"]


def test_an_older_schema_under_the_key_is_a_422_and_not_a_500(client):
    save_evaluation("calibration", {"gameweeks": "not a list"})
    response = client.get("/api/model/calibration")
    assert response.status_code == 422
    assert "older schema" in response.json()["detail"]


def test_the_new_key_does_not_break_api_quality(client):
    """Pydantic ignores extra keys, but this is the one way this task could
    break a shipped page, so it is asserted rather than assumed."""
    save_evaluation("calibration", _payload())
    assert "calibration" in json.loads(EVALUATION_PATH.read_text())
    assert client.get("/api/quality").status_code == 200


def test_the_openapi_paths_gained_exactly_the_calibration_get(client):
    paths = set(create_app().openapi()["paths"])
    assert {p for p in paths if p.startswith("/api/model")} == {
        "/api/model/calibration"}
