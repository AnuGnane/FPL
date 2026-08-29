"""GET /api/journal — the decision journal (spec §6.4).

Never an error. No advice history, no finished gameweek, no configured entry
and an unreachable FPL API all land in the same place: an empty journal the UI
shows its empty state for. The join itself lives in ``gaffer.journal``; this
module only decides where the client and the entry id come from.
"""

from __future__ import annotations

from fastapi import APIRouter

from gaffer.journal import load_journal
from gaffer.web.schemas import Journal

router = APIRouter(prefix="/api", tags=["journal"])

EMPTY = Journal()


def fpl_client():
    """Seam for tests; the real one is the read-only client the CLI uses."""
    from gaffer.api.client import FPLClient

    return FPLClient()


def entry_id() -> int | None:
    """Seam for tests; ``None`` when nothing is configured."""
    from gaffer.config import load_config

    try:
        return load_config().entry_id
    except Exception:                    # noqa: BLE001 — no config at all
        return None


@router.get("/journal", response_model=Journal)
def journal() -> Journal:
    who = entry_id()
    if not who:
        return EMPTY
    try:
        return Journal(**load_journal(fpl_client(), int(who)))
    except Exception as exc:             # noqa: BLE001 — network, JSON, schema
        print(f"journal unavailable: {exc}")
        return EMPTY
