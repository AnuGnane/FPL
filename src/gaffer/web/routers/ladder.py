"""GET and POST /api/ladder — the transfer ladder (v13 §3.2).

GET serves the banked payload for the latest gameweek and is a 200 for every
empty state it knows about. POST re-solves it as an anonymous job through
``app.state.jobs``, exactly as ``/api/whatif`` submits, and the job saves the
result so the next GET reflects it. No ``JOB_KINDS`` entry: a kind would need
an abandon-timeout row and a pin move for a computation that takes seconds.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from gaffer.artifacts import latest_gw
from gaffer.errors import GafferError
from gaffer.ladder import build_ladder, load_ladder
from gaffer.web.jobs import WHATIF_TIMEOUT_S, JobQueueFull
from gaffer.web.schemas import JobAccepted, LadderPayload

router = APIRouter(prefix="/api", tags=["ladder"])


@router.get("/ladder", response_model=LadderPayload)
def ladder(gw: int | None = Query(default=None)) -> LadderPayload:
    current = latest_gw()
    wanted = current if gw is None else int(gw)
    if wanted is None:
        return LadderPayload(
            note="no saved solve state — run `gaffer advise` first")
    payload = load_ladder(wanted)
    if payload is None:
        return LadderPayload(
            gw=wanted,
            note=f"no ladder for GW{wanted} — run `gaffer advise` or "
                 f"rebuild it here")
    fields = {k: v for k, v in payload.items()
              if k in LadderPayload.model_fields}
    return LadderPayload(**fields)


@router.post("/ladder", status_code=202, response_model=JobAccepted)
def rebuild(request: Request):
    gw = latest_gw()
    if gw is None:
        raise GafferError("no saved solve state — run `gaffer advise` first")
    try:
        job_id = request.app.state.jobs.submit(
            lambda: build_ladder(gw), timeout_s=WHATIF_TIMEOUT_S)
    except JobQueueFull as exc:
        return JSONResponse(status_code=429, content={"detail": str(exc)})
    return JobAccepted(job_id=job_id)
