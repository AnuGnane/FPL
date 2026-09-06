"""``GET`` and ``POST /api/decisions/{gw}`` — the deviation note (v16 §5).

GET is 404-free: an absent note is the empty shape with its state. POST
refuses in the settings endpoint's ``{constraint, error, players}`` shape.
"""

from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException

from gaffer.artifacts import upcoming_gw
from gaffer.decisions import (REASONS, TEXT_MAX, note_for, note_state,
                              save_note)
from gaffer.web.schemas import DecisionNote, DecisionWrite

router = APIRouter(prefix="/api", tags=["decisions"])


def _now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def _fail(constraint: str, error: str) -> HTTPException:
    return HTTPException(status_code=422,
                         detail={"constraint": constraint, "error": error,
                                 "players": []})


def _view(gw: int) -> DecisionNote:
    state, deadline, grade = note_state(gw, now=_now())
    return DecisionNote(**note_for(gw), state=state, deadline=deadline,
                        grade=grade)


@router.get("/decisions/{gw}", response_model=DecisionNote)
def decision(gw: int) -> DecisionNote:
    return _view(gw)


@router.post("/decisions/{gw}", response_model=DecisionNote)
def save(gw: int, req: DecisionWrite) -> DecisionNote:
    if req.reason not in REASONS:
        raise _fail("unknown_reason",
                    f"the reason is one of {', '.join(REASONS)}")
    if len(req.text or "") > TEXT_MAX:
        raise _fail("text_too_long", f"the note is at most {TEXT_MAX} characters")
    try:
        nxt = upcoming_gw()
    except Exception:  # noqa: BLE001 — no snapshot is no rule
        nxt = None
    if nxt is not None and int(gw) > int(nxt):
        raise _fail("future_gw", f"GW{gw} is past the next deadline (GW{nxt})")
    state, _, _ = note_state(gw, now=_now())
    if state == "before_deadline":
        raise _fail("not_open", f"GW{gw}'s note opens at the deadline")
    if state == "graded":
        raise _fail("graded", f"GW{gw} has been graded; the note is closed")
    save_note(gw, req.reason, req.text or "")
    return _view(gw)
