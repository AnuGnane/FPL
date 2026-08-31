"""GET /api/sensitivity — the banked robustness report for this week's board.

Read-only and never an error. A week nobody has swept is not a degraded state,
it is every week before the button is pressed, so it is a 200 with
``available: false`` and the card shows the button. A report from an *older*
gameweek is also ``available: false``, with a notice: last week's robustness
is not this week's, and a stale card is worse than an empty one. Its numbers
are still in the body — refusing to headline a stale report is not a reason
to hide what it said — but nothing renders them as current.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from gaffer.artifacts import latest_gw
from gaffer.sensitivity import load_sensitivity
from gaffer.web.schemas import SensitivityReport

router = APIRouter(prefix="/api", tags=["sensitivity"])


@router.get("/sensitivity", response_model=SensitivityReport)
def sensitivity(gw: int | None = Query(default=None)) -> SensitivityReport:
    current = latest_gw()
    wanted = current if gw is None else int(gw)
    if wanted is None:
        return SensitivityReport()
    payload = load_sensitivity(wanted)
    if payload is None:
        return SensitivityReport(
            gw=wanted,
            notice=f"no sensitivity report for GW{wanted} — run it to see "
                   f"how much of this plan survives the forecast being wrong")
    fields = {k: v for k, v in payload.items()
              if k in SensitivityReport.model_fields and k != "available"}
    banked = payload.get("gw")
    if current is not None and banked is not None and int(banked) != current:
        # Served, but not as this week's: the numbers are real and the card is
        # entitled to show what it is refusing to headline.
        return SensitivityReport(available=False, **{
            **fields,
            "notice": f"that sensitivity report is GW{int(banked)}'s and the "
                      f"saved board is GW{current} — re-run the sweep to see "
                      f"how much of *this* plan survives"})
    return SensitivityReport(available=True, **fields)
