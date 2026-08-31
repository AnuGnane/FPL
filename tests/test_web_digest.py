"""``GET /api/digest``: whichever digest is newest, or an honest nothing."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from gaffer import artifacts
from gaffer.web.app import create_app

FRIDAY = {"kind": "friday", "generated_at": "2026-08-28T17:00:00+00:00",
          "gw": 5, "headline": "GW5: captain Haaland, 1 transfer.",
          "sections": [{"key": "move", "title": "The plan",
                        "bits": ["Haaland in, Rice out"]}]}
TUESDAY = {"kind": "tuesday", "generated_at": "2026-09-01T09:30:00+00:00",
           "gw": 4, "headline": "GW4: you 58, model 63.",
           "sections": [{"key": "verdict", "title": "GW4",
                         "bits": ["You scored 58."]}]}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    return TestClient(create_app())


def _write(kind, payload):
    (artifacts.REPORTS / f"digest_{kind}.json").write_text(
        json.dumps(payload))


def test_no_digest_at_all_is_an_unavailable_panel(client):
    body = client.get("/api/digest").json()
    assert body["available"] is False and body["digest"] is None


def test_one_digest_is_served_whole(client):
    _write("friday", FRIDAY)
    body = client.get("/api/digest").json()
    assert body["available"] is True
    assert body["digest"]["headline"] == FRIDAY["headline"]
    assert body["digest"]["sections"][0]["bits"] == ["Haaland in, Rice out"]


def test_the_newer_of_the_two_wins(client):
    """A11: the artifact's own timestamp is a fact and the browser's clock is
    not."""
    _write("friday", FRIDAY)
    _write("tuesday", TUESDAY)
    assert client.get("/api/digest").json()["digest"]["kind"] == "tuesday"


def test_a_kind_can_be_pinned(client):
    _write("friday", FRIDAY)
    _write("tuesday", TUESDAY)
    assert client.get("/api/digest?kind=friday").json()["digest"]["kind"] \
        == "friday"


def test_pinning_a_kind_that_has_never_run_is_unavailable_not_a_fallback(
        client):
    _write("tuesday", TUESDAY)
    body = client.get("/api/digest?kind=friday").json()
    assert body["available"] is False


def test_an_unknown_kind_is_a_422_naming_the_two(client):
    response = client.get("/api/digest?kind=wednesday")
    assert response.status_code == 422
    assert "friday" in response.json()["detail"]


def test_a_corrupt_artifact_is_unavailable_not_a_500(client):
    (artifacts.REPORTS / "digest_friday.json").write_text("{not json")
    assert client.get("/api/digest").json()["available"] is False


def test_a_digest_missing_its_timestamp_still_serves(client):
    """A hand-edited or older artifact sorts last rather than crashing the
    comparison."""
    _write("friday", {k: v for k, v in FRIDAY.items()
                      if k != "generated_at"})
    body = client.get("/api/digest").json()
    assert body["available"] is True
    assert body["digest"]["generated_at"] == ""
