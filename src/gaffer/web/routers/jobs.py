"""The job runner's HTTP surface (spec §5).

Route order matters: ``/api/jobs/current`` is declared before
``/api/jobs/{job_id}`` or the path parameter would swallow the literal.

``GET /api/jobs/{job_id}`` serves *both* runners. The v7 runner owns the ids it
minted; anything else falls through to the v6 ``JobRegistry`` that the what-if
lab and the v6 rerun buttons still poll, so this router can own the path
without breaking them.
"""

from __future__ import annotations

import json
import time
from typing import Iterator

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from gaffer.web.jobs import JobAlreadyRunning
from gaffer.web.schemas import JobRunView, JobStarted

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _view(run) -> JobRunView:
    return JobRunView(**run.as_dict())


@router.post("/{kind}", status_code=202, response_model=JobStarted)
def start(kind: str, request: Request):
    runner = request.app.state.job_runner
    if kind not in runner.kinds:
        raise HTTPException(
            status_code=404,
            detail=f"unknown job kind: {kind} — allowed: "
                   f"{', '.join(sorted(runner.kinds))}")
    try:
        job_id = runner.start(kind)
    except JobAlreadyRunning as exc:
        return JSONResponse(status_code=409,
                            content={"detail": {"running_kind":
                                                exc.running_kind,
                                                "job_id": exc.job_id}})
    return JobStarted(job_id=job_id, kind=kind)


@router.get("/current")
def current(request: Request):
    run = request.app.state.job_runner.current()
    if run is None:
        return Response(status_code=204)
    return _view(run).model_dump()


@router.delete("/current")
def cancel_current(request: Request):
    """Free the lane held by the job running now. 404 when nothing holds it.

    v9c orchestrator-authorized protected edit (plan T7): DELETE
    /api/jobs/current. v9c D4
    (specs/2026-08-31-gaffer-v9c-model-debt-design.md). The runner takes one
    job at a time, so a job that wedges 409s every later job; until v9c the
    only way out was restarting the process, and the 409's own payload named a
    run the caller had no way to clear.

    This does **not** stop the work. The worker is a daemon thread and cannot
    be safely killed — the runner has said so since v6. What it does is
    release the lane and mark the run failed with a reason, so the next job
    can start. Every job kind is idempotent by design (a v8f constraint), so
    the re-run that follows is safe even while the abandoned thread is still
    writing.

    Declared before ``GET /{job_id}`` for the reason this module's docstring
    gives about ``GET /current``: the literal must be matched before the path
    parameter can swallow it.
    """
    run = request.app.state.job_runner.abandon_current()
    if run is None:
        raise HTTPException(status_code=404, detail="no job is running")
    return _view(run).model_dump()


@router.get("/{job_id}")
def status(job_id: str, request: Request):
    run = request.app.state.job_runner.get(job_id)
    if run is not None:
        return _view(run).model_dump()
    legacy = request.app.state.jobs.get(job_id)
    if legacy is None:
        raise HTTPException(status_code=404, detail=f"no such job: {job_id}")
    return legacy


POLL_S = 0.25
"""How often the generator looks for new lines while a job is still running."""

IDLE_TIMEOUT_S = 3600.0
"""A generator gives up after an hour rather than pinning a worker forever."""

HEARTBEAT_S = 15.0
"""Longest the generator may go without writing anything at all.

This is a sync generator running on an anyio worker thread, and a closed client
is only discovered on a write. A job that prints nothing for minutes — a long
MILP solve, a slow fetch — used to mean no write at all, so an abandoned stream
(a reload, and JobButton's mount probe re-attaching) held its worker until the
idle hour was up. A comment frame every few seconds is a write, and the write
is what raises.
"""

HEARTBEAT = ": keep-alive\n\n"
"""An SSE comment: any line starting with ``:``, which EventSource ignores."""


def _sse(name: str, data: str, event_id: int | None = None) -> str:
    prefix = "" if event_id is None else f"id: {event_id}\n"
    return f"{prefix}event: {name}\ndata: {data}\n\n"


@router.get("/{job_id}/stream")
def stream(job_id: str, request: Request, from_: int = Query(0, alias="from")):
    """Every captured line as an event, then a terminal ``end``.

    Hand-rolled rather than a new dependency: this is one generator yielding
    ``text/event-stream`` frames, and ``sse-starlette`` is not installed.

    Reconnects replay from an absolute line index — ``?from=`` or the
    ``Last-Event-ID`` header the browser sends by itself — so a tab that
    dropped mid-run redraws exactly what it missed, out of the 500-line ring
    buffer, rather than the whole scrollback or nothing.

    A quiet run still writes: see ``HEARTBEAT_S``.
    """
    runner = request.app.state.job_runner
    if runner.get(job_id) is None:
        raise HTTPException(status_code=404, detail=f"no such job: {job_id}")
    header = request.headers.get("last-event-id")
    start = from_
    if header is not None and header.strip().isdigit():
        start = int(header.strip()) + 1

    def generate() -> Iterator[str]:
        cursor = start
        deadline = time.monotonic() + IDLE_TIMEOUT_S
        last_write = time.monotonic()
        while True:
            wrote = False
            for index, line in runner.lines_since(job_id, cursor):
                cursor = index + 1
                wrote = True
                yield _sse("line", line, index)
            if wrote:
                last_write = time.monotonic()
            run = runner.get(job_id)
            if run is None:
                break
            if run.status in ("done", "failed"):
                # One last sweep: a line can land between the read above and
                # the status flip, and losing the final line of a failed run is
                # losing the only thing the user needed.
                for index, line in runner.lines_since(job_id, cursor):
                    cursor = index + 1
                    yield _sse("line", line, index)
                yield _sse("end", json.dumps(
                    {"status": run.status, "error": run.error,
                     "summary": run.summary}))
                break
            if time.monotonic() > deadline:
                yield _sse("end", json.dumps(
                    {"status": "failed",
                     "error": "stream idle for an hour — reload the page",
                     "summary": None}))
                break
            if time.monotonic() - last_write >= HEARTBEAT_S:
                last_write = time.monotonic()
                yield HEARTBEAT
            time.sleep(POLL_S)

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})
