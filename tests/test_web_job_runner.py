"""The v7 kind-keyed runner. The v6 JobRegistry in the same module is
untouched and has its own suite in tests/test_web_jobs.py."""

import threading
import time

import pytest

from gaffer.web.jobs import JOB_LINE_CAP, JobAlreadyRunning, JobRunner


def _wait(runner, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = runner.get(job_id)
        if run is not None and run.status in ("done", "failed"):
            return run
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} never finished")


def test_a_successful_run_captures_its_printed_lines():
    def body():
        print("step one")
        print("step two")
        return {"gw": 5}

    runner = JobRunner({"advise": body})
    run = _wait(runner, runner.start("advise"))
    assert run.status == "done"
    assert run.kind == "advise"
    assert run.lines[:2] == ["step one", "step two"]
    assert run.summary == "{'gw': 5}"
    assert run.error is None
    assert run.started_at and run.finished_at


def test_a_failing_run_is_failed_and_keeps_the_message():
    def body():
        print("about to fall over")
        raise RuntimeError("no models on disk")

    runner = JobRunner({"advise": body})
    run = _wait(runner, runner.start("advise"))
    assert run.status == "failed"
    assert run.error == "no models on disk"
    assert "about to fall over" in run.lines


def test_only_one_job_runs_at_a_time():
    release = threading.Event()
    runner = JobRunner({"advise": release.wait, "evaluate": lambda: None})
    first = runner.start("advise")
    with pytest.raises(JobAlreadyRunning) as excinfo:
        runner.start("evaluate")
    assert excinfo.value.running_kind == "advise"
    assert excinfo.value.job_id == first
    release.set()
    _wait(runner, first)
    # Once it finishes the lane is free again.
    _wait(runner, runner.start("evaluate"))


def test_an_unknown_kind_is_a_key_error_not_a_silent_no_op():
    runner = JobRunner({"advise": lambda: None})
    with pytest.raises(KeyError):
        runner.start("rm-rf")


def test_current_is_the_running_job_and_none_when_idle():
    release = threading.Event()
    runner = JobRunner({"advise": release.wait})
    assert runner.current() is None
    job_id = runner.start("advise")
    assert runner.current().id == job_id
    release.set()
    _wait(runner, job_id)
    assert runner.current() is None


def test_the_line_buffer_is_capped_and_keeps_the_tail():
    def body():
        for i in range(JOB_LINE_CAP + 50):
            print(i)

    runner = JobRunner({"advise": body})
    run = _wait(runner, runner.start("advise"), timeout=20.0)
    assert len(run.lines) == JOB_LINE_CAP
    assert run.lines[-1] == str(JOB_LINE_CAP + 49)
    # The absolute index survives truncation so a reconnecting client knows
    # what it missed rather than replaying from a shifted zero.
    assert run.first_line_index == 50


def test_lines_since_replays_from_an_absolute_index():
    def body():
        for word in ("a", "b", "c"):
            print(word)

    runner = JobRunner({"advise": body})
    job_id = runner.start("advise")
    _wait(runner, job_id)
    assert runner.lines_since(job_id, 0) == [(0, "a"), (1, "b"), (2, "c")]
    assert runner.lines_since(job_id, 2) == [(2, "c")]
    assert runner.lines_since(job_id, 99) == []
