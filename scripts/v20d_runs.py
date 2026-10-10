"""v20d's per-run reading: did each Thursday run bank, and did the term see it?

v20 spec §2 v20d "Lever check per run" and its verdict table. Each Thursday
advise run from 2026-09-17 on (GW5's, the first after v19b's merge) is read
from three places:

- the advise log, ``logs/advise.log``, which the Thursday plist appends to
  without timestamps. ``pipeline.bank_price_reading`` logs a failure ("price
  reading not banked: …") and nothing on success, but the ``bank_prices`` it
  calls prints ``Banked N price readings for D …`` or ``price log not
  written: …`` to the same stdout, so the log names the bank's count and UTC
  day. The log is cut into runs at the CLI's ``=== GW{n} — deadline … ===``
  header, printed after ``weekly_run`` returns, so a bank line belongs to the
  next header below it; a gameweek's first header is the Thursday plist's,
  since nothing else appends to this log (holiday F-16).
- the price log, ``data/live/price_log.parquet``: that UTC day's ``drop``
  readings (``price_change_percent < 0``, not calibrating, the test
  ``price_timing.price_falls`` applies). The log keeps one reading per day
  and the nightly ``com.gaffer.prices`` plist (23:15 London, the same UTC
  day) replaces the 18:00 one, so these are the day's *last* readings, not
  the ones the solve saw, and its row count cannot show the 18:00 bank. That
  is why the bank is read from the advise log first, and the row count only
  when the log carries neither a bank nor a failure line.
- the served plan, ``reports/gw{n}-advice.json`` and the runs banked under
  ``reports/advice_history/``: ``generated_at`` gives the run's UTC day, the
  head week's ``sells`` the sales and its ``trace.price_charge`` the term.
  ``price_fall`` is an input and is not served, whatever the spec says.

The trace charges only a sale scheduled for a *later* week
(``trace.py``'s W2 §3.4 block): a head-week sale reads ``0.0`` with
``price_timing`` on and ``None`` with it off. So the spec's "a numeric
``price_charge``" holds at ``0.0`` on the head week, and only ``None`` there
is the reader's row. Ruling (holiday F-16), against the spec table's "``None``
or ``0.0``", which would read the term working as a defect.

A run is the earliest Thursday payload for a gameweek written at or after
16:00 UTC (the plist fires 18:00 London: 17:00 UTC in summer, 18:00 in
winter), so a Thursday-morning web run is not taken for it. A gameweek whose
header is in the log but whose Thursday payload is gone (``advice_history``
keeps twenty runs; ``gw{n}-advice.json`` holds the newest) prints its line as
``missing`` with the reason and is named in the row line, not read.

The table's rows, in the order they are tested:

1. ``step``: any run that did not bank, or banked on another UTC day.
2. ``reader``: every run banked, a ``drop``-flagged sale, and that run's
   head-week ``price_charge`` reads ``None``. This row wins over ``live`` when
   the runs disagree, because one silent reader is a defect whatever the
   other weeks did.
3. ``live``: every run banked and at least one ``drop``-flagged sale with a
   numeric head-week ``price_charge``.
4. ``no evidence``: every run banked, no head week sold a ``drop``-flagged
   player.

Fewer than three runs is read and marked ``short`` (the spec reads "at least
three"). Read-only: it writes nothing, changes no default and lands no fix
(the first row's fix is ``pipeline.py``'s, orchestrator-only). A missing log,
price log or report prints the lines with the reason, never a traceback,
because the night shift transcribes them into the spec's §6.

    uv run python scripts/v20d_runs.py
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from gaffer.data import store
from gaffer.price_log import PRICE_LOG_PATH, load_price_log

FIRST_RUN = date(2026, 9, 17)
"""GW5's Thursday, the first scheduled run after v19b (v20 spec §2 v20d)."""

MIN_RUNS = 3
THURSDAY = 3
PLIST_HOUR_UTC = 16
"""The earliest UTC hour a plist run can stamp (18:00 BST is 17:00 UTC)."""

FAILURES = ("price reading not banked:", "price log not written:")
BANKED = re.compile(r"Banked (\d+) price readings for (\d{4}-\d{2}-\d{2})")
HEADER = re.compile(r"^=== GW(\d+) — deadline (.*?) ===\s*$")

ADVISE_LOG = Path("logs/advise.log")
REPORTS = Path("reports")


def log_runs(text: str | None) -> dict[int, list[dict]]:
    """``{gw: [run, …]}`` out of the advise log, each run ``{"deadline",
    "failure", "banked", "banked_day"}``, in log order.

    Lines between one header and the next belong to the second header's run,
    since the bank is logged inside ``weekly_run`` before the CLI prints the
    header. A run that died before its header leaves its lines to the next
    run's; a run that dies before the solve has no plan to read anyway.
    """
    out: dict[int, list[dict]] = {}
    failure = banked = banked_day = None
    for line in (text or "").splitlines():
        line = line.strip()
        if any(f in line for f in FAILURES):
            failure = failure or line
            continue
        hit = BANKED.search(line)
        if hit:
            banked, banked_day = int(hit.group(1)), hit.group(2)
            continue
        m = HEADER.match(line)
        if m:
            out.setdefault(int(m.group(1)), []).append(
                {"deadline": m.group(2), "failure": failure,
                 "banked": banked, "banked_day": banked_day})
            failure = banked = banked_day = None
    return out


def _utc(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    try:
        when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is not None:
        when = when.astimezone(timezone.utc)
    return when


def _payloads(reports: Path) -> list[dict]:
    """Every readable advice payload, current files and banked history."""
    paths = sorted(reports.glob("gw*-advice.json"))
    history = reports / "advice_history"
    if history.is_dir():
        paths += sorted(history.glob("gw*-*.json"))
    out = []
    for path in paths:
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict) and payload.get("gw") is not None:
            out.append(payload)
    return out


def thursday_runs(payloads: list[dict], since: date = FIRST_RUN) -> list[dict]:
    """The plist's payload per gameweek: the earliest on a Thursday at or
    after ``PLIST_HOUR_UTC``, oldest first."""
    chosen: dict[int, tuple[datetime, dict]] = {}
    for payload in payloads:
        when = _utc(payload.get("generated_at"))
        if (when is None or when.date() < since
                or when.weekday() != THURSDAY or when.hour < PLIST_HOUR_UTC):
            continue
        try:
            gw = int(payload["gw"])
        except (TypeError, ValueError):
            continue
        if gw not in chosen or when < chosen[gw][0]:
            chosen[gw] = (when, payload)
    return [p for _, p in sorted(chosen.values(), key=lambda wp: wp[0])]


def _head_week(payload: dict) -> dict:
    weeks = payload.get("plan_by_gw") or []
    if isinstance(weeks, dict):
        weeks = list(weeks.values())
    weeks = [w for w in weeks if isinstance(w, dict)]
    for week in weeks:
        if week.get("gw") == payload.get("gw"):
            return week
    return weeks[0] if weeks else {"sells": payload.get("sells") or []}


def _codes(moves) -> list[int]:
    out = []
    for move in moves or []:
        try:
            out.append(int(move["code"]))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _charge(week: dict) -> float | None:
    trace = week.get("trace")
    value = trace.get("price_charge") if isinstance(trace, dict) else None
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _prepared(prices: pd.DataFrame | None) -> pd.DataFrame | None:
    if prices is None or prices.empty:
        return None
    frame = prices.copy()
    frame["snap_date"] = frame["snap_date"].astype(str)
    frame["code"] = pd.to_numeric(frame["code"], errors="coerce")
    frame["pct"] = pd.to_numeric(frame["price_change_percent"], errors="coerce")
    return frame


def run_reading(payload: dict, logged: dict[int, list[dict]] | None,
                prices: pd.DataFrame | None) -> dict:
    """One ``V20D_RUN`` payload. ``logged`` is ``None`` when no log exists."""
    gw = int(payload["gw"])
    when = _utc(payload.get("generated_at"))
    day = when.date().isoformat() if when else None
    week = _head_week(payload)
    sells = _codes(week.get("sells"))
    out = {"gw": gw, "day": day, "generated_at": payload.get("generated_at"),
           "log_runs": None, "log_failure": None, "log_banked": None,
           "log_banked_day": None, "rows_that_day": None, "sells": sells,
           "drop_sells": [], "price_charge": _charge(week), "lever": None,
           "reason": None}

    reasons = []
    first = None
    if logged is None:
        reasons.append(f"no advise log at {ADVISE_LOG}")
    else:
        entries = logged.get(gw) or []
        out["log_runs"] = len(entries)
        first = entries[0] if entries else None
        if first is None:
            reasons.append(f"no GW{gw} header in the advise log")
        else:
            out["log_failure"] = first["failure"]
            out["log_banked"] = first["banked"]
            out["log_banked_day"] = first["banked_day"]

    frame = _prepared(prices)
    if frame is None:
        reasons.append(f"no price log at {store.DATA_DIR / PRICE_LOG_PATH}")
    elif day is not None:
        that_day = frame[frame["snap_date"] == day]
        out["rows_that_day"] = int(len(that_day))
        drops = that_day[that_day["pct"].notna() & (that_day["pct"] < 0)]
        if "calibrating" in drops.columns:
            drops = drops[~drops["calibrating"].fillna(False).astype(bool)]
        drop_codes = {int(c) for c in drops["code"].dropna()}
        out["drop_sells"] = [c for c in sells if c in drop_codes]

    if out["log_failure"]:
        out["lever"] = "step: not banked"
    elif out["log_banked_day"] is not None and out["log_banked_day"] != day:
        out["lever"] = "step: banked a different day"
    elif out["log_banked_day"] is None and out["rows_that_day"] == 0:
        out["lever"] = "step: not banked"
    elif out["log_banked_day"] is None and first is not None:
        # Neither line: the step was off, or the log predates the print.
        reasons.append("no bank line in the run's log; the price log's row "
                       "count may be the nightly bank's, not the solve's")
        out["lever"] = "no reading"
    elif reasons:
        out["lever"] = "no reading"
    elif not out["drop_sells"]:
        out["lever"] = "banked, no drop sale"
    elif out["price_charge"] is not None:
        out["lever"] = "banked, drop sale charged"
    else:
        out["lever"] = "banked, drop sale uncharged"
    out["reason"] = "; ".join(reasons) or None
    return out


def missing_runs(logged: dict[int, list[dict]] | None, read: set[int],
                 since: date = FIRST_RUN) -> list[dict]:
    """Gameweeks the log ran for since ``since`` with no Thursday payload."""
    out = []
    for gw, entries in sorted((logged or {}).items()):
        deadline = _utc(entries[0]["deadline"])
        if gw in read or deadline is None or deadline.date() < since:
            continue
        out.append({"gw": gw, "day": None, "lever": "missing",
                    "log_runs": len(entries),
                    "reason": "no Thursday advice payload left in reports/ "
                              "(advice_history keeps twenty runs; "
                              "gw{n}-advice.json holds the newest)"})
    return out


def table_row(runs: list[dict], missing: list[dict] | None = None) -> dict:
    """The ``V20D_ROW`` payload: which of the spec's four rows holds."""
    n = len(runs)
    out = {"runs": n, "short": n < MIN_RUNS, "row": None,
           "missing": [m["gw"] for m in missing or []], "reason": None}
    if not runs:
        return {**out, "reason": f"no Thursday run since {FIRST_RUN}"}
    levers = [r["lever"] for r in runs]
    if any(lv.startswith("step:") for lv in levers):
        return {**out, "row": "step"}
    if any(lv == "no reading" for lv in levers):
        unread = [r["gw"] for r in runs if r["lever"] == "no reading"]
        return {**out, "reason": f"runs unread: GW{unread}"}
    if "banked, drop sale uncharged" in levers:
        return {**out, "row": "reader"}
    if "banked, drop sale charged" in levers:
        return {**out, "row": "live"}
    return {**out, "row": "no evidence"}


def reading(log_text: str | None, payloads: list[dict],
            prices: pd.DataFrame | None) -> tuple[list[dict], dict]:
    """Every ``V20D_RUN`` payload (read runs, then missing ones) and the row."""
    logged = None if log_text is None else log_runs(log_text)
    runs = [run_reading(p, logged, prices) for p in thursday_runs(payloads)]
    missing = missing_runs(logged, {r["gw"] for r in runs})
    return runs + missing, table_row(runs, missing)


def main() -> int:
    try:
        log_text = (ADVISE_LOG.read_text(errors="replace")
                    if ADVISE_LOG.is_file() else None)
    except OSError:
        log_text = None
    prices = None
    if store.exists(PRICE_LOG_PATH):
        try:
            prices = load_price_log()
        except (OSError, ValueError, KeyError, TypeError):
            # A corrupt parquet raises ArrowInvalid (a ValueError); each run
            # then names the missing price log as its reason.
            prices = None
    try:
        runs, row = reading(log_text, _payloads(REPORTS), prices)
    except (KeyError, TypeError, ValueError) as exc:
        runs, row = [], {"runs": 0, "short": True, "row": None, "missing": [],
                         "reason": f"reports unreadable: {type(exc).__name__}"}
    if not REPORTS.is_dir():
        row = {**row, "reason": f"no reports directory at {REPORTS}"}
    for run in runs:
        print(f"V20D_RUN {json.dumps(run, sort_keys=True)}")
    print(f"V20D_ROW {json.dumps(row, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
