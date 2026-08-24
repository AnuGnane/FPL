"""This Week: the saved advice payload, its staleness, and a re-run job."""

from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from gaffer.artifacts import (latest_gw, load_advice, load_solve_state,
                              upcoming_gw)
from gaffer.errors import GafferError
from gaffer.web.jobs import ADVISE_TIMEOUT_S, JobQueueFull
from gaffer.web.schemas import AdviceLatest, JobAccepted, Staleness

router = APIRouter(prefix="/api/advice", tags=["advice"])


def run_train_and_advise() -> dict:
    """The job body: exactly what the launchd Thursday run does."""
    from gaffer.advise import run_advise
    from gaffer.config import load_config
    from gaffer.models.train import load_training_frame, train_all
    from gaffer.report.render import render_report
    from gaffer.tracking import latest_health

    frame, team_frame, _ = load_training_frame()
    train_all(frame, team_frame, save=True)
    advice = run_advise(load_config())
    render_report(advice, model_health=latest_health())
    return {"gw": advice.gw, "expected_pts": advice.expected_pts}


def staleness_for(advice_gw: int, deadline: str,
                  generated_at: str) -> Staleness:
    """Server-side staleness — the client only displays it (spec §4)."""
    current = upcoming_gw()
    stamp = pd.Timestamp(deadline)
    stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None \
        else stamp.tz_convert("UTC")
    passed = stamp < pd.Timestamp.now(tz="UTC")
    behind = current is not None and current > advice_gw
    if behind:
        reason = (f"this advice is for GW{advice_gw}; GW{current} is the next "
                  f"deadline")
    elif passed:
        reason = f"GW{advice_gw}'s deadline has passed"
    else:
        reason = f"current for GW{advice_gw}"
    return Staleness(advice_gw=advice_gw, current_gw=current,
                     generated_at=generated_at, deadline=deadline,
                     deadline_passed=passed, stale=bool(behind or passed),
                     reason=reason)


@router.get("/latest", response_model=AdviceLatest)
def latest() -> AdviceLatest:
    gw = latest_gw()
    if gw is None:
        raise GafferError("no advice on disk yet — run `gaffer advise` first")
    state = load_solve_state(gw)
    payload = load_advice(gw)
    return AdviceLatest(
        gw=gw, mode=state.mode, deadline=state.deadline, advice=payload,
        staleness=staleness_for(gw, state.deadline, state.generated_at))


@router.post("/rerun", status_code=202, response_model=JobAccepted)
def rerun(request: Request):
    try:
        job_id = request.app.state.jobs.submit(run_train_and_advise,
                                               timeout_s=ADVISE_TIMEOUT_S)
    except JobQueueFull as exc:
        return JSONResponse(status_code=429, content={"detail": str(exc)})
    return JobAccepted(job_id=job_id)
