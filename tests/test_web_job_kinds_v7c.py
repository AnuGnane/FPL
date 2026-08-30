"""The job kinds added after the original five: v7c's snapshot, v7d's
advise-fast and track-pens."""

from gaffer.web import job_kinds


def test_the_snapshot_kind_is_on_the_allow_list():
    assert job_kinds.JOB_KINDS["snapshot"] is job_kinds.run_snapshot_job


def test_the_snapshot_job_reports_the_rows_it_banked(monkeypatch, capsys):
    """The runner captures this thread's stdout, so the wrapper's print is
    what the browser shows as the job's progress line."""
    monkeypatch.setattr("gaffer.snapshot.run_snapshot", lambda: 42)
    assert job_kinds.run_snapshot_job() == {"rows": 42}
    assert "42 availability rows" in capsys.readouterr().out


def test_a_degraded_snapshot_is_still_a_finished_job(monkeypatch):
    """``run_snapshot`` answers ``None`` on any bad afternoon; the job must
    report zero rows rather than fail the run."""
    monkeypatch.setattr("gaffer.snapshot.run_snapshot", lambda: None)
    assert job_kinds.run_snapshot_job() == {"rows": 0}


def test_the_snapshot_wrapper_imports_lazily():
    import inspect

    source = inspect.getsource(job_kinds)
    assert "from gaffer.snapshot import" not in source.split("def ")[0]


def test_the_fast_advise_kind_is_on_the_allow_list():
    assert job_kinds.JOB_KINDS["advise-fast"] \
        is job_kinds.run_train_and_advise_fast


def test_the_advise_body_still_defaults_to_the_config_on_disk():
    """The refactor must be invisible to every existing caller: the kind
    table stores the function itself, and the runner calls it with no args."""
    import inspect

    from gaffer.web.routers.advice import run_train_and_advise

    assert inspect.signature(run_train_and_advise).parameters["cfg"].default \
        is None


def test_the_advise_body_uses_the_config_it_is_handed(monkeypatch):
    from gaffer.config import Config
    from gaffer.web.routers.advice import run_train_and_advise

    seen = {}

    class _Advice:
        gw = 5
        expected_pts = 61.0

    def _run(cfg):
        seen["scenarios_n"] = cfg.scenarios_n
        return _Advice()

    monkeypatch.setattr("gaffer.models.train.load_training_frame",
                        lambda: (None, None, None))
    monkeypatch.setattr("gaffer.models.train.train_all",
                        lambda frame, team_frame, save=True: None)
    monkeypatch.setattr("gaffer.advise.run_advise", _run)
    monkeypatch.setattr("gaffer.report.render.render_report",
                        lambda advice, model_health=None: "reports/gw5.html")
    monkeypatch.setattr("gaffer.tracking.latest_health", lambda: None)

    out = run_train_and_advise(
        Config(entry_id=1, league_id=2, scenarios_n=7))
    assert seen["scenarios_n"] == 7
    assert out == {"gw": 5, "expected_pts": 61.0}


def test_fast_advise_replaces_the_sweep_count_with_zero(monkeypatch):
    """The kind is the --fast flag, served: same body, n = 0.

    ``job_kinds`` binds ``run_train_and_advise`` by reference at import, so
    the substitute goes on ``job_kinds`` itself — patching the router module
    would leave the table pointing at the original.
    """
    from gaffer.config import Config

    seen = {}

    def _body(cfg=None):
        seen["cfg"] = cfg
        return {"gw": 5, "expected_pts": 61.0}

    monkeypatch.setattr(
        "gaffer.config.load_config",
        lambda path="config.toml": Config(entry_id=1, league_id=2,
                                          scenarios_n=40))
    monkeypatch.setattr(job_kinds, "run_train_and_advise", _body)

    out = job_kinds.run_train_and_advise_fast()
    assert seen["cfg"].scenarios_n == 0
    assert seen["cfg"].entry_id == 1
    assert out == {"gw": 5, "expected_pts": 61.0}
