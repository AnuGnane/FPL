"""The daily price bank: FPL's own predictor, kept instead of printed.

``gaffer prices`` has been stateless since it was written — it reads
``price_change_percent`` out of the bootstrap, prints whoever is near a
threshold, and forgets. That is enough to answer "who moves tonight" and
nothing else, and the questions worth asking are all the other ones: how long
does a player sit at ninety before he rises, does the predictor lead or lag
the transfer counts, and is a rise on a Tuesday worth planning around. None of
them are answerable from a file that only kept the alerts, so this log keeps
**every** player's reading, every day.

It is the availability log's twin and shares its every mechanic on purpose:
one row per player per UTC day, ``snap_date`` as the idempotency key,
append-by-rewrite because parquet has no append, and an ``os.replace`` at the
end so a job killed mid-write costs the day rather than the season. Even the
clock is shared — :func:`gaffer.snapshot.snap_date` is imported rather than
restated, because two definitions of "today" in one project is a bug waiting
for the week somebody joins the two logs.

Nothing here is a trained feature. The log is being accrued now so that a
future cycle has a season of it to justify a price-timing term with; today it
is banked and read by nobody, which is the correct order to do that in.

Nothing here may raise. The caller is a launchd job at 23:15 with nowhere to
report a traceback, and it has already printed the output the user actually
asked for by the time this runs.
"""

from __future__ import annotations

import os

import pandas as pd

from gaffer.data import store
from gaffer.snapshot import snap_date

PRICE_LOG_PATH = "live/price_log.parquet"

PRICE_LOG_COLS = ["snap_date", "code", "now_cost", "price_change_percent",
                  "direction", "calibrating"]
"""Six columns, and deliberately no ``name``.

A code is a stable join key and a web name is not: banking a display name
every day for a season stores nothing but the day FPL decided to spell it
differently. Names come from ``data/live/players.parquet`` at read time.
"""

_REQUIRED = {"code", "now_cost", "price_change_percent"}


def _direction(pct: pd.Series) -> pd.Series:
    """``rise`` / ``drop`` / ``flat``, and null where nothing was published.

    Three-valued where :func:`gaffer.prices.price_alerts` is two-valued,
    because that function only ever sees rows past a threshold and this one
    sees the whole league. The null matters most: a locked player, or one FPL
    has not started predicting for, is not a player the predictor said would
    hold his price.
    """
    out = pd.Series(pd.NA, index=pct.index, dtype="object")
    out[pct > 0] = "rise"
    out[pct < 0] = "drop"
    out[pct == 0] = "flat"
    return out.astype("string")


def price_rows(players: pd.DataFrame, day: str | None = None) -> pd.DataFrame:
    """The bootstrap's price fields -> dated log rows, one per player.

    Dtypes are forced rather than inferred, the trade
    :func:`gaffer.snapshot.snapshot_rows` makes: parquet wants one dtype per
    column, and a pre-season day on which nobody has a published prediction
    would otherwise write an all-null object column into a file whose other
    days are floats.
    """
    if players is None or not isinstance(players, pd.DataFrame):
        raise ValueError("no player frame to bank")
    if not _REQUIRED.issubset(players.columns):
        missing = sorted(_REQUIRED - set(players.columns))
        raise ValueError(f"player frame is missing {', '.join(missing)}")
    if players.empty:
        raise ValueError("player frame is empty")

    pct = pd.to_numeric(players["price_change_percent"], errors="coerce")
    calibrating = players.get("price_change_calibrating")
    if calibrating is None:
        # The bootstrap gained this field mid-season once already. An older
        # cache banks as "not calibrating", which is what it means.
        calibrating = pd.Series(False, index=players.index)
    out = pd.DataFrame({
        "snap_date": str(day or snap_date()),
        "code": pd.to_numeric(players["code"],
                              errors="coerce").astype("int64"),
        "now_cost": pd.to_numeric(players["now_cost"],
                                  errors="coerce").astype("Int64"),
        "price_change_percent": pct.astype("float64"),
        "direction": _direction(pct),
        "calibrating": pd.Series(calibrating, index=players.index).fillna(
            False).astype(bool),
    })
    return out[PRICE_LOG_COLS].reset_index(drop=True)


def append_prices(rows: pd.DataFrame) -> int:
    """Rewrite the log with ``rows`` replacing anything from the same day.

    :func:`gaffer.snapshot.append_snapshot`'s body, for the same reasons in
    the same order: parquet has no append and a few hundred rows a day is
    cheap to re-emit; replacement keyed on ``snap_date`` is what makes a hand
    re-run free; and the temp-file-plus-``os.replace`` is what stops a job
    killed mid-parquet from costing every day already banked.

    ``store.DATA_DIR`` is read here rather than bound at import so a test that
    redirects it redirects both paths together.
    """
    existing = (store.load(PRICE_LOG_PATH) if store.exists(PRICE_LOG_PATH)
                else pd.DataFrame(columns=PRICE_LOG_COLS))
    for col in PRICE_LOG_COLS:
        if col not in existing.columns:
            existing[col] = None
    days = set(rows["snap_date"].astype(str))
    kept = existing[~existing["snap_date"].astype(str).isin(days)]
    frames = [f[PRICE_LOG_COLS] for f in (kept, rows) if not f.empty]
    merged = (pd.concat(frames, ignore_index=True) if frames
              else rows[PRICE_LOG_COLS])
    tmp_rel = PRICE_LOG_PATH + ".tmp"
    tmp = store.DATA_DIR / tmp_rel
    try:
        store.save(merged, tmp_rel)
        os.replace(tmp, store.DATA_DIR / PRICE_LOG_PATH)
    finally:
        tmp.unlink(missing_ok=True)
    return int(len(rows))


def load_price_log() -> pd.DataFrame:
    """Every banked day, or an empty frame with the right columns."""
    if not store.exists(PRICE_LOG_PATH):
        return pd.DataFrame(columns=PRICE_LOG_COLS)
    return store.load(PRICE_LOG_PATH)


def bank_prices(players: pd.DataFrame | None,
                day: str | None = None) -> int | None:
    """Bank today's predictor readings. Rows written, or ``None``.

    Every failure lands in the one ``except`` and becomes a printed line. This
    is instrumentation running after the command has already printed what the
    user asked for, and instrumentation never blocks: a read-only disk on one
    Tuesday night should cost that Tuesday's row and absolutely nothing else.
    """
    try:
        rows = price_rows(players, day=day)
        n = append_prices(rows)
        print(f"Banked {n} price readings for "
              f"{rows['snap_date'].iloc[0]} to {PRICE_LOG_PATH}.")
        return n
    except Exception as exc:  # noqa: BLE001 — a scheduled job never blocks
        print(f"price log not written: {exc}")
        return None
