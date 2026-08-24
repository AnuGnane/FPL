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

import queue
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
