"""The deviation note (v16 §5): why the manager did something other than
what the advice said, one note per gameweek.

A reason code from a fixed list plus up to 280 characters of text. Written
through :func:`gaffer.io.atomic_write` under a module lock — the browser
saves one field at a time and two saves racing on one file is a click, not
a hypothetical. Read by the Review tab (beside the grade), the by-reason
tally and the brief. Nothing here decides anything.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

import pandas as pd

from gaffer import artifacts
from gaffer.io import atomic_write

REASONS = ("injury", "fixtures", "eye_test", "price", "chip", "rival",
           "gut", "other")
"""The whole vocabulary. Eight, and the tally is per code — more codes is a
later cycle's question (spec §11)."""

TEXT_MAX = 280

DECISIONS = "decisions.json"

NO_NOTE = "none"
"""The tally's row for graded gameweeks with no note."""

_LOCK = threading.Lock()


def decisions_path():
    return artifacts.REPORTS / DECISIONS


def load_decisions() -> dict[int, dict]:
    """``{gw: {gw, reason, text, at}}``; ``{}`` on any failure."""
    path = decisions_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
        return {int(gw): {"gw": int(gw), "reason": note.get("reason"),
                          "text": str(note.get("text") or ""),
                          "at": note.get("at")}
                for gw, note in (raw or {}).items()}
    except Exception as exc:  # noqa: BLE001 — a corrupt store is an empty one
        print(f"decisions: store unreadable ({exc})")
        return {}


def note_for(gw: int) -> dict:
    """The note, or the empty shape — never an absence the client has to
    special-case."""
    return load_decisions().get(int(gw)) or {"gw": int(gw), "reason": None,
                                             "text": "", "at": None}


def save_note(gw: int, reason: str, text: str) -> dict:
    """Write one gameweek's note. ``ValueError`` on a bad reason or a long
    text — the router turns those into its refusal shape."""
    if reason not in REASONS:
        raise ValueError(f"reason must be one of {', '.join(REASONS)}")
    text = str(text or "")
    if len(text) > TEXT_MAX:
        raise ValueError(f"text is at most {TEXT_MAX} characters")
    note = {"gw": int(gw), "reason": reason, "text": text,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with _LOCK:
        notes = load_decisions()
        notes[int(gw)] = note
        artifacts.REPORTS.mkdir(parents=True, exist_ok=True)
        atomic_write(decisions_path(), json.dumps(
            {str(g): n for g, n in sorted(notes.items())}, indent=1))
    return note


def _deadline_for(gw: int) -> str | None:
    """The advised deadline: the advice payload's, else the events
    snapshot's, else ``None``."""
    try:
        deadline = artifacts.load_advice(gw).get("deadline")
        if deadline:
            return str(deadline)
    except Exception:  # noqa: BLE001
        pass
    try:
        events = artifacts.load_snapshot("live/events.parquet")
        row = events[events["gw"] == int(gw)]
        if not row.empty:
            return str(row["deadline_time"].iloc[0])
    except Exception:  # noqa: BLE001
        pass
    return None


def grade_for(gw: int, ledger: list[dict] | None = None) -> dict | None:
    """The transfers lane's grade off the ledger, or ``None``."""
    if ledger is None:
        from gaffer.review import load_ledger
        ledger = load_ledger()
    for row in ledger:
        if int(row.get("gw", -1)) != int(gw):
            continue
        for lane in row.get("lanes") or []:
            if lane.get("lane") == "transfers":
                return {"lane": "transfers", "label": lane.get("label"),
                        "delta_pts": lane.get("delta_pts")}
    return None


def note_state(gw: int, *, now: pd.Timestamp | None = None
               ) -> tuple[str, str | None, dict | None]:
    """``(state, deadline, grade)`` — ``before_deadline`` | ``open`` |
    ``graded`` (plan R11). No deadline on record is ``open``."""
    grade = grade_for(gw)
    deadline = _deadline_for(gw)
    if grade is not None:
        return "graded", deadline, grade
    if deadline is not None:
        stamp = pd.Timestamp(deadline)
        stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
        ts = pd.Timestamp.now(tz="UTC") if now is None else now
        if stamp > ts:
            return "before_deadline", deadline, None
    return "open", deadline, None


def by_reason(ledger: list[dict], notes: dict[int, dict]) -> list[dict]:
    """Per reason code: count and mean transfers-lane ``delta_pts`` over the
    graded gameweeks, ``REASONS`` order then ``none``. Rows with no graded
    transfers lane are left out; a graded row with no note counts under
    ``none``. Codes with no rows are omitted."""
    cells: dict[str, list[float]] = {}
    for row in ledger:
        grade = grade_for(int(row["gw"]), [row])
        if grade is None or grade["delta_pts"] is None:
            continue
        reason = (notes.get(int(row["gw"])) or {}).get("reason") or NO_NOTE
        cells.setdefault(reason, []).append(float(grade["delta_pts"]))
    out = []
    for reason in (*REASONS, NO_NOTE):
        deltas = cells.get(reason)
        if deltas:
            out.append({"reason": reason, "count": len(deltas),
                        "mean_delta_pts": round(sum(deltas) / len(deltas), 1)})
    return out
