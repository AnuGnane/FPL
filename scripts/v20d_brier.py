"""v20d's second reading: is the price term's probability worth its charge?

v20 spec §2 v20d "The term's worth, as a second reading". The objective's
price-timing term charges a sale ``min(1, |pct| / 100)`` of a fall on a
``drop`` reading (``price_timing.price_falls``). Over every ``(snap_date,
code)`` in the banked log with a drop reading and a row for the same code the
next UTC day, this scores that number against "fell overnight" (``now_cost``
down the next day) by Brier, beside the base rate's Brier over the same rows
(the constant forecast that is the rows' own fall rate).

The rule (v20 spec §2 v20d): if the term's Brier is worse than the base
rate's over at least thirty drop-days, a ruling to turn ``[optimizer]
price_timing``'s default off goes to the user with the numbers; otherwise the
line is recorded and the default stands. "Drop-days" could mean drop rows or
distinct days with a drop row, so the line carries both (``drop_rows``,
every non-calibrating drop reading before the next-day match, beside ``n``,
the rows scored, and ``drop_days``, the distinct days among them) and the
verdict reads the stricter one, distinct days (holiday F-12).

``calibrating`` rows are left out, as ``price_timing.price_falls`` leaves them
out: the term never charges them, so they are not evidence about its worth.

Read-only. It writes nothing and changes no default; a missing, corrupt or
short log prints the line with ``n=0`` and a reason, never a traceback,
because the night shift transcribes the line into the spec's §6 whatever it
says.

    uv run python scripts/v20d_brier.py
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd

from gaffer.data import store
from gaffer.price_log import PRICE_LOG_PATH, load_price_log

MIN_DROP_DAYS = 30
"""The spec's "≥ 30 drop-days", read as distinct UTC days (module docstring)."""


def _empty(reason: str) -> dict:
    return {"n": 0, "drop_rows": 0, "drop_days": 0, "falls": 0,
            "brier_term": None,
            "brier_base": None, "base_rate": None, "verdict": "no reading",
            "reason": reason}


def _next_day(day: str) -> str:
    return (date.fromisoformat(day) + timedelta(days=1)).isoformat()


def brier_reading(log: pd.DataFrame | None) -> dict:
    """The ``V20D_BRIER`` payload over a banked price log."""
    if log is None or log.empty:
        return _empty("price log is empty")
    frame = log.copy()
    frame["snap_date"] = frame["snap_date"].astype(str)
    frame["code"] = pd.to_numeric(frame["code"], errors="coerce")
    frame["now_cost"] = pd.to_numeric(frame["now_cost"], errors="coerce")
    frame["pct"] = pd.to_numeric(frame["price_change_percent"],
                                 errors="coerce")
    frame = frame.dropna(subset=["code", "now_cost"])
    if frame["snap_date"].nunique() < 2:
        return _empty("fewer than two banked days")

    # Calibrating is about the reading, so it leaves the drop side only; a
    # calibrating next-day row's now_cost is still the true outcome.
    drops = frame[frame["pct"].notna() & (frame["pct"] < 0)]
    if "calibrating" in drops.columns:
        drops = drops[~drops["calibrating"].fillna(False).astype(bool)]
    drops = drops.copy()
    drop_rows = int(len(drops))
    drops["next_day"] = drops["snap_date"].map(_next_day)
    later = frame[["snap_date", "code", "now_cost"]].rename(
        columns={"snap_date": "next_day", "now_cost": "next_cost"})
    rows = drops.merge(later, on=["next_day", "code"], how="inner")
    if rows.empty:
        return {**_empty("no drop reading with a row the next day"),
                "drop_rows": drop_rows}

    p = (rows["pct"].abs() / 100.0).clip(upper=1.0)
    fell = (rows["next_cost"] < rows["now_cost"]).astype(float)
    base_rate = float(fell.mean())
    brier_term = float(((p - fell) ** 2).mean())
    brier_base = float(((base_rate - fell) ** 2).mean())
    drop_days = int(rows["snap_date"].nunique())
    if drop_days < MIN_DROP_DAYS:
        verdict = f"short: {drop_days} drop-days of {MIN_DROP_DAYS}"
    elif brier_term > brier_base:
        verdict = "term worse than base rate: ruling to the user"
    else:
        verdict = "term no worse than base rate: default stands"
    return {"n": int(len(rows)), "drop_rows": drop_rows,
            "drop_days": drop_days, "falls": int(fell.sum()),
            "brier_term": round(brier_term, 4),
            "brier_base": round(brier_base, 4),
            "base_rate": round(base_rate, 4), "verdict": verdict,
            "reason": None}


def main() -> int:
    if not store.exists(PRICE_LOG_PATH):
        payload = _empty(f"no price log at {store.DATA_DIR / PRICE_LOG_PATH}")
    else:
        try:
            payload = brier_reading(load_price_log())
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # A corrupt parquet raises ArrowInvalid (a ValueError); a log
            # missing a column raises KeyError; a malformed snap_date raises
            # ValueError in date.fromisoformat.
            payload = _empty(f"price log unreadable: {type(exc).__name__}")
    print(f"V20D_BRIER {json.dumps(payload, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
