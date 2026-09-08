"""v17d — one weekly pipeline module (specs/2026-09-07-v17d-pipeline-design.md).

Unit tests over stubbed steps, the job-kind and CLI seams, and the
``golden``-marked parity run over the recorded board (spec §1 item 2)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


def _advice(gw=4, expected_pts=60.0):
    return SimpleNamespace(gw=gw, expected_pts=expected_pts)


def _wire(monkeypatch, calls, *, advice=None, brief=None, run_advise=None):
    """Stub the four steps by module attribute (the lazy imports read them)
    and record every call in ``calls``."""
    advice = advice if advice is not None else _advice()
    monkeypatch.setattr("gaffer.models.train.load_training_frame",
                        lambda: ([1, 2, 3], "team_frame", None))
    monkeypatch.setattr("gaffer.models.train.train_all",
                        lambda frame, team_frame, save=True:
                        calls.append(("train", len(frame), team_frame, save)))
    monkeypatch.setattr("gaffer.advise.run_advise", run_advise or (
        lambda cfg, client=None: calls.append(("advise", cfg, client)) or advice))
    monkeypatch.setattr("gaffer.tracking.latest_health", lambda: {"h": 1})
    monkeypatch.setattr("gaffer.report.render.render_report",
                        lambda a, model_health=None:
                        calls.append(("render", a, model_health)) or "reports/gw4-report.html")
    monkeypatch.setattr("gaffer.brief.run_brief",
                        lambda gw, cfg=None: calls.append(("brief", gw, cfg)) or (
                            brief or {"gw": gw, "written": True, "note": None, "path": "p"}))


def test_the_steps_run_in_order_train_advise_render_brief(monkeypatch):
    from gaffer.pipeline import weekly_run

    calls = []
    _wire(monkeypatch, calls)
    cfg = object()
    out = weekly_run(cfg)
    assert [c[0] for c in calls] == ["train", "advise", "render", "brief"]
    assert calls[0] == ("train", 3, "team_frame", True)
    assert out.trained is True and out.training_rows == 3
    assert out.advice.gw == 4 and out.report_path == Path("reports/gw4-report.html")
    assert calls[2][2] == {"h": 1}  # the latest health reaches the render


def test_train_false_skips_the_train_step_and_says_so(monkeypatch):
    from gaffer.pipeline import weekly_run

    calls = []
    _wire(monkeypatch, calls)
    out = weekly_run(object(), train=False)
    assert [c[0] for c in calls] == ["advise", "render", "brief"]
    assert out.trained is False and out.training_rows is None


def test_the_client_reaches_run_advise(monkeypatch):
    from gaffer.pipeline import weekly_run

    calls = []
    _wire(monkeypatch, calls)
    cfg, client = object(), object()
    weekly_run(cfg, client=client, train=False)
    assert calls[0] == ("advise", cfg, client)


def test_the_brief_gets_the_gw_and_the_config_in_force(monkeypatch):
    from gaffer.pipeline import weekly_run

    calls = []
    _wire(monkeypatch, calls)
    cfg = object()
    out = weekly_run(cfg, train=False)
    assert calls[-1] == ("brief", 4, cfg)
    assert out.brief["written"] is True


def test_the_brief_does_not_fire_when_advise_raises(monkeypatch):
    from gaffer.pipeline import weekly_run

    calls = []

    def boom(cfg, client=None):
        raise RuntimeError("no models")
    _wire(monkeypatch, calls, run_advise=boom)
    with pytest.raises(RuntimeError):
        weekly_run(object(), train=False)
    assert [c[0] for c in calls] == []


def test_a_brief_that_raises_is_a_note_not_a_failed_run(monkeypatch):
    from gaffer.pipeline import weekly_run

    calls, logged = [], []
    _wire(monkeypatch, calls)

    def boom(gw, cfg=None):
        raise RuntimeError("import failed")
    monkeypatch.setattr("gaffer.brief.run_brief", boom)
    out = weekly_run(object(), train=False, log=logged.append)
    assert out.advice.gw == 4
    assert out.brief == {"gw": 4, "written": False,
                         "note": "brief not written: import failed", "path": None}
    assert logged == ["brief not written: import failed"]


def test_the_train_step_logs_the_rows_it_trained_on(monkeypatch):
    from gaffer.pipeline import weekly_run

    calls, logged = [], []
    _wire(monkeypatch, calls)
    weekly_run(object(), log=logged.append)
    assert logged == ["Trained on 3 player-GW rows. Models saved to models/."]


def test_record_is_the_dict_the_runner_stored(monkeypatch):
    from gaffer.pipeline import RunResult

    out = RunResult(advice=_advice(5, 61.0), report_path=Path("r"),
                    brief={"gw": 5, "written": False, "note": "n", "path": None},
                    trained=True, training_rows=10)
    rec = out.record()
    assert list(rec) == ["gw", "expected_pts", "brief"]
    assert rec == {"gw": 5, "expected_pts": 61.0,
                   "brief": {"gw": 5, "written": False, "note": "n", "path": None}}


# --- the job kind and the router (spec §2.10, §2.11, gate item 3) ---------

def test_the_job_kind_body_records_the_result(monkeypatch):
    from gaffer.config import Config
    from gaffer.pipeline import RunResult
    from gaffer.web import job_kinds

    seen = {}

    def fake_run(cfg, *, client=None, train=True, log=print):
        seen["cfg"], seen["train"] = cfg, train
        return RunResult(advice=_advice(5, 61.0), report_path=Path("r"),
                         brief={"gw": 5, "written": True, "note": None, "path": "p"},
                         trained=True, training_rows=1)
    monkeypatch.setattr("gaffer.pipeline.weekly_run", fake_run)
    monkeypatch.setattr("gaffer.config.load_config",
                        lambda path="config.toml": Config(entry_id=1, league_id=2))

    out = job_kinds.run_train_and_advise()
    assert seen["train"] is True and seen["cfg"].entry_id == 1
    assert out == {"gw": 5, "expected_pts": 61.0,
                   "brief": {"gw": 5, "written": True, "note": None, "path": "p"}}
    # The config it is handed wins over the one on disk (v7c's contract).
    job_kinds.run_train_and_advise(Config(entry_id=9, league_id=2))
    assert seen["cfg"].entry_id == 9


def test_the_advise_kind_is_the_body_defined_in_job_kinds():
    from gaffer.web import job_kinds

    assert job_kinds.JOB_KINDS["advise"] is job_kinds.run_train_and_advise
    assert job_kinds.run_train_and_advise.__module__ == "gaffer.web.job_kinds"


def test_non_web_code_does_not_import_the_advice_router():
    """Gate item 3 as a rail: the router is HTTP only."""
    import gaffer.pipeline
    import gaffer.cli
    import gaffer.web.job_kinds
    from gaffer.web.routers import advice as advice_router

    for mod in (gaffer.pipeline, gaffer.cli, gaffer.web.job_kinds):
        assert "routers.advice" not in Path(mod.__file__).read_text()
    assert not hasattr(advice_router, "run_train_and_advise")


def test_the_plist_is_unchanged_and_still_runs_advise():
    """Gate item 4: the brief arrives through the CLI, not the plist."""
    text = Path("scripts/com.gaffer.advise.plist").read_text()
    assert "uv run gaffer train &amp;&amp; uv run gaffer advise" in text
    assert "gaffer brief" not in text
