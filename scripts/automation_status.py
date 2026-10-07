"""The next fire time of a launchd plist, for ``install_automation.sh --status``.

launchd answers "is it loaded" (``launchctl list <label>``) but not "when does
it next run": a ``StartCalendarInterval`` job carries no next-fire field. The
installer's ``--status`` flag (holiday F-5) asks this script instead, so the
install box in the ROADMAP can be read off one command rather than by hand
from nine plists. It only reads; it never loads or unloads a job.

launchd reads the calendar keys in the machine's local time, so the answer is
in local time too. A key left out is a wildcard, as in cron; ``Weekday`` 0 and
7 are both Sunday.

Usage::

    .venv/bin/python scripts/automation_status.py scripts/com.gaffer.advise.plist
"""

from __future__ import annotations

import plistlib
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

HORIZON_DAYS = 400
"""How far ahead to look. A leap-day-only schedule could need four years, but
no gaffer plist names a ``Day`` or ``Month``; past this the answer is "never"."""


def _matches_date(entry: dict, day: datetime) -> bool:
    if "Month" in entry and entry["Month"] != day.month:
        return False
    if "Day" in entry and entry["Day"] != day.day:
        return False
    # isoweekday is Monday=1..Sunday=7; launchd counts Sunday as 0 or 7.
    if "Weekday" in entry and entry["Weekday"] % 7 != day.isoweekday() % 7:
        return False
    return True


def next_calendar_fire(entries: list[dict], now: datetime) -> datetime | None:
    """The first minute strictly after ``now`` that any entry names, or None
    when none does within :data:`HORIZON_DAYS`."""
    start = now.replace(second=0, microsecond=0)
    best: datetime | None = None
    for entry in entries:
        hours = [entry["Hour"]] if "Hour" in entry else range(24)
        minutes = [entry["Minute"]] if "Minute" in entry else range(60)
        for offset in range(HORIZON_DAYS):
            day = start.replace(hour=0, minute=0) + timedelta(days=offset)
            if not _matches_date(entry, day):
                continue
            hit = next((day.replace(hour=h, minute=m)
                        for h in hours for m in minutes
                        if day.replace(hour=h, minute=m) > now), None)
            if hit is not None:
                if best is None or hit < best:
                    best = hit
                break
    return best


def describe(plist: dict, now: datetime) -> str:
    """One line for the status table: when the job next fires."""
    calendar = plist.get("StartCalendarInterval")
    if calendar is not None:
        entries = calendar if isinstance(calendar, list) else [calendar]
        nxt = next_calendar_fire(entries, now)
        return nxt.strftime("%a %d %b %H:%M") if nxt else "never"
    if "StartInterval" in plist:
        return f"every {plist['StartInterval']}s"
    if plist.get("RunAtLoad"):
        return "at load only"
    return "no schedule"


def load_plist(path: Path) -> dict:
    """Parse a plist the way launchd does, comments and all.

    ``com.gaffer.core-insights.plist`` quotes ``--refresh`` inside an XML
    comment. CoreFoundation's parser accepts that; expat, under plistlib,
    does not (a comment may not contain ``--``). The comments carry no keys,
    so they are dropped before parsing rather than the plist being edited.
    """
    raw = re.sub(rb"<!--.*?-->", b"", path.read_bytes(), flags=re.DOTALL)
    return plistlib.loads(raw)


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: automation_status.py <plist>", file=sys.stderr)
        return 2
    print(describe(load_plist(Path(argv[0])), datetime.now()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
