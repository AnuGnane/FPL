"""The Model Quality page's one endpoint.

Disk-only and deliberately so: `gaffer evaluate` retrains every component and
takes minutes to hours, which is not something a page load may start. The UI
renders the artifact; the CLI makes it.
"""

from __future__ import annotations

import json

from fastapi import APIRouter
from pydantic import ValidationError

from gaffer.errors import GafferError
from gaffer.evaluation import EVALUATION_PATH, load_evaluation
from gaffer.pen_tracker import tracker_path
from gaffer.web.schemas import CalibrationReport, PenTracker, Quality

router = APIRouter(prefix="/api", tags=["quality"])

EMPTY_NOTE = "Run `gaffer evaluate --calibration` after a graded gameweek."
"""The CLI-only story spec §4 asks the UI to tell, written once.

There is no ``calibration`` job kind and there cannot be a flag: ``JOB_KINDS``
maps a kind to a **zero-argument** callable (plan A14). So the command is the
answer to "why is this empty", and both the empty payload and the card's empty
state say it in these words.
"""


@router.get("/quality", response_model=Quality)
def quality() -> Quality:
    # load_evaluation raises GafferError when the artifact is missing, which
    # the app-wide handler turns into a 422 carrying the "run gaffer
    # evaluate" sentence the empty state prints verbatim.
    stored = load_evaluation()
    try:
        return Quality(**stored)
    except (ValidationError, TypeError) as exc:
        # Same reasoning as pens() below: a well-formed artifact from an older
        # schema — a mode whose sub-model has since gained a required field —
        # is "re-run the CLI", not a 500. The page has a fix to print, and the
        # empty state prints this sentence verbatim, so hand it the sentence
        # rather than a stack trace.
        raise GafferError(
            "evaluation report is from an older schema — re-run "
            "`gaffer evaluate`") from exc


@router.get("/model/calibration", response_model=CalibrationReport)
def calibration() -> CalibrationReport:
    """The banked calibration report, or an honest empty one.

    200 with ``available: false`` rather than the 422 :func:`quality` answers,
    and deliberately (spec §4). This card renders beside populated ones on the
    same tab; a 422 there is indistinguishable from a broken endpoint, while an
    empty payload carries the sentence that says what to run.

    Disk-only, like everything else in this module: ``gaffer evaluate
    --calibration`` makes the artifact, the page renders it.
    """
    if not EVALUATION_PATH.exists():
        # No artifact at all is the ordinary state of a fresh machine, and it
        # is empty rather than an error. A *corrupt* one is not: that goes
        # through load_evaluation's GafferError to the 422 with the sentence
        # naming the CLI, exactly as quality() and pens() answer it.
        return CalibrationReport(note=EMPTY_NOTE)
    stored = load_evaluation()
    payload = stored.get("calibration")
    if not payload:
        return CalibrationReport(note=EMPTY_NOTE)
    try:
        return CalibrationReport(available=True, **payload)
    except (ValidationError, TypeError) as exc:
        # Same reasoning as quality() and pens(): a well-formed artifact from
        # an older schema is "re-run the CLI", not a 500.
        raise GafferError(
            "calibration report is from an older schema — re-run "
            "`gaffer evaluate --calibration`") from exc


@router.get("/pens", response_model=PenTracker)
def pens() -> PenTracker:
    """The penalty tracker artifact, read off disk.

    ``json.loads(read_text())`` rather than pandas: the file is one small
    hand-written dict and going through a frame would only lose the nulls
    that ``taker_hit_rate`` deliberately carries.
    """
    path = tracker_path()
    if not path.exists():
        # The app-wide GafferError handler turns this into the 422 whose
        # sentence the empty state prints verbatim.
        raise GafferError("no pen tracker report — run `gaffer track-pens` first")
    try:
        return PenTracker(**json.loads(path.read_text()))
    except (json.JSONDecodeError, ValidationError, OSError, TypeError) as exc:
        # A run killed mid-write leaves truncated JSON; an artifact from an
        # older schema leaves the wrong shape. Both are "re-run the CLI", not
        # a 500 — the page has a fix to print, so print it.
        raise GafferError(
            "pen tracker report is unreadable — re-run `gaffer track-pens`"
        ) from exc
