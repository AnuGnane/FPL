"""GET /api/review — the banked decision ledger (spec F3).

Never an error, and for a sharper reason than the journal's: an unreviewed
season is not a degraded state, it is the state every season begins in. So the
empty ledger is a 200 with an empty body and the hub shows a "Review" button,
where a 422 would show a retry button for something that did not fail.

All the arithmetic happened at review time (spec D2). This module reads a JSON
file and adds up a summary; it grades nothing, fetches nothing, and cannot be
slow.
"""

from __future__ import annotations

from fastapi import APIRouter

from gaffer.review import load_ledger, season_summary
from gaffer.web.schemas import Review

router = APIRouter(prefix="/api", tags=["review"])

EMPTY = Review()


@router.get("/review", response_model=Review)
def review() -> Review:
    try:
        ledger = load_ledger()
        if not ledger:
            return EMPTY
        return Review(gws=ledger, summary=season_summary(ledger))
    except Exception as exc:  # noqa: BLE001 — a corrupt bank is an empty one
        print(f"review ledger unavailable: {exc}")
        return EMPTY
