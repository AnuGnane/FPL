"""User overrides: the manager's own team news, and the last word on minutes.

Everything else in the tool is a model output with a model's humility. This
file is the one place a human number is applied *as fact* — the user watched
the press conference, or the training-ground video, or simply knows something
the feeds do not — so it is applied after every automated pass and it is
applied whole.

It is serve-time only. Nothing here is ever a trained feature and nothing here
is read by a backtest; the pins are banked into the availability artifacts for
the same reason the news layer's readings are, so that a future season can ask
what the user knew and when. That is the whole train/serve rule, restated for
a source whose author happens to be the user.

Scope is deliberately two numbers. ``p_play`` and ``e_min`` are the minutes
model's outputs, which is where almost all of FPL's forecast error lives; an
attacking-EP override would need a seam inside protected code and would let a
bad afternoon rewrite the model's whole opinion of a player.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from gaffer import artifacts
from gaffer.errors import GafferError

OVERRIDE_COLS = ["override", "override_p_play", "override_e_min",
                 "override_note"]
"""The four columns :func:`attach_overrides` adds to an availability frame.

``override`` is the marker the why-panel and the daily snapshot read: a
boolean saying "the user pinned something about this player", which stays
true and legible long after the pin itself has been deleted from the store.
"""

MAX_OVERRIDES = 50
"""More pins than this is not a manager's judgement, it is a second model.

The cap exists so a runaway client cannot turn the availability pass into a
serialization problem, and so the why-panel stays a list somebody reads.
"""

NOTE_MAX = 200
"""Characters. Refused rather than truncated: a silently halved note is a
sentence the user did not write."""


def overrides_path() -> Path:
    """``reports/overrides.json``, resolved at call time.

    ``artifacts.REPORTS`` is a relative path, so a test that changes directory
    changes this with it — the same trade every other report store makes.
    """
    return artifacts.REPORTS / "overrides.json"


def load_overrides() -> dict[int, dict]:
    """``{code: {p_play, e_min, note, set_at, model_p_play, model_e_min}}``.

    Never raises. An absent file, a hand-edited one, a half-written one and a
    file whose top-level shape has drifted all come back as ``{}`` — an advise
    run that died of its own override store would be a far worse failure than
    one that ignored it, and the print is what makes the difference visible.

    JSON object keys are strings by definition; this is where they become
    integers again, so a caller looking a code up with an int cannot miss.
    """
    path = overrides_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
        rows = raw.get("overrides") if isinstance(raw, dict) else None
        if not isinstance(rows, dict):
            return {}
        out: dict[int, dict] = {}
        for code, row in rows.items():
            if not isinstance(row, dict):
                continue
            out[int(code)] = {
                "p_play": _clipped(row.get("p_play"), 0.0, 1.0, "p_play",
                                   code),
                "e_min": _clipped(row.get("e_min"), 0.0, 90.0, "e_min", code),
                "note": str(row.get("note") or ""),
                "set_at": str(row.get("set_at") or ""),
                "model_p_play": _opt_float(row.get("model_p_play")),
                "model_e_min": _opt_float(row.get("model_e_min")),
            }
        return out
    except Exception as exc:  # noqa: BLE001 — a bad store is an empty one
        print(f"overrides store unreadable, ignoring it: {exc}")
        return {}


def save_overrides(rows: dict[int, dict]) -> Path:
    """Write the whole store through a temp file and ``os.replace``.

    ``pen_tracker.save_tracker``'s idiom exactly: a reader sees the whole
    previous store or the whole new one, never the half-written middle. The
    availability pass is a reader, and it runs on a schedule.
    """
    payload = {"overrides": {str(code): dict(row)
                             for code, row in sorted(rows.items())}}
    artifacts.REPORTS.mkdir(exist_ok=True)
    path = overrides_path()
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=1, allow_nan=False))
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def _opt_float(value) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(out) else out


def _clipped(value, lo: float, hi: float, name: str, code) -> float | None:
    """A stored value, forced into the range the availability pass applies.

    :func:`set_override` refuses anything outside it, but the store is a file:
    it can be hand-edited, restored from an older schema, or written by a
    future version. ``_override_first_gw`` clips both fields on the way in, so
    an unclipped read would show the panel a number the model never applied —
    "the model had 0.82, you pinned 1.70" beside a squad built on 1.00. The
    print is what stops the correction being silent.
    """
    out = _opt_float(value)
    if out is None:
        return None
    if out < lo or out > hi:
        clipped = min(max(out, lo), hi)
        print(f"overrides: player {code}'s {name} is {out:g}, outside "
              f"{lo:g}-{hi:g} — reading it as {clipped:g}")
        return clipped
    return out


def _checked(value, lo: float, hi: float, name: str) -> float | None:
    """A pin value, or a refusal naming the range it missed."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise GafferError(f"{name} must be a number") from exc
    if math.isnan(out) or not (lo <= out <= hi):
        raise GafferError(f"{name} must be between {lo} and {hi} — got {out}")
    return out


def set_override(code: int, *, p_play=None, e_min=None, note: str = "",
                 known_codes=None, model_p_play=None,
                 model_e_min=None) -> dict:
    """Pin ``code``'s minutes, refusing anything the model cannot act on.

    ``known_codes`` is the universe the pin has to belong to — the bootstrap
    snapshot's codes, supplied by the caller so this module needs no data
    layer. Omitting it skips the check, which is for tests and for callers
    that have already validated.

    ``model_p_play`` / ``model_e_min`` are what the served pipeline had for
    this player at the moment the pin was made (spec A3). On a **re-pin the
    existing pair is preserved**: the second reading would be the first pin
    looking at itself, and "the model had 1.00" is not a sentence worth
    showing anybody.
    """
    code = int(code)
    if known_codes is not None and code not in {int(c) for c in known_codes}:
        raise GafferError(
            f"player {code} is not in the current player list — pin a code "
            f"the tool knows about")
    play = _checked(p_play, 0.0, 1.0, "p_play")
    mins = _checked(e_min, 0.0, 90.0, "e_min")
    if play is None and mins is None:
        raise GafferError("an override must pin p_play, e_min or both")
    if len(str(note or "")) > NOTE_MAX:
        raise GafferError(f"note is longer than {NOTE_MAX} characters")

    rows = load_overrides()
    if code not in rows and len(rows) >= MAX_OVERRIDES:
        raise GafferError(
            f"{MAX_OVERRIDES} overrides is the cap — delete one first")
    previous = rows.get(code, {})
    row = {
        "p_play": play, "e_min": mins, "note": str(note or ""),
        "set_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_p_play": (previous.get("model_p_play")
                         if previous.get("model_p_play") is not None
                         else _opt_float(model_p_play)),
        "model_e_min": (previous.get("model_e_min")
                        if previous.get("model_e_min") is not None
                        else _opt_float(model_e_min)),
    }
    rows[code] = row
    save_overrides(rows)
    return row


def delete_override(code: int) -> bool:
    """Remove one pin. ``False`` when there was nothing to remove."""
    rows = load_overrides()
    if int(code) not in rows:
        return False
    rows.pop(int(code))
    save_overrides(rows)
    return True


def attach_overrides(frame: pd.DataFrame,
                     overrides: dict[int, dict] | None = None) -> pd.DataFrame:
    """Add :data:`OVERRIDE_COLS` to an availability frame.

    Idempotent by design: the availability pass and the artifact writer both
    call it, and a frame that already carries the marker is returned untouched
    rather than re-read from disk. A frame with no ``code`` column is returned
    as it came — the bare bootstrap slice always has one, but a caller holding
    something else should get a no-op rather than a KeyError.

    The columns are added whether or not anybody has pinned anything, so the
    parquet schema does not depend on the week: an all-null column with a
    settled dtype is what the news layer's own optional fields already do.

    Never mutates the caller's frame.
    """
    if frame is None or "code" not in getattr(frame, "columns", []):
        return frame
    if "override" in frame.columns:
        return frame
    table = load_overrides() if overrides is None else dict(overrides)
    marks, plays, mins, notes = [], [], [], []
    for raw in frame["code"]:
        try:
            row = table.get(int(raw))
        except (TypeError, ValueError):
            row = None
        marks.append(row is not None)
        plays.append(None if row is None else row.get("p_play"))
        mins.append(None if row is None else row.get("e_min"))
        notes.append(None if row is None else (row.get("note") or None))
    out = frame.copy()
    out["override"] = pd.array(marks, dtype="boolean")
    out["override_p_play"] = pd.to_numeric(pd.Series(plays,
                                                     index=out.index),
                                           errors="coerce")
    out["override_e_min"] = pd.to_numeric(pd.Series(mins, index=out.index),
                                          errors="coerce")
    out["override_note"] = pd.Series(notes, index=out.index,
                                     dtype="object").astype("string")
    return out
