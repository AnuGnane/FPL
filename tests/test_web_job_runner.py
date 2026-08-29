"""The v7 kind-keyed runner. The v6 JobRegistry in the same module is
untouched and has its own suite in tests/test_web_jobs.py."""

import io
import sys
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


# --- stdout capture is per-thread, not per-process --------------------------
#
# redirect_stdout swaps a process-global. While a job ran, *every* other thread
# in the server — a request handler logging a warning, uvicorn's own access
# line — had its output swallowed into that job's log, and the operator's
# terminal went silent for the minutes an advise takes.


def test_another_threads_print_reaches_the_real_stdout_and_not_the_job_log(
        monkeypatch):
    real = io.StringIO()
    monkeypatch.setattr(sys, "stdout", real)

    job_printed = threading.Event()
    outsider_done = threading.Event()

    def body():
        print("job line one")
        job_printed.set()
        assert outsider_done.wait(5), "the other thread never printed"
        print("job line two")

    runner = JobRunner({"advise": body})
    job_id = runner.start("advise")

    def outsider():
        assert job_printed.wait(5), "the job never started printing"
        print("a request handler, mid-job")
        outsider_done.set()

    thread = threading.Thread(target=outsider)
    thread.start()
    thread.join(5)
    run = _wait(runner, job_id)

    assert run.status == "done", run.error
    # The job's lines went to the job.
    assert run.lines == ["job line one", "job line two"]
    # The other thread's line went to the terminal, and only there.
    assert "a request handler, mid-job" in real.getvalue()
    assert "a request handler, mid-job" not in "".join(run.lines)
    assert "job line one" not in real.getvalue()


def test_stdout_and_stderr_are_restored_even_when_the_job_raises(monkeypatch):
    real = io.StringIO()
    monkeypatch.setattr(sys, "stdout", real)
    monkeypatch.setattr(sys, "stderr", real)

    runner = JobRunner({"advise": lambda: 1 / 0})
    _wait(runner, runner.start("advise"))
    assert sys.stdout is real
    assert sys.stderr is real


def test_a_jobs_stderr_is_captured_too():
    def body():
        print("to stderr", file=sys.stderr)

    runner = JobRunner({"advise": body})
    run = _wait(runner, runner.start("advise"))
    assert "to stderr" in run.lines


def test_concurrent_writers_do_not_interleave_within_a_line():
    """_LineWriter buffers a partial line in an attribute. Two threads writing
    into it without a lock lose fragments to a read-modify-write race."""
    from gaffer.web.jobs import _LineWriter

    seen = []
    writer = _LineWriter(seen.append)
    start = threading.Barrier(9)

    def spam(tag):
        start.wait()
        for _ in range(200):
            writer.write(f"{tag * 20}\n")

    threads = [threading.Thread(target=spam, args=(c,)) for c in "abcdefgh"]
    for t in threads:
        t.start()
    start.wait()
    for t in threads:
        t.join(10)

    assert len(seen) == 8 * 200
    # Every emitted line is one tag repeated, never a splice of two writers.
    assert all(line == line[0] * 20 for line in seen), \
        [line for line in seen if line != line[0] * 20][:3]


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


class _WatchingLock:
    """The runner's lock, recording the state visible at every release.

    Another thread can only observe the runner between a release and the next
    acquire, so a snapshot taken at each release covers every window there is.
    """

    def __init__(self, runner):
        self._lock = threading.Lock()
        self._runner = runner
        self.seen: list[tuple[str | None, dict[str, str]]] = []

    def acquire(self, *args, **kwargs):
        return self._lock.acquire(*args, **kwargs)

    def release(self):
        runner = self._runner
        self.seen.append((runner._current,
                          {i: r.status for i, r in runner._runs.items()}))
        self._lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()


def test_the_lane_is_released_together_with_the_terminal_status():
    """A tab that saw `done` and posted its next job was occasionally told 409:
    the status flipped in one locked block and the lane cleared in the next."""
    runner = JobRunner({"advise": lambda: print("done")})
    watcher = _WatchingLock(runner)
    runner._lock = watcher
    _wait(runner, runner.start("advise"))

    assert runner.current() is None
    for current, statuses in watcher.seen:
        assert current is None or statuses[current] not in ("done", "failed")


def test_the_lane_is_released_together_with_a_failure_too():
    def boom():
        raise RuntimeError("no models on disk")

    runner = JobRunner({"advise": boom})
    watcher = _WatchingLock(runner)
    runner._lock = watcher
    _wait(runner, runner.start("advise"))

    assert runner.current() is None
    for current, statuses in watcher.seen:
        assert current is None or statuses[current] not in ("done", "failed")
