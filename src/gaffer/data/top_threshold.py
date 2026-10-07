"""The top-10k threshold: the season total at overall rank 10,000, by day.

ROADMAP candidate 3 (holiday F-4). The Field panel's ``P(top-10k)`` row has
been an empty state since v12 because "a weekly score threshold exists in no
source this project reads". It is one request away: the overall classic
league's standings come fifty to a page, so page 200's last row by
``rank_sort`` is the 10,000th entry, and its ``total`` is the line a squad has
to be above. ``tier_eo`` already walks the same pages for its sample; this
reads one of them for a different number.

``data/live/top_threshold_log.parquet``
    one row per (gameweek, scrape day). :mod:`gaffer.data.field`'s idiom: a
    rewrite keyed on (gw, snap_date), so a hand re-run is free and the last
    reading of a day stands. The standings move all through a gameweek, so
    the reading a reader wants for a finished week is that week's *latest*
    day, which is what :func:`threshold_series` returns.

**Anonymous by construction**, as the field sample is: the row is parsed down
to ranks and points at the fetch boundary, and no entry id or name is kept.

Nothing here raises for a scheduled caller: :func:`bank_threshold` is called
from the daily snapshot job and swallows everything, for ``run_snapshot``'s
reason — instrumentation never blocks.
"""

from __future__ import annotations

import pandas as pd

from gaffer.clock import snap_date
from gaffer.data import store
from gaffer.data.field import scrape_gw
from gaffer.data.tier_eo import MAX_PAGE, PAGE_SIZE, TIER_LEAGUE
from gaffer.io import atomic_save

THRESHOLD_PATH = "live/top_threshold_log.parquet"

THRESHOLD_RANK = MAX_PAGE * PAGE_SIZE
"""10,000, from the page arithmetic ``tier_eo`` already owns, so "the top
10k" means one set of pages in both modules."""

THRESHOLD_COLS = ["season", "gw", "snap_date", "rank_sort", "rank", "total",
                  "event_total", "last_updated"]
"""``rank_sort`` is the position (unique, 10,000 when the page is whole);
``rank`` is FPL's tied rank, kept because a tie at the line means everyone on
that total is in. ``event_total`` is the threshold entry's own week, one
manager's number, kept as served and not to be read as the field's week.
``last_updated`` is the payload's ``last_updated_data``: the standings are
recomputed in batches, and a reading taken before a batch is an older fact
than its ``snap_date`` says."""


def parse_threshold(payload: dict) -> dict | None:
    """The 10,000th row of a page-200 payload, as ranks and points only.

    The row with the largest ``rank_sort`` on the page, rather than
    ``results[-1]``, so a payload served out of order still names the right
    entry. ``None`` when the page is empty, short or shaped differently: a
    page whose last position is not 10,000 is a league with fewer entries,
    whose last row is not the line, and a changed API is a missing reading,
    not an exception.
    """
    try:
        results = payload["standings"]["results"]
        rows = [r for r in results
                if isinstance(r, dict) and r.get("rank_sort") is not None]
        if not rows:
            return None
        row = max(rows, key=lambda r: int(r["rank_sort"]))
        if int(row["rank_sort"]) != THRESHOLD_RANK:
            return None
        return {"rank_sort": int(row["rank_sort"]),
                "rank": int(row.get("rank") or 0),
                "total": int(row["total"]),
                "event_total": int(row.get("event_total") or 0),
                "last_updated": str(payload.get("last_updated_data") or "")}
    except (KeyError, TypeError, ValueError):
        return None


def fetch_threshold(client) -> dict | None:
    """One standings request, parsed. ``None`` on any failure."""
    try:
        payload = client.get_league_standings(TIER_LEAGUE, MAX_PAGE)
    except Exception:  # noqa: BLE001 — a page that will not load is no reading, as in tier_eo
        return None
    return parse_threshold(payload)


def threshold_rows(reading: dict, gw: int, season: str,
                   day: str | None = None) -> pd.DataFrame:
    """One reading -> one dated log row, dtypes forced as
    :func:`gaffer.data.field.field_eo_rows` forces them, for its reason."""
    row = {"season": str(season or ""), "gw": int(gw),
           "snap_date": str(day or snap_date()), **reading}
    out = pd.DataFrame([row], columns=THRESHOLD_COLS)
    for col in ("season", "snap_date", "last_updated"):
        out[col] = out[col].astype("object").astype("string")
    for col in ("gw", "rank_sort", "rank", "total", "event_total"):
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0) \
            .astype("int64")
    return out[THRESHOLD_COLS]


def append_threshold(rows: pd.DataFrame) -> int:
    """Rewrite the log with ``rows`` replacing the same (gw, snap_date) keys.

    :func:`gaffer.data.field.append_field_eo`'s trade: one row a day is cheap
    to re-emit, and replacement is what makes a second run in a day free.
    """
    if rows.empty:
        return 0
    existing = load_threshold_log()
    keys = set(zip(rows["gw"].astype(int).tolist(),
                   rows["snap_date"].astype(str).tolist()))
    kept = existing[[(int(g), str(d)) not in keys
                     for g, d in zip(existing["gw"], existing["snap_date"])]]
    frames = [f[THRESHOLD_COLS] for f in (kept, rows) if not f.empty]
    merged = (pd.concat(frames, ignore_index=True) if frames
              else rows[THRESHOLD_COLS])
    atomic_save(merged, THRESHOLD_PATH)
    return int(len(rows))


def load_threshold_log() -> pd.DataFrame:
    """Every banked row, or an empty frame with the right columns."""
    if not store.exists(THRESHOLD_PATH):
        return pd.DataFrame(columns=THRESHOLD_COLS)
    log = store.load(THRESHOLD_PATH)
    for col in THRESHOLD_COLS:
        if col not in log.columns:
            log[col] = None
    return log[THRESHOLD_COLS]


def threshold_series(season: str) -> dict[int, int]:
    """``gw -> total at rank 10,000`` from each gameweek's latest day.

    ``season`` is required, :func:`gaffer.data.field.latest_field_eo`'s rule:
    a gameweek number names a different week either side of a rollover. The
    latest day because the standings settle as bonus and late fixtures land,
    and the last reading before the next deadline is the week's final one.
    Empty on any failure: this is a display read.
    """
    try:
        log = load_threshold_log()
        log = log[log["season"].astype(str) == str(season)]
        out: dict[int, int] = {}
        for gw, part in log.groupby("gw"):
            day = max(str(d) for d in part["snap_date"])
            out[int(gw)] = int(part[part["snap_date"].astype(str) == day]
                               ["total"].iloc[-1])
    except Exception:  # noqa: BLE001 — a display read never blocks a page, and an old log's null cell is no series
        return {}
    return dict(sorted(out.items()))


def bank_threshold(client, events: pd.DataFrame, season: str,
                   now=None) -> int | None:
    """Fetch and bank today's reading for the last gameweek whose deadline
    has passed. Rows written, or ``None``; prints one line when it fetched.

    The gameweek is :func:`gaffer.data.field.scrape_gw`'s, not the snapshot's
    next unfinished one: the standings describe the week being played or just
    played, which is the week a deadline has passed for. Before the first
    deadline there is nothing to read and nothing is fetched or printed.
    """
    try:
        gw = scrape_gw(events, now=now)
        if gw is None:
            return None
        reading = fetch_threshold(client)
        if reading is None:
            print(f"top-10k threshold not banked: page {MAX_PAGE} of the "
                  f"overall standings had no readable row")
            return None
        day = snap_date()
        n = append_threshold(threshold_rows(reading, gw, season, day))
        print(f"Top-10k threshold: {reading['total']} points at rank "
              f"{reading['rank_sort']} for gw{gw} at {day}.")
        return n
    except Exception as exc:  # noqa: BLE001 — a scheduled job never blocks
        print(f"top-10k threshold not banked: {exc}")
        return None
