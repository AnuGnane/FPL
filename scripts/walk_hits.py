"""The walk's hits against the objective's, the reading (holiday F-25).

GUIDE §12.4's v16 residual: the restraint walk is symmetric by design, so it
can serve more hits than the objective's own week wanted (the GW4 board
served one hit where the objective wanted none, on a 60.25% share). The
residual calls "the walk never goes above the objective's hits" a one-line
candidate if a season says otherwise; this script is that season's reading.

Over this season's ``reports/gw{n}-advice.json`` it reads, through
``ladder.narrated`` (so a file banked before v17b is read as the brief reads
it), the served ``hits``, ``objective.hits``, the restraint block's chosen
rung and label, and the share of the last step the walk took, and prints one
``WALK_HITS_GW {…}`` per gameweek, then ``WALK_HITS {…}``: the gameweeks read,
how many served more hits than the objective (``above``) and fewer
(``below``), and those gameweeks named.

"This season" is every payload whose ``generated_at`` falls on or after
1 July of the newest payload's season (July to June); a payload without a
stamp is kept, since the ``gw{n}`` files are overwritten each season and an
unstamped one cannot be placed (ruling, holiday F-25).

A ``chosen`` of ``None`` reads "bank": no rung was chosen, so the served plan
is the bank's. ``last_taken_share`` is ``None`` when the walk took no step.

The rule, pre-registered before the script first ran (holiday F-25): the
"never above the objective's hits" rule is worth a replay arm iff three or
more gameweeks this season served more hits than the objective wanted
(``verdict: "arm"``); otherwise ``verdict: "hold"``. The rule itself would be
a replay arm, the Mac's; this script writes nothing, edits neither
``ladder.py`` nor ``advise.py`` and changes no default.

A missing ``reports/``, an unreadable file, an advice ``ladder.narrated``
cannot read or an advice without an ``objective`` block prints its line with
a reason, never a traceback, because the night shift transcribes the lines.

    uv run python scripts/walk_hits.py
"""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from pathlib import Path

from gaffer.ladder import narrated

REPORTS = Path("reports")
ARM_AT = 3
"""Gameweeks above the objective's hits that make the rule worth an arm."""

ADVICE = re.compile(r"^gw(\d+)-advice\.json$")


def _stamp(payload: dict) -> date | None:
    try:
        return datetime.fromisoformat(str(payload["generated_at"]).replace("Z", "+00:00")).date()
    except (KeyError, TypeError, ValueError):
        return None


def _season_start(day: date) -> date:
    return date(day.year if day.month >= 7 else day.year - 1, 7, 1)


def read_week(gw: int, payload: dict) -> dict:
    """One ``WALK_HITS_GW`` row: the hits on both sides and the walk's
    choice, or ``reason`` when the payload cannot be read against them.

    An advice with no ``restraint`` block at all (banked before v16) reads
    ``chosen: None``, not "bank": no walk is on record. A non-finite share
    reads ``None`` so the line stays strict JSON."""
    try:
        advice = narrated(payload)
        objective = advice.get("objective")
        if not isinstance(objective, dict):
            return {"gw": gw, "reason": "no objective block"}
        restraint = advice.get("restraint")
        walked = isinstance(restraint, dict)
        steps = (restraint.get("steps") or []) if walked else []
        taken = [s for s in steps if s.get("taken")]
        share = float(taken[-1]["share"]) if taken else None
        served, wanted = int(advice.get("hits") or 0), int(objective.get("hits") or 0)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        return {"gw": gw, "reason": f"unreadable advice: {exc.__class__.__name__}"}
    relation = "above" if served > wanted else "below" if served < wanted else "equal"
    return {"gw": gw, "served_hits": served, "objective_hits": wanted,
            "relation": relation,
            "chosen": (restraint.get("chosen") or "bank") if walked else None,
            "label": restraint.get("label") if walked else None,
            "last_taken_share": share if share is None or math.isfinite(share) else None}


def read_season(reports: Path = REPORTS) -> tuple[list[dict], dict]:
    """``(rows, summary)`` over this season's advice files."""
    if not reports.is_dir():
        return [], {"read": 0, "reason": f"no {reports}/ directory"}
    loaded: list[tuple[int, dict | None, str | None]] = []
    for path in reports.iterdir():
        m = ADVICE.match(path.name)
        if not m:
            continue
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            loaded.append((int(m.group(1)), None, f"unreadable: {exc.__class__.__name__}"))
            continue
        if not isinstance(payload, dict):
            loaded.append((int(m.group(1)), None, "unreadable: not an object"))
            continue
        loaded.append((int(m.group(1)), payload, None))
    stamps = [d for _, p, _ in loaded if p is not None and (d := _stamp(p)) is not None]
    start = _season_start(max(stamps)) if stamps else None
    rows = []
    for gw, payload, reason in sorted(loaded, key=lambda t: t[0]):
        if payload is None:
            rows.append({"gw": gw, "reason": reason})
            continue
        day = _stamp(payload)
        if start is not None and day is not None and day < start:
            continue
        rows.append(read_week(gw, payload))
    read = [r for r in rows if "relation" in r]
    above = [r["gw"] for r in read if r["relation"] == "above"]
    below = [r["gw"] for r in read if r["relation"] == "below"]
    summary = {"read": len(read), "skipped": len(rows) - len(read),
               "above": len(above), "below": len(below),
               "equal": len(read) - len(above) - len(below),
               "above_gws": above, "below_gws": below,
               "season_from": start.isoformat() if start else None,
               "verdict": "arm" if len(above) >= ARM_AT else "hold"}
    if not rows:
        summary["reason"] = f"no gw{{n}}-advice.json in {reports}/"
    return rows, summary


def main(reports: Path = REPORTS) -> None:
    """Read the season's banked runs and print a ``WALK_HITS_GW`` line per
    week and the ``WALK_HITS`` summary."""
    rows, summary = read_season(reports)
    for row in rows:
        print(f"WALK_HITS_GW {json.dumps(row)}")
    print(f"WALK_HITS {json.dumps(summary)}")


if __name__ == "__main__":
    main()
