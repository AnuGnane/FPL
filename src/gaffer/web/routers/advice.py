"""This Week: the saved advice payload, its staleness, and a re-run job."""

from __future__ import annotations

import json

import pandas as pd
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from gaffer.artifacts import (advice_history_files, data_warning,
                              diff_advice, ingested_through, latest_gw,
                              load_advice, load_solve_state, upcoming_gw)
from gaffer.errors import GafferError
from gaffer.web.jobs import ADVISE_TIMEOUT_S, JobQueueFull
from gaffer.web.schemas import (AdviceDiff, AdviceLatest, JobAccepted,
                                Staleness)

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
    # Read from the parquet, not from the stored advice payload: an advice
    # file written days ago still gets today's answer about what the model
    # has actually ingested.
    through = ingested_through()
    return Staleness(advice_gw=advice_gw, current_gw=current,
                     generated_at=generated_at, deadline=deadline,
                     deadline_passed=passed, stale=bool(behind or passed),
                     reason=reason, data_through_gw=through,
                     data_warning=data_warning(current, through))


PLAYER_KEYS = ("xi", "bench", "buys", "sells", "captain", "vice")
"""Advice keys holding player dicts the UI renders by position."""


def with_positions(payload: dict, pool: pd.DataFrame) -> dict:
    """Backfill ``position`` on player entries written before it was saved.

    ``advise`` only started emitting positions in v3.1, and a user with last
    week's advice on disk must not have to re-run the whole pipeline to get a
    pitch. The solved pool already knows every candidate's position, so read
    it from there and leave anything already positioned alone.
    """
    pos_of = {int(c): str(p)
              for c, p in zip(pool["code"], pool["position"])}

    def fill(entry: dict) -> dict:
        if entry.get("position"):
            return entry
        return {**entry, "position": pos_of.get(int(entry["code"]), "")}

    out = dict(payload)
    for key in PLAYER_KEYS:
        value = out.get(key)
        if isinstance(value, list):
            out[key] = [fill(e) for e in value if isinstance(e, dict)]
        elif isinstance(value, dict) and "code" in value:
            out[key] = fill(value)
    return out


@router.get("/latest", response_model=AdviceLatest)
def latest() -> AdviceLatest:
    gw = latest_gw()
    if gw is None:
        raise GafferError("no advice on disk yet — run `gaffer advise` first")
    state = load_solve_state(gw)
    payload = with_positions(load_advice(gw), state.pool)
    return AdviceLatest(
        gw=gw, mode=state.mode, deadline=state.deadline, advice=payload,
        staleness=staleness_for(gw, state.deadline, state.generated_at))


@router.get("/diff", response_model=AdviceDiff)
def diff(gw: int | None = None) -> AdviceDiff:
    """The "since last run" strip: this run against the one before it.

    Same gameweek only. Re-running on Friday after the press conferences is
    the case this exists for, and comparing Friday's GW5 plan with last week's
    GW4 plan would answer a question nobody asked.

    Never an error. A first run of the week, a wiped ``reports/`` directory
    and a history file that will not parse all land in the same place: the
    strip is not shown, and the rest of This Week renders exactly as it did.
    """
    target = gw if gw is not None else latest_gw()
    if target is None:
        return AdviceDiff(gw=0, available=False)
    files = advice_history_files(int(target))
    if len(files) < 2:
        return AdviceDiff(gw=int(target), available=False)
    previous_path, current_path = files[-2], files[-1]
    try:
        previous = json.loads(previous_path.read_text())
        current = json.loads(current_path.read_text())
    except (OSError, ValueError) as exc:
        # OSError as well as ValueError: the file was listed a moment ago, so
        # a rerun rotating history underneath the read, or a permission the
        # server lost, is exactly as much of a "no diff to show" as malformed
        # JSON is — and the strip promises never to be an error.
        print(f"advice history unreadable, no diff shown: {exc}")
        return AdviceDiff(gw=int(target), available=False)
    out = diff_advice(previous, current)
    return AdviceDiff(
        gw=int(target), available=True,
        previous_at=previous_path.stem.partition("-")[2],
        current_at=current_path.stem.partition("-")[2], **out)


@router.post("/rerun", status_code=202, response_model=JobAccepted)
def rerun(request: Request):
    try:
        job_id = request.app.state.jobs.submit(run_train_and_advise,
                                               timeout_s=ADVISE_TIMEOUT_S)
    except JobQueueFull as exc:
        return JSONResponse(status_code=429, content={"detail": str(exc)})
    return JobAccepted(job_id=job_id)
