"""The daily availability snapshot: what the news said, stamped with the day.

``reports/availability_gw{N}.parquet`` is one file per gameweek, overwritten by
every advise run (``artifacts.py:390``), and the raw news cache is bucketed by
fetch time only. So the shape of a week's injury news is visible only at the
moment a run happened, and every day nobody runs one is corrector training data
lost for ever. This log is the fix: one row per player per day, kept.

Nothing here may raise. The caller is a launchd job at 17:00 with nowhere to
report a traceback, and a missed day is a far cheaper failure than a job that
dies loudly every afternoon.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from gaffer.artifacts import AVAILABILITY_COLS
from gaffer.data import store
from gaffer.errors import GafferError

SNAPSHOT_PATH = "live/availability_log.parquet"

SNAPSHOT_COLS = ["season", "gw", "snap_date"] + AVAILABILITY_COLS
"""The availability contract, prefixed with the three keys that date it.

Reused from :mod:`gaffer.artifacts` rather than restated: the news endpoint,
the per-gameweek snapshot and this log all read one column list, so a source
that starts carrying a new field lands in all three at once.
"""


def snap_date(now: datetime | None = None) -> str:
    """Today in UTC, ``YYYY-MM-DD``. The log's idempotency key.

    UTC rather than local time so a machine that travels, or one running the
    job either side of a clock change, cannot bank two "days" for one.
    """
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")


def next_unfinished_gw(events: pd.DataFrame) -> int:
    """The gameweek this snapshot is about: the first one not yet finished.

    Not ``is_next``, which goes false for the hours a gameweek is actually
    being played — a snapshot taken on a Saturday evening still belongs to
    that gameweek's news cycle, and stamping it with the following one would
    file Saturday's team news against next week's deadline.
    """
    pending = events[~events["finished"].astype(bool)]
    if pending.empty:
        raise GafferError(
            "no unfinished gameweek in the bootstrap — the season is over")
    return int(pending["gw"].min())


def snapshot_rows(avail: pd.DataFrame, gw: int, season: str = "",
                  day: str | None = None) -> pd.DataFrame:
    """The availability frame -> dated log rows, one per player.

    Columns a flags-only week never produced are filled with nulls and settled
    dtypes, the same trade :func:`gaffer.artifacts.save_availability` makes:
    parquet wants one dtype per column, and an all-``None`` object column has
    none, so a quiet week and a news-heavy one would otherwise write two
    incompatible schemas into one growing file.
    """
    out = avail.copy()
    for col in AVAILABILITY_COLS:
        if col not in out.columns:
            out[col] = None
    out = out[AVAILABILITY_COLS].copy()
    for col in ("status", "injury_type", "source", "fetched_at"):
        out[col] = out[col].astype("object").where(
            out[col].notna(), None).astype("string")
    for col in ("chance_of_playing", "expected_return_gw", "p_start_hint"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["code"] = pd.to_numeric(out["code"], errors="coerce").astype("int64")
    out.insert(0, "snap_date", str(day or snap_date()))
    out.insert(0, "gw", int(gw))
    out.insert(0, "season", str(season or ""))
    return out[SNAPSHOT_COLS]


def append_snapshot(rows: pd.DataFrame) -> int:
    """Rewrite the log with ``rows`` replacing anything from the same day.

    Append-by-rewrite, like :func:`gaffer.news_shadow.write_shadow`: parquet
    has no append, and at a few hundred rows a day the whole file is cheap to
    re-emit. Replacement rather than accumulation, keyed on ``snap_date``, is
    what makes a hand re-run free.

    Returns the number of rows banked for the day.
    """
    existing = (store.load(SNAPSHOT_PATH) if store.exists(SNAPSHOT_PATH)
                else pd.DataFrame(columns=SNAPSHOT_COLS))
    for col in SNAPSHOT_COLS:
        if col not in existing.columns:
            existing[col] = None
    days = set(rows["snap_date"].astype(str))
    kept = existing[~existing["snap_date"].astype(str).isin(days)]
    frames = [f[SNAPSHOT_COLS] for f in (kept, rows) if not f.empty]
    merged = (pd.concat(frames, ignore_index=True) if frames
              else rows[SNAPSHOT_COLS])
    store.save(merged, SNAPSHOT_PATH)
    return int(len(rows))


def load_snapshot_log() -> pd.DataFrame:
    """Every banked day, or an empty frame with the right columns."""
    if not store.exists(SNAPSHOT_PATH):
        return pd.DataFrame(columns=SNAPSHOT_COLS)
    return store.load(SNAPSHOT_PATH)
