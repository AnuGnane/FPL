"""v16 §6.5 — GET /api/brief, POST /api/brief (an anonymous job, plan R1),
the chain after a web advise, the Friday headline."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from gaffer import artifacts
from gaffer.web.app import create_app

BRIEF = {"gw": 4, "run_stamp": "s", "prose": "One sentence. Two.", "facts": {"gw": 4},
         "model_command": "claude", "prompt_version": 1, "checked_at": "2026-09-05T09:00:00+00:00"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    artifacts.REPORTS.mkdir()
    return TestClient(create_app())


def test_no_brief_is_the_fallback_digest_panel_with_no_note(client):
    body = client.get("/api/brief").json()
    assert body["prose"] is None and body["gw"] is None
    assert body["fallback"] == {"available": False, "digest": None}
    assert body["note"] is None


def test_the_newest_brief_is_served(client):
    (artifacts.REPORTS / "brief_gw3.json").write_text(json.dumps({**BRIEF, "gw": 3}))
    (artifacts.REPORTS / "brief_gw4.json").write_text(json.dumps(BRIEF))
    body = client.get("/api/brief").json()
    assert body["gw"] == 4 and body["prose"] == "One sentence. Two."
    assert body["checked_at"] == BRIEF["checked_at"] and body["fallback"] is None


def test_a_banked_failure_note_reaches_the_fallback(client):
    (artifacts.REPORTS / "brief_note.json").write_text(json.dumps(
        {"gw": 4, "note": "the brief did not pass its check this week (x)", "at": "t"}))
    body = client.get("/api/brief").json()
    assert body["prose"] is None and "did not pass" in body["note"]


def test_post_submits_an_anonymous_job_and_the_result_is_the_run_dict(client, monkeypatch):
    monkeypatch.setattr("gaffer.web.routers.brief.run_brief",
                        lambda: {"gw": 4, "written": False, "note": "n", "path": None})
    resp = client.post("/api/brief")
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    for _ in range(4000):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            break
    assert job["status"] == "done" and job["result"]["note"] == "n"


def test_the_web_advise_body_chains_the_brief_on_success(monkeypatch):
    from types import SimpleNamespace

    from gaffer.web.routers import advice as advice_router

    calls = []
    monkeypatch.setattr("gaffer.models.train.load_training_frame", lambda: (None, None, None))
    monkeypatch.setattr("gaffer.models.train.train_all", lambda *a, **k: None)
    monkeypatch.setattr("gaffer.config.load_config", lambda: SimpleNamespace())
    monkeypatch.setattr("gaffer.advise.run_advise",
                        lambda cfg: SimpleNamespace(gw=4, expected_pts=60.0))
    monkeypatch.setattr("gaffer.report.render.render_report", lambda *a, **k: None)
    monkeypatch.setattr("gaffer.tracking.latest_health", lambda: None)
    monkeypatch.setattr("gaffer.brief.run_brief",
                        lambda gw: calls.append(gw) or {"gw": gw, "written": True,
                                                         "note": None, "path": "p"})
    out = advice_router.run_train_and_advise()
    assert calls == [4] and out["brief"]["written"] is True


def test_the_chain_does_not_fire_when_advise_fails(monkeypatch):
    from gaffer.web.routers import advice as advice_router

    calls = []
    monkeypatch.setattr("gaffer.models.train.load_training_frame", lambda: (None, None, None))
    monkeypatch.setattr("gaffer.models.train.train_all", lambda *a, **k: None)
    monkeypatch.setattr("gaffer.config.load_config", lambda: None)

    def boom(cfg):
        raise RuntimeError("no models")
    monkeypatch.setattr("gaffer.advise.run_advise", boom)
    monkeypatch.setattr("gaffer.brief.run_brief", lambda gw: calls.append(gw))
    with pytest.raises(RuntimeError):
        advice_router.run_train_and_advise()
    assert calls == []


def test_a_brief_that_raises_does_not_fail_the_advise_job(monkeypatch):
    from types import SimpleNamespace

    from gaffer.web.routers import advice as advice_router

    monkeypatch.setattr("gaffer.models.train.load_training_frame", lambda: (None, None, None))
    monkeypatch.setattr("gaffer.models.train.train_all", lambda *a, **k: None)
    monkeypatch.setattr("gaffer.config.load_config", lambda: None)
    monkeypatch.setattr("gaffer.advise.run_advise",
                        lambda cfg: SimpleNamespace(gw=4, expected_pts=60.0))
    monkeypatch.setattr("gaffer.report.render.render_report", lambda *a, **k: None)
    monkeypatch.setattr("gaffer.tracking.latest_health", lambda: None)

    def boom(gw):
        raise RuntimeError("import failed")
    monkeypatch.setattr("gaffer.brief.run_brief", boom)
    out = advice_router.run_train_and_advise()
    assert out["gw"] == 4 and "import failed" in out["brief"]["note"]


def test_the_friday_headline_is_the_briefs_first_sentence(tmp_path, monkeypatch):
    from tests.test_digest import ADVICE, EVENTS, GW  # noqa: F401 — the fixture shapes
    from gaffer.digest import friday_briefing

    monkeypatch.chdir(tmp_path)
    artifacts.REPORTS.mkdir()
    (artifacts.REPORTS / f"gw{GW}-advice.json").write_text(json.dumps(ADVICE))
    (artifacts.REPORTS / f"brief_gw{GW}.json").write_text(json.dumps(
        {**BRIEF, "gw": GW, "prose": "The ladder chose the bank. More."}))
    monkeypatch.setattr("gaffer.digest.latest_gw", lambda: GW)
    monkeypatch.setattr("gaffer.digest.upcoming_gw", lambda: GW)
    out = friday_briefing()
    assert out["headline"] == "The ladder chose the bank."


def test_the_cli_brief_command_prints_the_note_and_never_raises(monkeypatch):
    from typer.testing import CliRunner

    from gaffer.cli import app

    monkeypatch.setattr("gaffer.brief.run_brief",
                        lambda: {"gw": 4, "written": False, "note": "no advice", "path": None})
    out = CliRunner().invoke(app, ["brief"])
    assert out.exit_code == 0 and "no advice" in out.output
