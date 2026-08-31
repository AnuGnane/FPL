"""GET /api/misses — the biggest forecast errors of the last scored week.

Never an error and never a 404. A clone that has never ingested a result is
not a broken install, so the answer is a 200 with a null gameweek, which the
Quality tab renders as no card at all.

All the work is in :mod:`gaffer.misses`; this chooses the gameweek and shapes
the payload.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from gaffer.misses import biggest_misses, scoreable_gw
from gaffer.web.schemas import Misses, MissRow

router = APIRouter(prefix="/api", tags=["misses"])


@router.get("/misses", response_model=Misses)
def misses(gw: int | None = Query(
        default=None,
        description="Gameweek to score; the newest scoreable one when "
                    "omitted.")) -> Misses:
    try:
        wanted = scoreable_gw() if gw is None else int(gw)
        rows = [] if wanted is None else biggest_misses(wanted)
    except Exception as exc:  # noqa: BLE001 — one card, never the page
        print(f"misses: unavailable ({exc})")
        return Misses()
    if not rows:
        return Misses()
    return Misses(gw=wanted, rows=[MissRow(**row) for row in rows])
