"""The Model Quality page's one endpoint.

Disk-only and deliberately so: `gaffer evaluate` retrains every component and
takes minutes to hours, which is not something a page load may start. The UI
renders the artifact; the CLI makes it.
"""

from __future__ import annotations

from fastapi import APIRouter

from gaffer.evaluation import load_evaluation
from gaffer.web.schemas import Quality

router = APIRouter(prefix="/api", tags=["quality"])


@router.get("/quality", response_model=Quality)
def quality() -> Quality:
    # load_evaluation raises GafferError when the artifact is missing, which
    # the app-wide handler turns into a 422 carrying the "run gaffer
    # evaluate" sentence the empty state prints verbatim.
    return Quality(**load_evaluation())
