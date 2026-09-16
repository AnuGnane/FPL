"""``POST /api/ask`` — one question about this week, answered from the
brief's facts as an anonymous job (v19f §2.2: no thirteenth ``JOB_KINDS``
entry, exactly as ``POST /api/brief`` writes a brief)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from gaffer.brief import answer_question, check_question
from gaffer.web.jobs import JobQueueFull
from gaffer.web.routers.brief import BRIEF_TIMEOUT_MARGIN_S
from gaffer.web.schemas import AskRequest, JobAccepted

router = APIRouter(prefix="/api", tags=["ask"])


@router.post("/ask", status_code=202, response_model=JobAccepted)
def ask(request: Request, body: AskRequest):
    from gaffer.config import config_in_force

    # v19f §2.1: the length is decided here, before a job exists, so a refusal
    # is a synchronous 422 and not a job the reader has to poll to be told no.
    try:
        question = check_question(body.question)
    except ValueError as exc:
        return JSONResponse(status_code=422, content={"detail": str(exc)})
    gw = body.gw
    timeout = float(config_in_force().news_llm_timeout_s) + BRIEF_TIMEOUT_MARGIN_S
    try:
        job_id = request.app.state.jobs.submit(
            lambda: answer_question(question, gw, cfg=config_in_force()),
            timeout_s=timeout)
    except JobQueueFull as exc:
        return JSONResponse(status_code=429, content={"detail": str(exc)})
    return JobAccepted(job_id=job_id)
