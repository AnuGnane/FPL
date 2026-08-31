"""GET /api/confidence — what the banked record entitles the tool to claim.

Never an error, for the review router's reason: an ungraded season is not a
degraded state, it is the state every season begins in. So every failure —
no ledger, a corrupt one, a reports directory that does not exist — is a 200
carrying the "too early" sentence with a count of zero in it, which is both
true and the thing the card should say.

No arithmetic here at all: :mod:`gaffer.confidence` does the counting and this
reads a file.
"""

from __future__ import annotations

from fastapi import APIRouter

from gaffer.confidence import captain_confidence
from gaffer.web.schemas import Confidence, ConfidenceTier

router = APIRouter(prefix="/api", tags=["confidence"])


@router.get("/confidence", response_model=Confidence)
def confidence() -> Confidence:
    from gaffer.review import load_ledger

    try:
        ledger = load_ledger()
    except Exception as exc:  # noqa: BLE001 — a bad ledger is an empty one
        print(f"confidence: ledger unavailable ({exc})")
        ledger = []
    return Confidence(captain=ConfidenceTier(**captain_confidence(ledger)))
