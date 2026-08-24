import threading
import time

import pytest

from gaffer.web.jobs import JobQueueFull, JobRegistry


def _wait_for(registry, job_id, status, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = registry.get(job_id)
        if job and job["status"] == status:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} never reached {status}: "
                         f"{registry.get(job_id)}")


def test_a_job_runs_and_carries_its_result():
    registry = JobRegistry()
    job_id = registry.submit(lambda: {"answer": 42}, timeout_s=5.0)
    job = _wait_for(registry, job_id, "done")
    assert job["result"] == {"answer": 42}
    assert job["error"] is None


def test_unknown_job_id_is_none():
    assert JobRegistry().get("nope") is None


def test_an_exception_lands_in_the_job_record_not_the_thread():
    registry = JobRegistry()

    def boom():
        raise ValueError("pool is empty")

    job = _wait_for(registry, registry.submit(boom, timeout_s=5.0), "error")
    assert job["error"] == "pool is empty"
    assert job["result"] is None


def test_the_worker_survives_a_failed_job_and_runs_the_next_one():
    registry = JobRegistry()

    def boom():
        raise ValueError("pool is empty")

    registry.submit(boom, timeout_s=5.0)
    job = _wait_for(registry, registry.submit(lambda: "next", timeout_s=5.0),
                    "done")
    assert job["result"] == "next"


def test_a_slow_job_times_out_and_says_so():
    registry = JobRegistry()
    forever = threading.Event()
    try:
        job_id = registry.submit(lambda: forever.wait(30), timeout_s=0.1)
        job = _wait_for(registry, job_id, "error")
        assert "timed out after 0.1s" in job["error"]
    finally:
        forever.set()


def test_jobs_run_first_in_first_out_on_one_worker():
    registry = JobRegistry()
    order: list[int] = []
    gate = threading.Event()
    registry.submit(lambda: (gate.wait(2), order.append(1)), timeout_s=5.0)
    second = registry.submit(lambda: order.append(2), timeout_s=5.0)
    assert registry.get(second)["status"] == "queued"
    gate.set()
    _wait_for(registry, second, "done")
    assert order == [1, 2]


def test_queue_is_capped_at_five_pending():
    registry = JobRegistry(max_pending=5)
    gate = threading.Event()
    try:
        # Wait for the blocker to be *running* before counting pending jobs,
        # otherwise it would still occupy one of the five queued slots and the
        # test would race the worker thread.
        blocker = registry.submit(lambda: gate.wait(5), timeout_s=5.0)
        _wait_for(registry, blocker, "running")
        for _ in range(5):
            registry.submit(lambda: None, timeout_s=5.0)
        with pytest.raises(JobQueueFull):
            registry.submit(lambda: None, timeout_s=5.0)
    finally:
        gate.set()
