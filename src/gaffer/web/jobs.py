"""A very small in-process job runner.

One worker thread, FIFO, capped queue. That is the whole design: the only
long operations are a MILP re-solve (seconds) and a full train+advise
(minutes), and running two of either at once would fight over the same CPU
and the same ``reports/`` directory.

Timeouts are enforced by running each job on its own short-lived thread and
joining with a deadline. A timed-out job's thread is *not* killed — Python
has no safe way to do that — it is abandoned as a daemon and its result
discarded, which is acceptable because every job here either writes its own
artifacts idempotently or writes nothing at all.
"""

from __future__ import annotations

import contextlib
import io
import queue
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

WHATIF_TIMEOUT_S = 120.0
"""Spec §2.1: a what-if re-solve is a pure MILP run and should take seconds."""

ADVISE_TIMEOUT_S = 1800.0
"""Spec §2.1: train + advise from cold is minutes, not seconds."""

MAX_PENDING = 5
"""Beyond this the API answers 429 rather than growing an unbounded backlog."""


class JobQueueFull(RuntimeError):
    """Raised by :meth:`JobRegistry.submit` when the queue is at capacity."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _Job:
    id: str
    status: str = "queued"          # queued | running | done | error
    result: Any | None = None
    error: str | None = None
    submitted_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None

    def as_dict(self) -> dict:
        return {"id": self.id, "status": self.status, "result": self.result,
                "error": self.error, "submitted_at": self.submitted_at,
                "started_at": self.started_at,
                "finished_at": self.finished_at}


class JobRegistry:
    def __init__(self, max_pending: int = MAX_PENDING) -> None:
        self._max_pending = max_pending
        self._jobs: dict[str, _Job] = {}
        self._lock = threading.Lock()
        self._queue: queue.Queue = queue.Queue()
        self._worker = threading.Thread(target=self._run, daemon=True,
                                        name="gaffer-jobs")
        self._worker.start()

    def submit(self, fn: Callable[[], Any], timeout_s: float) -> str:
        """Queue ``fn``; returns the job id. Raises :class:`JobQueueFull`."""
        with self._lock:
            pending = sum(1 for j in self._jobs.values()
                          if j.status == "queued")
            if pending >= self._max_pending:
                raise JobQueueFull(
                    f"{pending} jobs already queued — wait for one to finish")
            job = _Job(id=uuid.uuid4().hex)
            self._jobs[job.id] = job
        self._queue.put((job.id, fn, timeout_s))
        return job.id

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.as_dict() if job else None

    def _set(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in fields.items():
                setattr(job, key, value)

    def _run(self) -> None:
        while True:
            job_id, fn, timeout_s = self._queue.get()
            self._set(job_id, status="running", started_at=_now())
            box: dict[str, Any] = {}

            def target() -> None:
                try:
                    box["result"] = fn()
                except BaseException as exc:      # noqa: BLE001
                    # Nothing may escape into the worker: an unhandled
                    # exception here would kill the only worker thread and
                    # every later job would sit queued forever.
                    box["error"] = str(exc) or exc.__class__.__name__

            runner = threading.Thread(target=target, daemon=True)
            runner.start()
            runner.join(timeout_s)
            if runner.is_alive():
                self._set(job_id, status="error", finished_at=_now(),
                          error=f"timed out after {timeout_s}s")
            elif "error" in box:
                self._set(job_id, status="error", finished_at=_now(),
                          error=box["error"])
            else:
                self._set(job_id, status="done", finished_at=_now(),
                          result=box.get("result"))


# --- v7 kind-keyed runner ------------------------------------------------
#
# Separate from JobRegistry above, deliberately. The registry queues anonymous
# callables for the what-if lab, where five pending re-solves is a reasonable
# thing to want. This runner is the opposite shape: four *named* long jobs that
# all write to reports/, exactly one of which may ever run, whose stdout is the
# progress bar the browser watches.

JOB_LINE_CAP = 500
"""Lines held per job (spec §5). Enough for a reconnecting tab to redraw."""


class JobAlreadyRunning(RuntimeError):
    """Raised by :meth:`JobRunner.start` while another job holds the lane."""

    def __init__(self, running_kind: str, job_id: str) -> None:
        super().__init__(f"{running_kind} is already running")
        self.running_kind = running_kind
        self.job_id = job_id


@dataclass
class JobRun:
    """One run of one kind. In memory only: a restart forgets, artifacts stay."""

    id: str
    kind: str
    status: str = "running"          # queued | running | done | failed
    lines: list[str] = field(default_factory=list)
    first_line_index: int = 0
    """Absolute index of ``lines[0]`` once the cap has begun dropping lines."""
    error: str | None = None
    summary: str | None = None
    started_at: str = field(default_factory=_now)
    finished_at: str | None = None

    def as_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "status": self.status,
                "error": self.error, "summary": self.summary,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "line_count": self.first_line_index + len(self.lines)}


class _LineWriter(io.TextIOBase):
    """A file-like that forwards whole lines to a callback.

    The partial line lives in an attribute, and ``print`` makes two ``write``
    calls (the text, then the newline) — an unlocked read-modify-write. Nothing
    races on it today: ``_ThreadRouter`` sends only the owner thread's writes
    here, and the closing ``flush`` is on that thread too. The lock stays
    because the invariant is one shared reference away from being false again
    and a spliced or vanished fragment fails silently.
    """

    def __init__(self, emit: Callable[[str], None]) -> None:
        self._emit = emit
        self._buffer = ""
        self._lock = threading.Lock()

    def write(self, text: str) -> int:
        with self._lock:
            self._buffer += text
            lines = []
            while "\n" in self._buffer:
                line, _, self._buffer = self._buffer.partition("\n")
                lines.append(line)
        # Emitted outside the lock: the callback takes the runner's lock, and
        # holding two in a fixed order here would invite the reverse elsewhere.
        for line in lines:
            self._emit(line)
        return len(text)

    def flush(self) -> None:
        with self._lock:
            pending, self._buffer = self._buffer, ""
        if pending:
            self._emit(pending)


class _ThreadRouter(io.TextIOBase):
    """Sends one thread's writes to ``captured``; everyone else's to ``passthrough``.

    ``contextlib.redirect_stdout`` swaps a process-global, so for the minutes an
    advise run takes it captured output from *every* thread in the process — a
    request handler's warning, uvicorn's access log — into that job's line
    buffer, and the operator's terminal went dark. Only the job's own thread
    should be captured; this routes by the ident recorded when the job started.
    """

    def __init__(self, owner_ident: int, captured: io.TextIOBase,
                 passthrough) -> None:
        self._owner = owner_ident
        self._captured = captured
        self._passthrough = passthrough

    def _target(self):
        return (self._captured if threading.get_ident() == self._owner
                else self._passthrough)

    def write(self, text: str) -> int:
        return self._target().write(text)

    def flush(self) -> None:
        target = self._target()
        # A stream can be closed under us (a redirected terminal at shutdown);
        # losing a flush must not fail the job that was only logging.
        with contextlib.suppress(ValueError, OSError):
            target.flush()

    def isatty(self) -> bool:
        # Progress bars ask. The job's log is not a terminal, and anything the
        # passthrough says about itself is its own business.
        target = self._target()
        try:
            return bool(target.isatty())
        except (AttributeError, ValueError):
            return False


class JobRunner:
    """Single-flight execution of the registered job kinds."""

    def __init__(self, kinds: dict[str, Callable[[], Any]]) -> None:
        self._kinds = dict(kinds)
        self._runs: dict[str, JobRun] = {}
        self._current: str | None = None
        self._lock = threading.Lock()

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(self._kinds)

    def _abandon_current(self, older_than: float) -> JobRun | None:
        """Free the lane if the job holding it has been running too long.

        Called with the lock held. Returns the run it abandoned, or ``None``
        if the lane was empty or its holder is younger than ``older_than``.

        v9c orchestrator-authorized protected edit (plan T7): the
        ``_abandon_current`` helper. v9c D4
        (specs/2026-08-31-gaffer-v9c-model-debt-design.md).
        ``ADVISE_TIMEOUT_S`` has had no reader since it was written: this
        runner, unlike the ``JobRegistry`` above it, never enforced a
        deadline, so a job that wedged held the single lane until the process
        restarted and every later job got a 409 naming a run nobody could
        clear.

        The worker thread is **not** killed. It is a daemon, Python has no
        safe way to stop one, and the module has said so since v6 (see the
        docstring at the top of this file). Abandonment frees the lane and
        discards the result; the thread runs on and its writes are harmless
        because every job kind writes its artifacts idempotently or writes
        nothing at all.

        The status is ``"failed"`` rather than a new ``"abandoned"`` value.
        ``JobRun.status``'s vocabulary is fixed, and more to the point the SSE
        generator in ``routers/jobs.py`` ends a stream only on ``done`` or
        ``failed`` — a new value would leave every watching browser polling
        for the full idle hour. The explanation goes in ``error``, where the
        UI already shows it.
        """
        if self._current is None:
            return None
        run = self._runs[self._current]
        age = (datetime.now(timezone.utc)
               - datetime.fromisoformat(run.started_at)).total_seconds()
        if age < older_than:
            return None
        run.status = "failed"
        run.error = (f"timed out after {older_than:.0f}s — abandoned as a "
                     f"daemon, its thread still running")
        run.finished_at = _now()
        self._current = None
        return run

    def abandon_current(self) -> JobRun | None:
        """Free the lane now, however old its holder is. ``None`` when idle.

        v9c orchestrator-authorized protected edit (plan T7): the public
        wrapper on ``_abandon_current``, for ``DELETE /api/jobs/current``.
        One locked block for the whole state change, for the reason
        ``_execute``'s ``finally`` gives below.
        """
        with self._lock:
            return self._abandon_current(0.0)

    def start(self, kind: str) -> str:
        if kind not in self._kinds:
            raise KeyError(kind)
        with self._lock:
            # v9c orchestrator-authorized protected edit (plan T7): reap a
            # wedged holder before refusing the new job. Until v9c the 409
            # below was permanent — the lane was cleared only by _execute's
            # finally, so a job that never returned blocked every later job
            # until the process restarted. v9c D4.
            self._abandon_current(ADVISE_TIMEOUT_S)
            if self._current is not None:
                running = self._runs[self._current]
                raise JobAlreadyRunning(running.kind, running.id)
            run = JobRun(id=uuid.uuid4().hex, kind=kind)
            self._runs[run.id] = run
            self._current = run.id
        threading.Thread(target=self._execute, args=(run,), daemon=True,
                         name=f"gaffer-job-{kind}").start()
        return run.id

    def get(self, job_id: str) -> JobRun | None:
        with self._lock:
            return self._runs.get(job_id)

    def current(self) -> JobRun | None:
        with self._lock:
            return None if self._current is None else self._runs[self._current]

    def lines_since(self, job_id: str, index: int) -> list[tuple[int, str]]:
        """``[(absolute index, line)]`` from ``index`` on; [] past the end."""
        with self._lock:
            run = self._runs.get(job_id)
            if run is None:
                return []
            start = max(index - run.first_line_index, 0)
            return [(run.first_line_index + i, line)
                    for i, line in enumerate(run.lines[start:], start=start)]

    def _append(self, run: JobRun, line: str) -> None:
        with self._lock:
            run.lines.append(line)
            if len(run.lines) > JOB_LINE_CAP:
                dropped = len(run.lines) - JOB_LINE_CAP
                del run.lines[:dropped]
                run.first_line_index += dropped

    def _execute(self, run: JobRun) -> None:
        writer = _LineWriter(lambda line: self._append(run, line))
        # This thread's ident, captured before the body runs: it is the one
        # whose writes belong in the job log. Everything else the process
        # prints while the job holds the lane goes on reaching the terminal.
        mine = threading.get_ident()
        real_out, real_err = sys.stdout, sys.stderr
        sys.stdout = _ThreadRouter(mine, writer, real_out)
        sys.stderr = _ThreadRouter(mine, writer, real_err)
        status, error, summary = "failed", None, None
        try:
            result = self._kinds[run.kind]()
            status = "done"
            summary = None if result is None else str(result)
        except BaseException as exc:      # noqa: BLE001 — nothing may escape
            error = str(exc) or exc.__class__.__name__
        finally:
            writer.flush()
            # Restore before the terminal flip: the moment the lane is free the
            # next job may start, and it must not inherit a dead router.
            sys.stdout, sys.stderr = real_out, real_err
            with self._lock:
                # One locked block for the whole ending. Flipping the status in
                # one and clearing the lane in a later one left a window where
                # a browser that had just been told `done` posted its next job
                # and was answered 409 by a runner with nothing running.
                #
                # v9c orchestrator-authorized protected edit (plan T7): the
                # _execute finally guard, so an abandoned thread can neither
                # steal the lane nor erase the abandon record. Both halves are
                # conditional, because this thread may have been abandoned
                # while it ran. Overwriting the status would erase the record
                # of why the lane was freed, and — far worse — clearing
                # _current unconditionally would clear a lane that by now
                # belongs to a *different*, newer job. v9c D4.
                if run.status == "running":
                    run.status = status
                    run.error = error
                    run.summary = summary
                    run.finished_at = _now()
                if self._current == run.id:
                    self._current = None
