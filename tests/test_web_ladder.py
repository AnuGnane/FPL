"""v13 §3.2 — GET and POST /api/ladder against a hand-built solve state."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gaffer.web.app import create_app
from gaffer.web.jobs import JobQueueFull
from tests.test_ladder import save_state


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    save_state({"max_hits": 2, "max_transfers": 15})
    return TestClient(create_app())


def _wait(client, job_id):
    for _ in range(4000):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            return job
    raise AssertionError("job never finished")


def test_get_with_no_state_is_an_empty_payload_with_a_note(tmp_path,
                                                           monkeypatch):
    monkeypatch.chdir(tmp_path)
    body = TestClient(create_app()).get("/api/ladder").json()
    assert body["gw"] is None and body["rungs"] == []
    assert "gaffer advise" in body["note"]


def test_get_before_a_build_names_the_gameweek_and_says_rebuild(client):
    body = client.get("/api/ladder").json()
    assert body["gw"] == 1 and body["rungs"] == []
    assert "rebuild" in body["note"]


def test_post_builds_banks_and_get_then_serves_it(client):
    resp = client.post("/api/ladder")
    assert resp.status_code == 202, resp.text
    job = _wait(client, resp.json()["job_id"])
    assert job["status"] == "done", job["error"]
    assert job["result"]["rungs"][0]["key"] == "bank"
    body = client.get("/api/ladder").json()
    assert body["gw"] == 1 and body["note"] is None
    assert [r["key"] for r in body["rungs"]][:5] == \
        ["bank", "hits0", "hits1", "hits2", "hits3"]
    assert body["cap"] == {"max_hits": 2, "max_transfers": None}
    assert body["cap_rung"] == "hits2"


def test_a_full_queue_is_a_429(client):
    app = client.app

    def full(fn, timeout_s):
        raise JobQueueFull("queue full")

    app.state.jobs.submit = full
    resp = client.post("/api/ladder")
    assert resp.status_code == 429
    assert "full" in resp.json()["detail"]


def test_post_with_no_state_is_the_advise_first_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    resp = TestClient(create_app()).post("/api/ladder")
    assert resp.status_code in (400, 422)
    assert "gaffer advise" in resp.text
