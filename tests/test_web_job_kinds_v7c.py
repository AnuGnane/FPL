"""The v7c job kind: the browser may trigger the daily availability snapshot."""

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
