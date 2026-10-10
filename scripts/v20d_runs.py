"""v20d's per-run reading: did each Thursday run bank, and did the term charge?

v20 spec §2 v20d "Lever check per run" and its verdict table. Each Thursday
advise run from 2026-09-17 on (GW5's, the first after v19b's merge) is read
from three places:

- the advise log, ``logs/advise.log``, which the Thursday plist appends to
  without timestamps. ``pipeline.bank_price_reading`` logs nothing on
  success, and ``prices_banked`` lives only on ``RunResult``, so the log can
  only say the step *failed* ("price reading not banked: …"). The log is cut
  into runs at the CLI's ``=== GW{n} — deadline … ===`` header, which
  ``gaffer advise`` prints after ``weekly_run`` returns, so a failure line
  belongs to the next header below it (holiday F-16).
- the price log, ``data/live/price_log.parquet``: the rows banked on the
  run's UTC day, and that day's ``drop`` readings (``price_change_percent <
  0``, not calibrating, the test ``price_timing.price_falls`` applies).
- the served plan, ``reports/gw{n}-advice.json`` and the runs banked under
  ``reports/advice_history/``: ``generated_at`` gives the run's UTC day, the
  head week's ``sells`` the sales, and its ``trace.price_charge`` the term.
  ``price_fall`` is an input and is not served, whatever the spec says.

A run is a Thursday (UTC) payload; the earliest on a given Thursday for a
gameweek is the plist's, because a web re-run comes after it and the
``reports/gw{n}-advice.json`` file is overwritten by the newest. A run's lever
holds when the log carries no failure line for its gameweek **and** the price
log has rows for its UTC day; rows on an earlier day only are "banked a
different day", which is the first row of the table too.

The table's rows, in the order they are tested:

1. ``step``: any run that did not bank, or banked on another UTC day.
2. ``reader``: every run banked, a ``drop``-flagged sale, and that run's
   ``price_charge`` reads ``None`` or ``0.0``. Ruling (holiday F-16): this
   row wins over ``live`` when the runs disagree, because one silent reader
   is a defect whatever the other weeks did.
3. ``live``: every run banked, at least one ``drop``-flagged sale, each with a
   numeric non-zero ``price_charge``.
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
NOT_BANKED = "price reading not banked:"
HEADER = re.compile(r"^=== GW(\d+) — deadline (.*?) ===\s*$")

ADVISE_LOG = Path("logs/advise.log")
REPORTS = Path("reports")


def log_runs(text: str | None) -> dict[int, dict]:
    """``{gw: {"runs": k, "failures": [...]}}`` out of the advise log.

    Lines between one header and the next belong to the second header's run,
    since the failure line is logged inside ``weekly_run`` before the CLI
    prints the header. A run that died before its header leaves its lines to
    the next run's; that is the one way this can misattribute, and a run that
    dies before the solve has no plan for this reading to read anyway.
    """
    out: dict[int, dict] = {}
    pending: list[str] = []
    for line in (text or "").splitlines():
        if NOT_BANKED in line:
            pending.append(line.strip())
            continue
        m = HEADER.match(line.strip())
        if m:
            entry = out.setdefault(int(m.group(1)), {"runs": 0, "failures": []})
            entry["runs"] += 1
            entry["failures"].extend(pending)
            pending = []
    return out


def _utc_day(stamp: str | None) -> date | None:
    if not stamp:
        return None
    try:
        when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is not None:
        when = when.astimezone(timezone.utc)
    return when.date()


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
    """The earliest Thursday payload per gameweek and day, oldest first."""
    chosen: dict[tuple[int, date], tuple[str, dict]] = {}
    for payload in payloads:
        day = _utc_day(payload.get("generated_at"))
        if day is None or day < since or day.weekday() != THURSDAY:
            continue
        try:
            key = (int(payload["gw"]), day)
        except (TypeError, ValueError):
            continue
        stamp = str(payload["generated_at"])
        if key not in chosen or stamp < chosen[key][0]:
            chosen[key] = (stamp, payload)
    return [chosen[k][1] for k in sorted(chosen, key=lambda k: (k[1], k[0]))]


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


def run_reading(payload: dict, logged: dict[int, dict] | None,
                prices: pd.DataFrame | None) -> dict:
    """One ``V20D_RUN`` payload. ``logged`` is ``None`` when no log exists."""
    gw = int(payload["gw"])
    day = _utc_day(payload.get("generated_at"))
    week = _head_week(payload)
    sells = _codes(week.get("sells"))
    out = {"gw": gw, "day": day.isoformat() if day else None,
           "generated_at": payload.get("generated_at"),
           "log_runs": None, "log_failure": None, "rows_that_day": None,
           "last_banked_before": None, "sells": sells, "drop_sells": [],
           "price_charge": _charge(week), "lever": None, "reason": None}

    reasons = []
    if logged is None:
        reasons.append(f"no advise log at {ADVISE_LOG}")
    else:
        entry = logged.get(gw)
        out["log_runs"] = entry["runs"] if entry else 0
        failures = entry["failures"] if entry else []
        out["log_failure"] = failures[0] if failures else None
        if not entry:
            reasons.append(f"no GW{gw} header in the advise log")

    frame = _prepared(prices)
    if frame is None:
        reasons.append(f"no price log at {store.DATA_DIR / PRICE_LOG_PATH}")
    elif day is not None:
        that_day = frame[frame["snap_date"] == day.isoformat()]
        out["rows_that_day"] = int(len(that_day))
        earlier = sorted(d for d in frame["snap_date"].unique()
                         if d < day.isoformat())
        out["last_banked_before"] = earlier[-1] if earlier else None
        drops = that_day[that_day["pct"].notna() & (that_day["pct"] < 0)]
        if "calibrating" in drops.columns:
            drops = drops[~drops["calibrating"].fillna(False).astype(bool)]
        drop_codes = {int(c) for c in drops["code"].dropna()}
        out["drop_sells"] = [c for c in sells if c in drop_codes]

    if out["log_failure"]:
        out["lever"] = "step: not banked"
    elif out["rows_that_day"] == 0:
        out["lever"] = ("step: banked a different day"
                        if out["last_banked_before"] else "step: not banked")
    elif reasons:
        out["lever"] = "no reading"
    elif not out["drop_sells"]:
        out["lever"] = "banked, no drop sale"
    elif out["price_charge"]:
        out["lever"] = "banked, drop sale charged"
    else:
        out["lever"] = "banked, drop sale uncharged"
    out["reason"] = "; ".join(reasons) or None
    return out


def table_row(runs: list[dict]) -> dict:
    """The ``V20D_ROW`` payload: which of the spec's four rows holds."""
    n = len(runs)
    out = {"runs": n, "short": n < MIN_RUNS, "row": None, "reason": None}
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
    logged = None if log_text is None else log_runs(log_text)
    runs = [run_reading(p, logged, prices) for p in thursday_runs(payloads)]
    return runs, table_row(runs)


def main() -> int:
    try:
        log_text = ADVISE_LOG.read_text(errors="replace") if ADVISE_LOG.is_file() else None
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
        runs, row = [], {"runs": 0, "short": True, "row": None,
                         "reason": f"reports unreadable: {type(exc).__name__}"}
    if not REPORTS.is_dir():
        row = {**row, "reason": f"no reports directory at {REPORTS}"}
    for run in runs:
        print(f"V20D_RUN {json.dumps(run, sort_keys=True)}")
    print(f"V20D_ROW {json.dumps(row, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
