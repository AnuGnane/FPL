"""Tonight's price fall, per owned player, for the objective's timing term.

``price_log.py`` has been banking every player's predictor reading nightly
since v10b and its own docstring says why: *"the log is being accrued now so
that a future cycle has a season of it to justify a price-timing term with;
today it is banked and read by nobody, which is the correct order to do that
in."* This is that cycle, and this is the reader.

**What the number is.** ``price_change_percent`` is FPL's own progress toward
the nightly 00:00 change; it reaches ±100 at the change itself and the live
log holds values past it (min -129.9). Read as a probability of falling
tonight it is ``min(1, |pct| / 100)`` on a ``drop``, and nothing at all
otherwise — a rise is never charged, because spec §8 and the ROADMAP both name
price chasing as rejected, and a ``flat`` or null reading is the predictor
declining to say.

``calibrating`` rows are dropped whole. The field exists to say the log is not
yet trustworthy, and ``routers/prices.py`` already suppresses its warnings on
it; a charge levied off an untrustworthy reading is worse than no charge,
because the solver cannot see the caveat.

Nothing here raises. It is read on the solve path and a missing log, a corrupt
log or a machine that has never run ``gaffer prices`` must cost the term and
nothing else.
"""

from __future__ import annotations

import pandas as pd

from gaffer.config import price_timing as price_timing_enabled
from gaffer.price_log import load_price_log


def price_falls(log: pd.DataFrame,
                owned: list[int] | None) -> dict[int, float]:
    """``{code: P(falls tonight)}`` over the newest banked day.

    The newest day only: a reading from Tuesday is not evidence about
    Thursday night, and the log keeps every day precisely so that "the newest"
    is a choice somebody made rather than the only row there is.
    """
    if log is None or log.empty or not owned:
        return {}
    frame = log.copy()
    day = max(str(d) for d in frame["snap_date"])
    frame = frame[frame["snap_date"].astype(str) == day]
    frame = frame[frame["code"].isin([int(c) for c in owned])]
    if "calibrating" in frame.columns:
        frame = frame[~frame["calibrating"].fillna(False).astype(bool)]
    if frame.empty:
        return {}
    pct = pd.to_numeric(frame["price_change_percent"], errors="coerce")
    falling = frame[pct.notna() & (pct < 0)]
    out = {}
    for code, value in zip(falling["code"],
                           pd.to_numeric(falling["price_change_percent"],
                                         errors="coerce")):
        out[int(code)] = round(min(1.0, abs(float(value)) / 100.0), 3)
    return out


def owned_price_falls(owned: list[int] | None) -> dict[int, float]:
    """:func:`price_falls` over the banked log, behind the switch.

    Empty dict on the switch being off, on no log, on a corrupt log and on a
    log with nothing near a threshold — and an empty dict makes the objective
    term arithmetically absent, which is what keeps a machine with no price
    log solving exactly what it always did.
    """
    try:
        if not price_timing_enabled():
            return {}
        return price_falls(load_price_log(), owned)
    except Exception as exc:  # noqa: BLE001 — never blocks a solve
        print(f"price timing: no charge applied ({exc})")
        return {}
