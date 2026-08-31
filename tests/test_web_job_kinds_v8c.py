"""v8c's eighth job kind: field-scrape.

The pattern is ``tests/test_web_job_kinds_v7c.py``'s, because the contract is
the snapshot kind's contract — a body that never raises, a wrapper that turns
its answer into a row count, and a lazy import so ``gaffer --help`` does not
pay for pandas."""

from __future__ import annotations

from gaffer.web import job_kinds


def test_the_field_scrape_kind_is_on_the_allow_list():
    assert job_kinds.JOB_KINDS["field-scrape"] \
        is job_kinds.run_field_scrape_job


def test_the_allow_list_is_the_kinds_the_frontend_knows():
    """Lockstep with ``frontend/src/types.ts``'s JOB_KINDS: the browser sends
    one of these strings and a kind the router does not know is a 404.

    v8b added ``review`` as the ninth.
    """
    assert sorted(job_kinds.JOB_KINDS) == [
        "advise", "advise-fast", "evaluate", "field-scrape", "news-shadow",
        "refresh-data", "review", "snapshot", "track-pens"]


def test_the_job_reports_the_rows_it_logged(monkeypatch, capsys):
    monkeypatch.setattr("gaffer.data.field.run_field_scrape",
                        lambda: 512)
    assert job_kinds.run_field_scrape_job() == {"rows": 512}
    assert "512" in capsys.readouterr().out


def test_a_degraded_scrape_is_still_a_finished_job(monkeypatch):
    """``run_field_scrape`` answers ``None`` on any bad Saturday — a dead
    API, a switch that is off, a gameweek that has not kicked off. The job
    reports zero rows rather than failing the run."""
    monkeypatch.setattr("gaffer.data.field.run_field_scrape", lambda: None)
    assert job_kinds.run_field_scrape_job() == {"rows": 0}


def test_an_already_banked_gameweek_is_a_zero_row_success(monkeypatch):
    monkeypatch.setattr("gaffer.data.field.run_field_scrape", lambda: 0)
    assert job_kinds.run_field_scrape_job() == {"rows": 0}


def test_the_wrapper_imports_lazily():
    import inspect

    source = inspect.getsource(job_kinds)
    assert "from gaffer.data.field import" not in source.split("def ")[0]
