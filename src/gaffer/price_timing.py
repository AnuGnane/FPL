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

The sign of ``price_change_percent`` is the whole test, and the log's
``direction`` column is redundant with it: ``direction == "drop"`` is exactly
``pct < 0`` on every row the banker writes. This module reads the number
rather than the label, so a log written before the label existed still scores.

**A stale log is no log.** If the newest banked day is not *today*, the whole
frame is dropped and the table is empty. Last night's reading is about a
change that has already happened, and charging a sale for a fall the player
has already taken is charging it twice.

Nothing here raises. It is read on the solve path and a missing log, a corrupt
log or a machine that has never run ``gaffer prices`` must cost the term and
nothing else.
"""

from __future__ import annotations

from functools import lru_cache

import pandas as pd

from gaffer.config import price_timing as price_timing_enabled
from gaffer.price_log import load_price_log
from gaffer.snapshot import snap_date


def price_falls(log: pd.DataFrame,
                owned: list[int] | None) -> dict[int, float]:
    """``{code: P(falls tonight)}`` over the newest banked day.

    The newest day only: a reading from Tuesday is not evidence about
    Thursday night, and the log keeps every day precisely so that "the newest"
    is a choice somebody made rather than the only row there is.

    And the newest day has to be *today* (``snapshot.snap_date()``, UTC). A
    log whose freshest row is yesterday's is describing a price change that
    has already resolved; charging it again is charging a fall twice. So a
    stale log yields ``{}``, exactly as a missing one does.
    """
    if log is None or log.empty or not owned:
        return {}
    frame = log.copy()
    day = max(str(d) for d in frame["snap_date"])
    if day != snap_date():
        return {}
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
    stale one — and an empty dict makes the objective term arithmetically
    absent, which is what keeps a machine with no price log solving exactly
    what it always did.

    Cached, and for the reason :func:`gaffer.config.optimizer_top_n` is:
    ``solve_plan`` builds its ``kw`` once per solve and both passes read the
    same table from it, but a long-lived process solves many times and a
    parquet read on each is the cost this reader exists to avoid. The key is
    ``(snap_date(), tuple(sorted(owned)))`` — the squad, so a different squad
    does not share a read, and *the day*, because the freshness rule
    (":func:`price_falls`'s newest banked day has to be today") is what a
    cache keyed on the squad alone would quietly outlive: a table computed at
    23:50 would still be served at 00:10, charging a fall that had by then
    already resolved. Anything that rewrites the price log (or
    ``config.toml``) under a running process calls
    ``owned_price_falls.cache_clear()``; the health poll
    already does, beside ``optimizer_top_n``'s. The returned dict is a fresh
    copy per call so a caller that mutates it cannot poison the cache.

    Note the switch itself is *not* cached: :func:`gaffer.config.price_timing`
    re-reads ``config.toml`` on every call, so a flipped flag takes effect on
    the next solve. It is this table — the parquet read — that the cache is
    for.
    """
    key = tuple(sorted(int(c) for c in owned)) if owned else ()
    return dict(_owned_price_falls(_today(), key))


def _today() -> str:
    """``snap_date()`` behind a guard, because it is read on the solve path.

    A clock that will not answer must cost the term and nothing else, like
    every other failure in this module. The empty string it returns is only a
    cache key, and is never compared against a banked day: it is
    :func:`price_falls` that decides freshness, and it calls ``snap_date()``
    again for itself, so the same broken clock raises there and
    :func:`_owned_price_falls`'s own ``except`` turns it into an empty
    table."""
    try:
        return str(snap_date())
    except Exception:  # noqa: BLE001 — never blocks a solve
        return ""


@lru_cache(maxsize=8)
def _owned_price_falls(day: str,
                       owned: tuple[int, ...]) -> dict[int, float]:
    """:func:`owned_price_falls`'s cache. Never call this one directly — it
    hands back the cached dict itself, and a mutation of it would be
    permanent.

    ``day`` is not read in the body: it is in the signature so that the
    freshness rule inside :func:`price_falls` cannot be outlived by the cache
    that wraps it. Midnight is a new key."""
    try:
        if not price_timing_enabled():
            return {}
        return price_falls(load_price_log(), list(owned))
    except Exception as exc:  # noqa: BLE001 — never blocks a solve
        print(f"price timing: no charge applied ({exc})")
        return {}


# The cache lives on the private reader, but callers should not have to know
# that — `optimizer_top_n`'s precedent, verbatim.
owned_price_falls.cache_clear = _owned_price_falls.cache_clear
owned_price_falls.cache_info = _owned_price_falls.cache_info
