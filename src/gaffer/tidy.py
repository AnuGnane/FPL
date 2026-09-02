"""``gaffer tidy`` — the two kinds of file that pile up and are safe to lose.

Spec §2.7 (specs/2026-09-01-gaffer-v12-program-design.md).

Measured on the real tree the day this shipped: 33 files matching
``data/live/backtest_log_*.parquet``, 28 of them paired with a
``reports/v7b_<tag>.json``, five orphans totalling **54 KB**. That is the whole
prize, and it is written here so nobody mistakes this for a disk-space tool.
The 150 MB under ``data/raw/`` — 67 MB of scrape cache, 34 MB of timestamped
API snapshots nothing prunes — is out of §2.7's scope, deliberately, and is
recorded as a residual instead. Widening a delete command past its spec is the
most expensive kind of helpfulness available here.

Four exclusions, each with a named reader:

* ``data/live/backtest_log.parquet`` (no tag) is written by
  ``backtest.run_backtest`` and read by ``/api/history``;
* only ``backtest_log_v7b_*`` is swept, because ``scripts/v7b_replay.py`` is
  the only writer that pairs a log with a report. ``scripts/s2_replay.py``
  writes ``backtest_log_s2_<mode>.parquet`` and no report at all;
* ``logs/advise.log`` is ``/api/health``'s launchd line;
* the availability, field EO, price and presser logs are the corpus, not
  output.
"""

from __future__ import annotations

import time
from pathlib import Path

LIVE = Path("data/live")
REPORTS = Path("reports")
LOGS = Path("logs")

BACKTEST_GLOB = "backtest_log_v7b_*.parquet"
KEEP_LOGS = {"advise.log"}
"""Log files that are never candidates, whatever their age."""


def _report_for(path: Path) -> Path:
    tag = path.name.removeprefix("backtest_log_").removesuffix(".parquet")
    return REPORTS / f"{tag}.json"


def candidates(older_than: int = 30) -> dict[str, list[Path]]:
    """``{"backtests": [...], "logs": [...]}`` — what ``--apply`` would delete.

    ``older_than`` applies to ``logs/`` alone. An orphaned backtest log is
    orphaned whatever its age: the report it would have been paired with is
    never going to appear.
    """
    backtests = [p for p in sorted(LIVE.glob(BACKTEST_GLOB))
                 if not _report_for(p).exists()]
    cutoff = time.time() - older_than * 86400
    logs = [p for p in sorted(LOGS.glob("*.log"))
            if p.name not in KEEP_LOGS and p.stat().st_mtime < cutoff]
    return {"backtests": backtests, "logs": logs}


def _size(paths) -> int:
    return sum(p.stat().st_size for p in paths)


def run_tidy(*, apply: bool = False, older_than: int = 30) -> dict:
    """Print what would go; delete it only under ``apply``."""
    found = candidates(older_than)
    every = found["backtests"] + found["logs"]
    if not every:
        print("nothing to tidy")
        return found
    total = _size(every)
    for path in every:
        print(f"  {path}  ({path.stat().st_size / 1024:.1f} KB)")
    print(f"{len(every)} files, {total / 1024:.1f} KB "
          f"({total / 1e6:.1f} MB)")
    if not apply:
        print("dry run — pass --apply to delete")
        return found
    for path in every:
        path.unlink(missing_ok=True)
    print(f"deleted {len(every)} files")
    return found
