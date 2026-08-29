"""The job runner's HTTP surface (spec §5).

Route order matters: ``/api/jobs/current`` is declared before
``/api/jobs/{job_id}`` or the path parameter would swallow the literal.

``GET /api/jobs/{job_id}`` serves *both* runners. The v7 runner owns the ids it
minted; anything else falls through to the v6 ``JobRegistry`` that the what-if
lab and the v6 rerun buttons still poll, so this router can own the path
without breaking them.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

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


@router.get("/{job_id}")
def status(job_id: str, request: Request):
    run = request.app.state.job_runner.get(job_id)
    if run is not None:
        return _view(run).model_dump()
    legacy = request.app.state.jobs.get(job_id)
    if legacy is None:
        raise HTTPException(status_code=404, detail=f"no such job: {job_id}")
    return legacy
