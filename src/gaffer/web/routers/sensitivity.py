"""GET /api/sensitivity — the banked robustness report for this week's board.

Read-only and never an error. A week nobody has swept is not a degraded state,
it is every week before the button is pressed, so it is a 200 with
``available: false`` and the card shows the button. A report from an *older*
gameweek is also ``available: false``, with a notice: last week's robustness
is not this week's, and a stale card is worse than an empty one.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from gaffer.artifacts import latest_gw
from gaffer.sensitivity import load_sensitivity
from gaffer.web.schemas import SensitivityReport

router = APIRouter(prefix="/api", tags=["sensitivity"])


@router.get("/sensitivity", response_model=SensitivityReport)
def sensitivity(gw: int | None = Query(default=None)) -> SensitivityReport:
    wanted = latest_gw() if gw is None else int(gw)
    if wanted is None:
        return SensitivityReport()
    payload = load_sensitivity(wanted)
    if payload is None:
        return SensitivityReport(
            gw=wanted,
            notice=f"no sensitivity report for GW{wanted} — run it to see "
                   f"how much of this plan survives the forecast being wrong")
    return SensitivityReport(available=True, **{
        k: v for k, v in payload.items()
        if k in SensitivityReport.model_fields and k != "available"})
