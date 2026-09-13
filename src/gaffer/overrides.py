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

Since v18d §2 this file is the *write* half only. Reading the store, and
attaching its four columns to an availability frame, is banked-file work and
lives in :mod:`gaffer.artifacts` beside every other banked file; the names are
imported back here so a caller that has always said ``overrides.<name>`` is
unaffected.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

from gaffer import artifacts
# v18d §2: the read half is in ``gaffer.artifacts`` — the store is a banked
# file and that is the banked-file reader. Re-exported here so a caller that
# has always said ``overrides.load_overrides`` still finds it.
from gaffer.artifacts import (OVERRIDE_COLS, attach_overrides,  # noqa: F401
                              clipped, load_overrides, opt_float,
                              overrides_path)
from gaffer.errors import GafferError
from gaffer.io import atomic_write

MAX_OVERRIDES = 50
"""More pins than this is not a manager's judgement, it is a second model.

The cap exists so a runaway client cannot turn the availability pass into a
serialization problem, and so the why-panel stays a list somebody reads.
"""

NOTE_MAX = 200
"""Characters. Refused rather than truncated: a silently halved note is a
sentence the user did not write."""


def save_overrides(rows: dict[int, dict]) -> Path:
    """Write the whole store atomically.

    ``pen_tracker.save_tracker``'s idiom exactly: a reader sees the whole
    previous store or the whole new one, never the half-written middle. The
    availability pass is a reader, and it runs on a schedule — and two saves
    can race in from concurrent HTTP handlers.
    """
    payload = {"overrides": {str(code): dict(row)
                             for code, row in sorted(rows.items())}}
    artifacts.REPORTS.mkdir(exist_ok=True)
    path = overrides_path()
    atomic_write(path, json.dumps(payload, indent=1, allow_nan=False))
    return path


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
                         else opt_float(model_p_play)),
        "model_e_min": (previous.get("model_e_min")
                        if previous.get("model_e_min") is not None
                        else opt_float(model_e_min)),
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
