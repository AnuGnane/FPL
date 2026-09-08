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
        source = Path(mod.__file__).read_text()
        # Both spellings of the import (Task 2 review).
        assert "routers.advice" not in source
        assert "routers import advice" not in source
    assert not hasattr(advice_router, "run_train_and_advise")


def test_the_plist_is_unchanged_and_still_runs_advise():
    """Gate item 4: the brief arrives through the CLI, not the plist."""
    text = Path("scripts/com.gaffer.advise.plist").read_text()
    assert "uv run gaffer train &amp;&amp; uv run gaffer advise" in text
    assert "gaffer brief" not in text


# --- the CLI (spec §2.3, gate item 4) -------------------------------------

def _cli_config(tmp_path, monkeypatch):
    import gaffer.config as config_mod

    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text('[fpl]\nentry_id = 1\nleague_id = 2\n')
    real_load = config_mod.load_config
    monkeypatch.setattr(config_mod, "load_config",
                        lambda path="config.toml": real_load(cfg_path))


def test_the_cli_advise_command_runs_the_pipeline_without_training(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from gaffer.cli import app
    from gaffer.pipeline import RunResult
    from tests.test_v4c_degradation import _fixture_advice

    _cli_config(tmp_path, monkeypatch)
    seen = {}

    def fake_run(cfg, *, client=None, train=True, log=print):
        seen["train"], seen["entry_id"] = train, cfg.entry_id
        return RunResult(advice=_fixture_advice(), report_path=Path("reports/gw7.html"),
                         brief={"gw": 7, "written": False,
                                "note": "no llm_command configured under [news]", "path": None},
                         trained=False, training_rows=None)
    monkeypatch.setattr("gaffer.pipeline.weekly_run", fake_run)
    out = CliRunner().invoke(app, ["advise"])
    assert out.exit_code == 0, out.output
    assert seen == {"train": False, "entry_id": 1}
    assert out.output.endswith("Report: reports/gw7.html\n"
                               "no llm_command configured under [news]\n")


def test_the_cli_still_exits_one_on_a_missing_model(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from gaffer.cli import app

    _cli_config(tmp_path, monkeypatch)

    def fake_run(cfg, **kw):
        raise SystemExit("Model 'minutes' missing — run `gaffer train` first.")
    monkeypatch.setattr("gaffer.pipeline.weekly_run", fake_run)
    out = CliRunner().invoke(app, ["advise"])
    assert out.exit_code == 1 and "gaffer train" in out.output


# --- the parity gate (spec §1 item 2) -------------------------------------

STUB_PROSE = "The plan holds. Bank the free transfer and keep the armband where it is."
STUB_COMMAND = f"python3 -c \"print('{STUB_PROSE}')\""
"""No digit and no capitalised word off a sentence start, so the truth
check has nothing to test; it ignores the prompt on stdin (spec §2.7)."""

REPO = Path(__file__).resolve().parents[1]


def _golden_header_or_skip():
    import json

    from tests import golden_client as gc

    path = gc.GOLDEN_DIR / gc.HEADER_NAME
    if not path.exists():
        pytest.skip("golden board not recorded (tests/data/golden_board/header.json)")
    header = json.loads(path.read_text())
    stale = gc.stale_inputs(header, REPO)
    if stale:
        pytest.skip(f"golden board recorded under a different {stale[0]} "
                    f"({len(stale)} input(s) differ); re-record with "
                    "python -m tests.golden_client --write")
    return header


def _parity_run(root: Path, monkeypatch, entry: str):
    """One entry over the golden board in a fresh scratch tree: the CLI or
    the job kind, both over the recorded client, training stubbed (the
    models are the pinned input, spec §2.6), the LLM stubbed."""
    import dataclasses
    import json

    from tests import golden_client as gc

    assert entry in ("cli", "job"), entry
    gc.build_scratch_tree(root, REPO)
    cfg = dataclasses.replace(gc.golden_config(), news_llm_command=STUB_COMMAND)
    client = gc.RecordedClient()
    monkeypatch.setattr("gaffer.config.load_config", lambda path="config.toml": cfg)
    monkeypatch.setattr("gaffer.advise.FPLClient", lambda: client)
    monkeypatch.setattr("gaffer.models.train.load_training_frame", lambda: ([], None, None))
    monkeypatch.setattr("gaffer.models.train.train_all", lambda *a, **k: None)
    with gc.golden_cwd(root, client):
        if entry == "cli":
            from typer.testing import CliRunner

            from gaffer.cli import app

            out = CliRunner().invoke(app, ["advise"])
            assert out.exit_code == 0, (entry, out.output)
            returned = None
        else:
            from gaffer.web.job_kinds import JOB_KINDS

            returned = JOB_KINDS["advise"]()
    advice_files = sorted((root / "reports").glob("gw*-advice.json"))
    assert len(advice_files) == 1, (entry, advice_files)
    advice = json.loads(advice_files[0].read_text())
    brief = json.loads((root / "reports" / f"brief_gw{advice['gw']}.json").read_text())
    return gc.strip_volatile(advice, str(root.resolve())), brief, returned


@pytest.mark.golden
def test_the_cli_and_the_job_kind_run_the_same_pipeline_on_the_golden_board(
        tmp_path_factory, monkeypatch):
    import json

    from gaffer.brief import check_brief
    from tests import golden_client as gc

    header = _golden_header_or_skip()
    expected = json.loads((gc.GOLDEN_DIR / gc.EXPECTED_DIR / "advice.json").read_text())

    advice_cli, brief_cli, _ = _parity_run(
        tmp_path_factory.mktemp("parity-cli"), monkeypatch, "cli")
    advice_job, brief_job, returned = _parity_run(
        tmp_path_factory.mktemp("parity-job"), monkeypatch, "job")

    # Task 4 review: the job arm runs with the train step on, stubbed; had
    # the stub not held, the models would have been rewritten through the
    # scratch tree's symlink, and this is what says so.
    assert gc.stale_inputs(header, REPO) == []
    assert advice_cli == expected
    assert advice_job == expected
    for brief in (brief_cli, brief_job):
        assert brief["prose"] == STUB_PROSE
        assert brief["model_command"] == "python3"
        assert check_brief(brief["prose"], brief["facts"]) == []
    assert returned["gw"] == expected["gw"]
    assert returned["expected_pts"] == expected["expected_pts"]
    assert returned["brief"]["written"] is True
