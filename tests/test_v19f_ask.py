"""v19f §2.2 — ``POST /api/ask``: an anonymous job, the checked answer in
its result, a 422 for an over-long question, a 429 for a full queue."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gaffer import artifacts
from gaffer.brief import QUESTION_MAX_CHARS
from gaffer.web.app import create_app
from gaffer.web.jobs import JobQueueFull

ANSWER = {"gw": 4, "question": "Why bank?", "answer": "The ladder chose the bank.",
          "offences": ["number 52 is not in the facts: x"], "model_command": "claude",
          "at": "2026-09-16T09:00:00+00:00"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    artifacts.REPORTS.mkdir()
    return TestClient(create_app())


def test_asking_is_accepted_with_a_job_id(client, monkeypatch):
    monkeypatch.setattr("gaffer.web.routers.ask.answer_question",
                        lambda q, gw, *, cfg: ANSWER)
    resp = client.post("/api/ask", json={"question": "Why bank?"})
    assert resp.status_code == 202 and resp.json()["job_id"]


def test_the_jobs_result_carries_the_answer_and_the_offences(client, monkeypatch):
    seen = {}

    def fake(question, gw, *, cfg):
        seen["question"], seen["gw"] = question, gw
        return ANSWER

    monkeypatch.setattr("gaffer.web.routers.ask.answer_question", fake)
    job_id = client.post("/api/ask", json={"question": " Why bank? ", "gw": 4}
                         ).json()["job_id"]
    for _ in range(4000):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            break
    assert job["status"] == "done"
    assert job["result"]["answer"] == "The ladder chose the bank."
    assert job["result"]["offences"] == ANSWER["offences"]
    # The router strips before submitting, so the job answers the same
    # question the 422 check saw (v19f §2.2).
    assert seen == {"question": "Why bank?", "gw": 4}


def test_an_over_long_question_is_refused_synchronously(client):
    resp = client.post("/api/ask", json={"question": "x" * (QUESTION_MAX_CHARS + 1)})
    assert resp.status_code == 422
    assert "question too long (500 characters)" in resp.json()["detail"]


def test_a_full_queue_is_a_429(client, monkeypatch):
    def full(*args, **kwargs):
        raise JobQueueFull("the queue is full")

    monkeypatch.setattr(client.app.state.jobs, "submit", full)
    resp = client.post("/api/ask", json={"question": "Why bank?"})
    assert resp.status_code == 429 and "full" in resp.json()["detail"]
