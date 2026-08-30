"""The Model Quality page's one endpoint.

Disk-only and deliberately so: `gaffer evaluate` retrains every component and
takes minutes to hours, which is not something a page load may start. The UI
renders the artifact; the CLI makes it.
"""

from __future__ import annotations

import json

from fastapi import APIRouter

from gaffer.errors import GafferError
from gaffer.evaluation import load_evaluation
from gaffer.pen_tracker import tracker_path
from gaffer.web.schemas import PenTracker, Quality

router = APIRouter(prefix="/api", tags=["quality"])


@router.get("/quality", response_model=Quality)
def quality() -> Quality:
    # load_evaluation raises GafferError when the artifact is missing, which
    # the app-wide handler turns into a 422 carrying the "run gaffer
    # evaluate" sentence the empty state prints verbatim.
    return Quality(**load_evaluation())


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
        raise GafferError("no pen tracker report — run gaffer track-pens")
    return PenTracker(**json.loads(path.read_text()))
