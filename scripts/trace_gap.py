"""The trace's unattributed share, the reading (holiday F-86).

GUIDE §12.4: "The trace does not attribute the squad-side terms, so its lines
do not sum to the week's xPts" (ROADMAP "Residuals carried out of v12"). The
v20 spec §4 keeps the attribution itself out of scope, since it would be an
``advise.py`` decoration; this script is the reading taken before any ruling.

It reads every banked advice: ``reports/gw{n}-advice.json`` (what
``artifacts.advice_path`` writes) and ``reports/advice_history/gw*-*.json``.
For each traced served week (``ServedWeek.trace``, a ``PlanWeekTrace``) it
compares ``expected_pts`` with the sum of the trace's charges. The sum is
exactly what ``gaffer.trace.trace_plan`` writes, with signs as the objective
carries them:

    attributed = ep_gain - hit_cost - ft_use_penalty - price_charge

``ep_gain`` is the week's moves' decayed swap gains summed. ``hit_cost`` and
``ft_use_penalty`` are decayed by ``decay ** i`` as the objective decays
them. A ``price_charge`` of ``None`` counts as 0: either the term is off
(the objective carried no such charge) or its inputs were unrecorded.
``ft_shadow`` and ``bank_value`` are valuations, not this week's charges,
so they stay out, as the ``PlanWeekTrace`` docstring keeps them. The
unattributed share is ``(expected_pts - attributed) / expected_pts``. It is
what the XI, captain, vice and bench terms carry, the squad-side terms the
docstring names.

A week whose ``ep_gain`` is ``None`` (some move could not be priced) is not
read: unknown is not zero. Neither is a week with no positive
``expected_pts``, where a share is undefined. A payload banked twice (the
current file and its history copy share ``gw`` and ``generated_at``) is
read once.

It prints one ``TRACE_GAP {…}`` per file and then ``TRACE_GAPS {…}``. The
file line gives the gameweek, the weeks traced, the share over those weeks
(sum of unattributed over sum of ``expected_pts``) and its min and max over
the weeks. The summary covers every file.

The rule, pre-registered before the script first ran (holiday F-86): if the
per-week share's spread (max - min) over every week of every banked file is
under ``SPREAD_AT`` (0.05), the verdict is ``ruling``. The board's caption
could then carry the number ("the squad-side terms, about n%"), which is
Anu's call; the default is that the sentence stays as it is. Otherwise the
verdict is ``hold``: the sentence stays, and the line is the evidence that
attribution needs the solve. The spread is per week, because the caption
sits under each week's lines (ruling, holiday F-86). The script writes
nothing and changes no default.

A missing ``reports/``, an unreadable file or an advice the served reader
cannot read prints its line with a reason, never a traceback, because the
night shift transcribes the lines.

    uv run python scripts/trace_gap.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import ValidationError

from gaffer.served import ServedPlan

REPORTS = Path("reports")
SPREAD_AT = 0.05
"""The per-week spread under which one number could stand in the caption."""

CURRENT = re.compile(r"^gw(\d+)-advice\.json$")
HISTORY = re.compile(r"^gw(\d+)-.+\.json$")


def week_share(week) -> float | None:
    """One served week's unattributed share, or ``None`` when it cannot be
    read (no trace, an unpriced move, no positive ``expected_pts``)."""
    trace = week.trace
    if trace is None or trace.ep_gain is None:
        return None
    xpts = float(week.expected_pts)
    if not xpts > 0:
        return None
    attributed = (float(trace.ep_gain) - float(trace.hit_cost)
                  - float(trace.ft_use_penalty)
                  - float(trace.price_charge or 0.0))
    return (xpts - attributed) / xpts


def read_file(path: Path, payload: dict) -> dict:
    """One ``TRACE_GAP`` row, or ``reason`` when there is nothing to read."""
    name = str(path)
    try:
        plan = ServedPlan.model_validate(payload)
    except ValidationError:
        return {"file": name, "reason": "unreadable advice"}
    shares, xpts, gaps = [], 0.0, 0.0
    for week in plan.plan_by_gw:
        share = week_share(week)
        if share is None:
            continue
        shares.append(share)
        xpts += float(week.expected_pts)
        gaps += share * float(week.expected_pts)
    if not shares:
        return {"file": name, "gw": plan.gw, "weeks_traced": 0,
                "reason": "no traced week with a priced gain"}
    return {"file": name, "gw": plan.gw, "weeks_traced": len(shares),
            "share": round(gaps / xpts, 4),
            "min": round(min(shares), 4), "max": round(max(shares), 4),
            "_shares": shares, "_xpts": xpts, "_gaps": gaps}


def _paths(reports: Path) -> list[Path]:
    found = [p for p in reports.iterdir() if CURRENT.match(p.name)]
    history = reports / "advice_history"
    if history.is_dir():
        found += [p for p in history.iterdir()
                  if p.is_file() and HISTORY.match(p.name)]
    return sorted(found)


def read_all(reports: Path = REPORTS) -> tuple[list[dict], dict]:
    """``(rows, summary)`` over every banked advice."""
    if not reports.is_dir():
        return [], {"files": 0, "reason": f"no {reports}/ directory",
                    "verdict": "hold"}
    rows, seen = [], set()
    for path in _paths(reports):
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            rows.append({"file": str(path),
                         "reason": f"unreadable: {exc.__class__.__name__}"})
            continue
        if not isinstance(payload, dict):
            rows.append({"file": str(path), "reason": "unreadable: not an object"})
            continue
        key = (payload.get("gw"), payload.get("generated_at"))
        if key[1] is not None and key in seen:
            continue
        seen.add(key)
        rows.append(read_file(path, payload))
    read = [r for r in rows if "share" in r]
    shares = [s for r in read for s in r["_shares"]]
    summary: dict = {"files": len(read), "skipped": len(rows) - len(read),
                     "weeks": len(shares)}
    if shares:
        spread = max(shares) - min(shares)
        summary.update(
            share=round(sum(r["_gaps"] for r in read)
                        / sum(r["_xpts"] for r in read), 4),
            min=round(min(shares), 4), max=round(max(shares), 4),
            spread=round(spread, 4),
            verdict="ruling" if spread < SPREAD_AT else "hold")
    else:
        summary.update(verdict="hold",
                       reason=f"no traced week in {reports}/")
    for r in read:
        for k in ("_shares", "_xpts", "_gaps"):
            del r[k]
    return rows, summary


def main(reports: Path = REPORTS) -> None:
    rows, summary = read_all(reports)
    for row in rows:
        print(f"TRACE_GAP {json.dumps(row)}")
    print(f"TRACE_GAPS {json.dumps(summary)}")


if __name__ == "__main__":
    main()
