"""The lane a wedged job used to hold forever.

``ADVISE_TIMEOUT_S`` was written in v6 and never read. ``JobRunner`` takes one
job at a time and cleared ``_current`` only in ``_execute``'s ``finally``, so
a job that never returned held the lane until the process restarted and every
later job got a 409 naming a run the caller had no way to clear.

v9c's D4 fixed it in two places — a reap inside ``start`` and a
``DELETE /api/jobs/current`` — and in a third the spec did not enumerate: a
guard inside ``_execute``'s ``finally``, without which the fix trades a loud
bug for a quiet one. An abandoned thread is still alive; when it finishes it
would otherwise overwrite the record saying why the lane was freed *and* clear
``_current``, which by then may name a different, newer job. Tests 4 and 5
below are that hazard, and they are the reason this file exists at all.
"""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from gaffer.web import jobs as jobs_module
from gaffer.web.app import create_app
from gaffer.web.jobs import JobAlreadyRunning, JobRunner


def _wait(runner, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = runner.get(job_id)
        if run is not None and run.status in ("done", "failed"):
            return run
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} never finished")


@pytest.fixture()
def sleeper():
    """A job body that blocks until the test releases it."""
    release = threading.Event()

    def body():
        print("working")
        release.wait(5.0)
        print("finished")
        return {"gw": 5}

    yield body, release
    release.set()


# --- 1-3: the reaper ------------------------------------------------

def test_a_fresh_holder_is_not_reaped(sleeper, monkeypatch):
    """The timeout is a reaper, not a cancel-everything. A job started a
    second ago still 409s the next one."""
    body, release = sleeper
    monkeypatch.setattr(jobs_module, "ADVISE_TIMEOUT_S", 1800.0)
    runner = JobRunner({"advise": body, "evaluate": lambda: None})
    first = runner.start("advise")
    with pytest.raises(JobAlreadyRunning):
        runner.start("evaluate")
    assert runner.current().id == first
    release.set()


def test_a_holder_past_the_timeout_is_reaped_and_the_next_job_starts(
        sleeper, monkeypatch):
    body, release = sleeper
    monkeypatch.setattr(jobs_module, "ADVISE_TIMEOUT_S", 0.05)
    runner = JobRunner({"advise": body, "evaluate": lambda: None})
    runner.start("advise")
    time.sleep(0.1)
    second = runner.start("evaluate")     # no JobAlreadyRunning
    assert isinstance(second, str) and second
    release.set()


def test_the_reaped_run_says_why(sleeper, monkeypatch):
    body, release = sleeper
    monkeypatch.setattr(jobs_module, "ADVISE_TIMEOUT_S", 0.05)
    runner = JobRunner({"advise": body, "evaluate": lambda: None})
    first = runner.start("advise")
    time.sleep(0.1)
    runner.start("evaluate")
    reaped = runner.get(first)
    assert reaped.status == "failed"
    assert "timed out" in reaped.error and "abandoned" in reaped.error
    assert reaped.finished_at is not None
    release.set()


# --- 4-5: the hazard the guard exists for ---------------------------

def test_the_abandoned_thread_cannot_steal_the_lane_back(sleeper, monkeypatch):
    """Plan A14, the central hazard. ``_execute``'s ``finally`` used to clear
    ``_current`` unconditionally — so the wedged run would free a lane that by
    then belonged to its own replacement, and the browser watching the newer
    job would be told nothing is running."""
    body, release = sleeper
    monkeypatch.setattr(jobs_module, "ADVISE_TIMEOUT_S", 0.05)
    held = threading.Event()
    runner = JobRunner({"advise": body, "evaluate": held.wait})
    first = runner.start("advise")
    time.sleep(0.1)
    second = runner.start("evaluate")

    release.set()                          # let the abandoned thread finish
    _wait(runner, first)
    time.sleep(0.05)

    assert runner.current() is not None
    assert runner.current().id == second
    assert "timed out" in runner.get(first).error
    held.set()


def test_the_abandoned_thread_cannot_overwrite_its_own_record(
        sleeper, monkeypatch):
    """The other half of the guard: the run completed *successfully*, and
    writing "done" over the abandonment would erase the only record of why
    the lane was freed."""
    body, release = sleeper
    monkeypatch.setattr(jobs_module, "ADVISE_TIMEOUT_S", 0.05)
    runner = JobRunner({"advise": body, "evaluate": lambda: None})
    first = runner.start("advise")
    time.sleep(0.1)
    runner.start("evaluate")
    before = runner.get(first).error

    release.set()
    _wait(runner, first)
    time.sleep(0.05)

    run = runner.get(first)
    assert run.status == "failed"
    assert run.error == before
    assert run.summary is None            # not the {'gw': 5} it returned


# --- 8: the reaper does not reap the living -------------------------

def test_a_normal_run_is_unaffected_end_to_end():
    runner = JobRunner({"advise": lambda: {"gw": 5}})
    run = _wait(runner, runner.start("advise"))
    assert run.status == "done"
    assert run.error is None
    assert run.summary == "{'gw': 5}"
    assert runner.current() is None


# --- 6-7, 9-10: the HTTP surface ------------------------------------

@pytest.fixture()
def client_and_release(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    release = threading.Event()

    def slow():
        print("working")
        release.wait(5.0)
        return {"gw": 5}

    app = create_app()
    app.state.job_runner = JobRunner({"advise": slow,
                                      "evaluate": lambda: None})
    yield TestClient(app), release, app
    release.set()


def test_delete_current_frees_the_lane_immediately(client_and_release):
    """Regardless of age — a cancel is not a timeout."""
    client, release, _ = client_and_release
    started = client.post("/api/jobs/advise")
    assert started.status_code == 202
    assert client.post("/api/jobs/evaluate").status_code == 409

    cancelled = client.delete("/api/jobs/current")
    assert cancelled.status_code == 200
    body = cancelled.json()
    assert body["id"] == started.json()["job_id"]
    assert body["status"] == "failed"
    assert "abandoned" in body["error"]

    assert client.post("/api/jobs/evaluate").status_code == 202
    release.set()


def test_delete_current_on_an_idle_runner_is_a_404(client_and_release):
    """404, not 500 and not 204. 204 is ``GET``'s answer for "nothing
    running"; the DELETE has to distinguish "I freed something" from "there
    was nothing to free", which is what a UI needs to decide whether to say
    anything at all."""
    client, _, _ = client_and_release
    response = client.delete("/api/jobs/current")
    assert response.status_code == 404
    assert "no job is running" in response.json()["detail"]


def test_the_409_payload_still_names_the_holder(client_and_release):
    """``frontend/src/api/useJob.ts`` reads this shape."""
    client, release, _ = client_and_release
    started = client.post("/api/jobs/advise").json()
    conflict = client.post("/api/jobs/evaluate")
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == {"running_kind": "advise",
                                         "job_id": started["job_id"]}
    release.set()


def test_the_sse_stream_still_ends_on_an_abandoned_run(client_and_release):
    """The concrete reason plan A12 chose ``"failed"`` over a new
    ``"abandoned"`` value: the generator terminates only on ``done`` or
    ``failed``, so any other status would leave every watching browser
    polling at ``POLL_S`` for the full ``IDLE_TIMEOUT_S`` hour."""
    client, release, app = client_and_release
    job_id = client.post("/api/jobs/advise").json()["job_id"]
    app.state.job_runner.abandon_current()

    with client.stream("GET", f"/api/jobs/{job_id}/stream") as stream:
        text = "".join(chunk for chunk in stream.iter_text())
    assert "event: end" in text
    assert "failed" in text
    release.set()


def test_the_delete_route_shares_the_path_with_the_get(client_and_release):
    """Declared before ``GET /{job_id}`` so the path parameter cannot swallow
    the literal — and on one path, which is why no route-set pin moved."""
    client, _, _ = client_and_release
    paths = client.app.openapi()["paths"]
    assert set(paths["/api/jobs/current"]) == {"get", "delete"}


# --- review B1: the abandoned thread must not blind its replacement --------

def test_an_abandoned_thread_finishing_late_does_not_blind_the_replacement(
        monkeypatch):
    """Review B1, and the stdout half of test 4's hazard.

    ``_execute`` installs a ``_ThreadRouter`` over ``sys.stdout`` and used to
    restore the real stream unconditionally in its ``finally``. An abandoned
    thread is still alive and reaches that line *late* — by which time
    ``sys.stdout`` is the replacement job's router, and tearing it out means
    the replacement's log comes back empty for no reason anyone watching can
    see. The restore now checks it is undoing its own install.
    """
    monkeypatch.setattr(jobs_module, "ADVISE_TIMEOUT_S", 0.05)
    wedged_may_finish = threading.Event()
    second_started = threading.Event()
    second_may_finish = threading.Event()

    def wedged():
        print("first job line")
        wedged_may_finish.wait(5.0)
        print("first job, far too late")

    def replacement():
        second_started.set()
        second_may_finish.wait(5.0)
        # Printed *after* the abandoned thread has run its finally.
        print("replacement job line")

    runner = JobRunner({"advise": wedged, "evaluate": replacement})
    first = runner.start("advise")
    time.sleep(0.1)
    second = runner.start("evaluate")
    assert second_started.wait(5.0)

    # Let the abandoned thread run its finally while the replacement is live.
    wedged_may_finish.set()
    _wait(runner, first)
    time.sleep(0.05)

    second_may_finish.set()
    run = _wait(runner, second)
    assert "replacement job line" in run.lines, (
        "the abandoned thread's finally tore out the replacement's router")
