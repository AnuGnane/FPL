"""The ninth job kind, and the plist that runs it without a browser."""

from __future__ import annotations

from pathlib import Path

import pytest

from gaffer.web import job_kinds


def test_the_allow_list_count_is_pinned():
    """A kind not in the allow-list is a 404, never an exec of user input.
    The count is pinned on both sides — see frontend/src/types.test.ts."""
    # 9 -> 10: v8e added the `sensitivity` kind on both sides.
    # v8f added digest-friday and digest-tuesday as the eleventh and twelfth.
    assert len(job_kinds.JOB_KINDS) == 12
    assert "review" in job_kinds.JOB_KINDS


def test_every_kind_is_callable_without_arguments():
    for kind, fn in job_kinds.JOB_KINDS.items():
        assert callable(fn), kind


def test_the_review_job_reports_how_many_gameweeks_it_graded(monkeypatch,
                                                             capsys):
    monkeypatch.setattr("gaffer.review.run_review", lambda: [1, 2])
    assert job_kinds.JOB_KINDS["review"]() == {"gws": 2}
    assert "2 gameweeks" in capsys.readouterr().out


def test_a_review_that_graded_nothing_is_a_finished_job_not_a_failed_one(
        monkeypatch, capsys):
    """Zero is what an already-reviewed season looks like, which is what the
    Tuesday job sees every week between gameweeks."""
    monkeypatch.setattr("gaffer.review.run_review", lambda: [])
    assert job_kinds.JOB_KINDS["review"]() == {"gws": 0}


def test_the_review_import_is_lazy(monkeypatch):
    """``job_kinds`` is imported by ``app.py`` at start-up, so a heavyweight
    import at module level would cost every ``gaffer ui`` its parquet reads."""
    source = Path("src/gaffer/web/job_kinds.py").read_text()
    head = source.split("def run_review_job")[0]
    assert "from gaffer.review import" not in head


def test_the_plist_runs_the_command_on_a_tuesday_morning():
    text = Path("scripts/com.gaffer.review.plist").read_text()
    assert "gaffer review" in text
    assert "<key>Weekday</key><integer>2</integer>" in text
    assert "com.gaffer.review" in text
    assert "logs/review.log" in text


def test_the_installer_installs_it():
    text = Path("scripts/install_automation.sh").read_text()
    assert "advise prices snapshot field review" in text
    assert "review" in text.split("echo")[-1]
