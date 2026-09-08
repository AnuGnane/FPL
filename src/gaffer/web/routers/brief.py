"""``GET /api/brief`` — the newest brief or the digest panel to fall back on;
``POST /api/brief`` — write one now, as an anonymous job (plan R1: no
thirteenth ``JOB_KINDS`` entry, exactly as ``/api/ladder`` rebuilds)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from gaffer.brief import latest_brief, load_note, run_brief
from gaffer.web.jobs import JobQueueFull
from gaffer.web.routers.digest import digest as digest_panel
from gaffer.web.schemas import BriefPanel, JobAccepted

router = APIRouter(prefix="/api", tags=["brief"])

BRIEF_TIMEOUT_MARGIN_S = 60.0


@router.get("/brief", response_model=BriefPanel)
def brief() -> BriefPanel:
    payload = latest_brief()
    if payload is not None:
        return BriefPanel(gw=payload.get("gw"), prose=payload.get("prose"),
                          checked_at=payload.get("checked_at"),
                          run_stamp=payload.get("run_stamp"),
                          model_command=payload.get("model_command"))
    note = load_note() or {}
    return BriefPanel(note=note.get("note"), fallback=digest_panel())


@router.post("/brief", status_code=202, response_model=JobAccepted)
def write(request: Request):
    from gaffer.config import config_in_force

    timeout = float(config_in_force().news_llm_timeout_s) + BRIEF_TIMEOUT_MARGIN_S
    try:
        job_id = request.app.state.jobs.submit(lambda: run_brief(), timeout_s=timeout)
    except JobQueueFull as exc:
        return JSONResponse(status_code=429, content={"detail": str(exc)})
    return JobAccepted(job_id=job_id)
