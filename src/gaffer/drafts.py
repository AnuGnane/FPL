"""``reports/drafts.json``: named what-if constraint sets.

A draft is what you *asked for*, not what you got. Freezing the squad would
make a draft stale the moment a price changed or a hamstring went, and would
lose the only thing worth keeping — the argument. Re-solving the constraints
against today's board keeps "the Salah route" meaningful all week, and the
comparison stamps each row with when it was solved so nobody reads a Tuesday
answer on a Friday.

The store is deliberately small and deliberately dumb: no solving here, no
validation of players against a pool (the router does that, because it is the
half that knows the pool), and the same atomic single-JSON write every other
report store uses.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from gaffer import artifacts
from gaffer.errors import GafferError
from gaffer.io import atomic_write

MAX_DRAFTS = 12
"""Spec D4's cap. Twelve named plans is a planning session; a hundred is a
filing cabinet nobody opens."""

NAME_MAX = 60

CONSTRAINT_DEFAULTS: dict = {"lock": [], "ban": [], "force_in": [],
                             "max_hits": 0, "chip": "none", "horizon": None}
"""The six keys a draft may carry — ``WhatIfRequest``'s fields exactly.

Anything else in the payload is dropped rather than stored: the store is fed
from an HTTP body, and a key the solver does not understand is a key that will
be silently ignored later at a worse moment.
"""


def drafts_path() -> Path:
    return artifacts.REPORTS / "drafts.json"


def normalize(constraints: dict | None) -> dict:
    """The six keys, defaulted and typed. Never raises."""
    raw = dict(constraints or {})
    return {
        "lock": [int(c) for c in raw.get("lock") or []],
        "ban": [int(c) for c in raw.get("ban") or []],
        "force_in": [int(c) for c in raw.get("force_in") or []],
        "max_hits": int(raw.get("max_hits") or 0),
        "chip": str(raw.get("chip") or "none"),
        "horizon": (None if raw.get("horizon") in (None, "")
                    else int(raw["horizon"])),
    }


def load_drafts() -> list[dict]:
    """Every saved draft in creation order, or ``[]``.

    Never raises, for the same reason the overrides store does not: a
    hand-edited file must cost you your drafts, not your afternoon.
    """
    path = drafts_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text())
        rows = raw.get("drafts") if isinstance(raw, dict) else None
        if not isinstance(rows, list):
            return []
        return [{"name": str(r["name"]),
                 "created_at": str(r.get("created_at") or ""),
                 "constraints": normalize(r.get("constraints"))}
                for r in rows if isinstance(r, dict) and r.get("name")]
    except Exception as exc:  # noqa: BLE001
        print(f"drafts store unreadable, ignoring it: {exc}")
        return []


def save_drafts(rows: list[dict]) -> Path:
    """Atomic whole-file write — ``pen_tracker.save_tracker``'s idiom.

    Two saves can race in from concurrent HTTP handlers, which is why this
    goes through the shared helper rather than straight to the destination.
    """
    artifacts.REPORTS.mkdir(exist_ok=True)
    path = drafts_path()
    atomic_write(path, json.dumps({"drafts": rows}, indent=1,
                                  allow_nan=False))
    return path


def add_draft(name: str, constraints: dict | None) -> dict:
    """Save one named constraint set, refusing a name that cannot be used."""
    clean = str(name or "").strip()
    if not clean:
        raise GafferError("a draft needs a name")
    if len(clean) > NAME_MAX:
        raise GafferError(f"a draft name is at most {NAME_MAX} characters")
    rows = load_drafts()
    if any(r["name"] == clean for r in rows):
        raise GafferError(f"a draft called {clean!r} already exists")
    if len(rows) >= MAX_DRAFTS:
        raise GafferError(
            f"{MAX_DRAFTS} drafts is the cap — delete one first")
    row = {"name": clean,
           "created_at": datetime.now(timezone.utc).isoformat(
               timespec="seconds"),
           "constraints": normalize(constraints)}
    rows.append(row)
    save_drafts(rows)
    return row


def delete_draft(name: str) -> bool:
    rows = load_drafts()
    kept = [r for r in rows if r["name"] != str(name)]
    if len(kept) == len(rows):
        return False
    save_drafts(kept)
    return True
