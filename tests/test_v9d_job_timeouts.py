"""Per-kind abandon deadlines, and a cancel that says it was cancelled.

Two v9c mechanisms, each finished here. The reaper inside ``JobRunner.start``
worked off one constant chosen for the most expensive kind, so a snapshot that
wedges — four seconds of work — held the single lane for the same half hour a
cold train-and-advise would. And ``abandon_current`` reaches the same helper
with ``older_than=0.0``, which reported "timed out after 0s" about a button
the user had just pressed.

The deadline read is the **holder's**, not the incoming job's, and that is the
easiest thing to get wrong: keyed on the incoming kind, a snapshot request
would reap a running advise on the 120-second clock. Test 2 is that assertion.
"""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from gaffer.web import job_kinds as kinds_module
from gaffer.web import jobs as jobs_module
from gaffer.web.app import create_app
from gaffer.web.job_kinds import (ABANDON_TIMEOUT_S, JOB_KINDS,
                                  SLOW_ABANDON_KINDS)
from gaffer.web.jobs import JobAlreadyRunning, JobRunner


def _wait(runner, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = runner.get(job_id)
        if run is not None and run.status in ("done", "failed"):
            return run
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} never finished")


def _until(predicate, timeout=5.0):
    """Poll rather than sleep a fixed span, as v9c's timeout rails do."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture()
def sleeper():
    """A job body that blocks until the test releases it."""
    release = threading.Event()

    def body():
        print("working")
        release.wait(5.0)
        return {"gw": 5}

    yield body, release
    release.set()


# --- 1-3: whose clock, and how long ---------------------------------

def test_a_fast_kind_is_reaped_on_its_own_short_deadline(sleeper, monkeypatch):
    """A wedged snapshot no longer costs the next job half an hour."""
    body, release = sleeper
    monkeypatch.setitem(ABANDON_TIMEOUT_S, "snapshot", 0.05)
    runner = JobRunner({"snapshot": body, "evaluate": lambda: None})
    first = runner.start("snapshot")
    assert _until(lambda: runner.get(first) is not None)
    time.sleep(0.1)
    assert isinstance(runner.start("evaluate"), str)
    release.set()


def test_the_deadline_is_the_holders_and_not_the_incoming_jobs(
        sleeper, monkeypatch):
    """The single easiest way to get the lookup wrong. An ``advise`` holder is
    on the slow deadline even when the *incoming* kind is a fast one — read
    the incoming kind instead and a snapshot request would reap a running
    train-and-advise a hundred and twenty seconds in."""
    body, release = sleeper
    monkeypatch.setitem(ABANDON_TIMEOUT_S, "snapshot", 0.05)
    runner = JobRunner({"advise": body, "snapshot": lambda: None})
    runner.start("advise")
    time.sleep(0.1)
    with pytest.raises(JobAlreadyRunning):
        runner.start("snapshot")
    release.set()


def test_a_kind_with_no_override_falls_back_to_the_old_constant(
        sleeper, monkeypatch):
    """Not a ``KeyError`` — that would 500 every POST /api/jobs/{kind} while
    a job was running — and not zero, which would make the single lane
    last-writer-wins. The unlisted kind keeps ``ADVISE_TIMEOUT_S``, which is
    also how the eight slow kinds get theirs."""
    body, release = sleeper
    assert "not-a-real-kind" not in ABANDON_TIMEOUT_S
    monkeypatch.setattr(jobs_module, "ADVISE_TIMEOUT_S", 0.05)
    runner = JobRunner({"not-a-real-kind": body, "evaluate": lambda: None})
    first = runner.start("not-a-real-kind")
    time.sleep(0.1)
    assert isinstance(runner.start("evaluate"), str)
    assert "timed out" in runner.get(first).error
    release.set()


# --- 4-6: what the freed lane says ----------------------------------

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


def test_a_cancel_says_it_was_cancelled(client_and_release):
    """Plan A10's positive rail, and the assertion whose absence let the
    wording be wrong for a whole cycle: every existing assertion on this
    string read either "abandoned" (true both ways) or came off the timeout
    path."""
    client, release, _ = client_and_release
    assert client.post("/api/jobs/advise").status_code == 202
    body = client.delete("/api/jobs/current").json()
    assert "cancelled" in body["error"]
    assert "timed out" not in body["error"]
    release.set()


def test_a_timeout_still_says_it_timed_out_with_the_seconds_in_it(
        sleeper, monkeypatch):
    """The fork must not have swallowed the branch that was already right."""
    body, release = sleeper
    monkeypatch.setitem(ABANDON_TIMEOUT_S, "snapshot", 0.05)
    runner = JobRunner({"snapshot": body, "evaluate": lambda: None})
    first = runner.start("snapshot")
    time.sleep(0.1)
    runner.start("evaluate")
    error = runner.get(first).error
    assert "timed out after 0s" in error
    release.set()


def test_both_branches_keep_the_daemon_sentence(client_and_release,
                                                monkeypatch):
    """The half that is true either way, that v9c's rails already read, and
    that a user needs: the lane is free, the work is not stopped."""
    client, release, _ = client_and_release
    client.post("/api/jobs/advise")
    cancelled = client.delete("/api/jobs/current").json()["error"]
    assert "abandoned as a daemon, its thread still running" in cancelled

    body = threading.Event()
    monkeypatch.setitem(ABANDON_TIMEOUT_S, "snapshot", 0.05)
    runner = JobRunner({"snapshot": lambda: body.wait(5.0),
                        "evaluate": lambda: None})
    first = runner.start("snapshot")
    time.sleep(0.1)
    runner.start("evaluate")
    assert ("abandoned as a daemon, its thread still running"
            in runner.get(first).error)
    body.set()
    release.set()


# --- 7-8: the table, and the living ---------------------------------

def test_every_job_kind_has_a_decided_deadline():
    """A thirteenth kind must not arrive without one. The overrides and the
    named slow set together are exactly ``JOB_KINDS``, so a new kind fails
    here rather than quietly inheriting half an hour."""
    assert set(ABANDON_TIMEOUT_S) | SLOW_ABANDON_KINDS == set(JOB_KINDS)
    assert not (set(ABANDON_TIMEOUT_S) & SLOW_ABANDON_KINDS)
    assert all(v > 0 for v in ABANDON_TIMEOUT_S.values())
    assert kinds_module.FAST_ABANDON_S == jobs_module.WHATIF_TIMEOUT_S


def test_a_normal_run_is_unaffected_end_to_end():
    """The reaper does not reap the living, and nothing above changed that."""
    runner = JobRunner({"snapshot": lambda: {"gw": 5}})
    run = _wait(runner, runner.start("snapshot"))
    assert run.status == "done"
    assert run.error is None
    assert runner.current() is None
