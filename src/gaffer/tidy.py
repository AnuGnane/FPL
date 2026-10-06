"""``gaffer tidy`` — the three kinds of file that pile up and are safe to lose.

Spec §2.7 (specs/2026-09-01-gaffer-v12-program-design.md).

Measured on the real tree the day this shipped: 33 files matching
``data/live/backtest_log_*.parquet``, 28 of them paired with a
``reports/v7b_<tag>.json``, five orphans totalling **54 KB**. That is the whole
prize, and it is written here so nobody mistakes this for a disk-space tool.
Nothing under ``data/raw/`` is swept, and v19h §1 closed the question for
good rather than leaving it a residual a fourth reader would reopen. The
timestamped API snapshots are already pruned by their own writer:
``api/client.py:80`` keeps the newest ``KEEP_DUMPS`` (20) per FPL kind on
every write, so bootstrap, fixtures and the entry sit at 20 apiece and a
keep-newest-N target here would find nothing to delete. The ``odds-*`` and
``ags-*`` snapshots are the other and much larger half, and they are a
corpus, not output: ``data/odds.py:663`` keeps them until a season of them
can fit the anytime-scorer weight that is a bare prior today, so a sweep
would delete the only training set that weight will ever have. The scrape
cache under ``data/raw/news/`` stays out of scope for §2.7's original
reason. A sweep there would delete a corpus or nothing, and widening a
delete command past its spec is the most expensive kind of helpfulness
available here.

Four exclusions, each with a named reader:

* ``data/live/backtest_log.parquet`` (no tag) is written by
  ``backtest.run_backtest`` and read by ``/api/history``;
* only ``backtest_log_v7b_*`` is swept, because ``scripts/v7b_replay.py`` is
  the only writer that pairs a log with a report. ``scripts/s2_replay.py``
  writes ``backtest_log_s2_<mode>.parquet`` and no report at all;
* ``logs/advise.log`` is ``/api/health``'s launchd line;
* the availability, field EO, price and presser logs are the corpus, not
  output.

The third kind, from the holiday's F-2 (ROADMAP candidate 7): the frozen EP
tables under ``reports/projections/`` that a banked grade has already passed
over. Their one reader is ``artifacts.latest_projection_before``, called by
``review.grade_gw``, and a grade is only taken of a finished week
(``run_review`` refuses the rest), so every snapshot that week will ever have
already exists when the ledger row names one. Once the siblings are gone a
``gaffer review --gw N`` re-grade can only select the named one again; if the
advice payload has been pruned by then it is flagged ``post_deadline``, where
without the sweep the re-grade would have named a newer, later snapshot. The
named one stays so the row can still be re-checked. A week with no
banked row, a row naming no snapshot, or a row with no ``season`` key (the
v19h legacy shape, rewritten by the next ``append_ledger``) keeps everything:
choosing for Review before Review has chosen is the call ``artifacts``'
``PROJECTIONS`` note refuses to make, and it is refused here too. Measured at
168 KB the day the GUIDE named it, so this is order, not disk space.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

LIVE = Path("data/live")
REPORTS = Path("reports")
LOGS = Path("logs")

BACKTEST_GLOB = "backtest_log_v7b_*.parquet"
KEEP_LOGS = {"advise.log"}
"""Log files that are never candidates, whatever their age."""

PROJECTIONS = REPORTS / "projections"
LEDGER = REPORTS / "decision_ledger.json"
"""``artifacts.PROJECTIONS`` and ``review.ledger_path()``, spelled out here
the way ``LIVE`` and ``REPORTS`` are, so the sweep stays relative to the
working directory a test ``chdir``s into and ``tidy`` pulls in neither
module."""

SNAPSHOT_NAME = re.compile(
    r"^(?P<season>.+)-gw(?P<gw>\d+)-(?P<stamp>\d{8}T\d{6}Z)\.parquet$")
"""``artifacts.projection_path``'s name. A ``.parquet`` file it did not
write is never a candidate; ``io.atomic_path``'s ``.tmp`` temp never reaches
the glob at all."""


def _report_for(path: Path) -> Path:
    tag = path.name.removeprefix("backtest_log_").removesuffix(".parquet")
    return REPORTS / f"{tag}.json"


def _graded_stamps() -> dict[tuple[str, int], str]:
    """``{(season, gw): stamp}`` for every banked grade that names a snapshot.

    Read off the file rather than through ``review.load_ledger``, which keeps
    the season in force only: a past season's superseded snapshots are as
    dead as this one's. A row without ``season`` is left out rather than read
    as the current season, because that would need the config and a wrong
    guess here deletes. A ledger that will not parse names nothing.
    """
    try:
        payload = json.loads(LEDGER.read_text())
    except (OSError, ValueError):
        return {}
    rows = payload.get("gws") if isinstance(payload, dict) else payload
    out = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        season, gw = row.get("season"), row.get("gw")
        stamp = row.get("projection_snapshot")
        if not season or gw is None or not stamp:
            continue
        try:
            out[(str(season), int(gw))] = str(stamp)
        except (TypeError, ValueError):
            continue
    return out


def superseded_projections() -> list[Path]:
    """Snapshots of a graded week other than the one its grade names.

    Only when the named snapshot is still on disk: a row pointing at a file
    that has gone is a row whose week is already past re-checking, and
    deleting its siblings too would leave a later ``gaffer review --gw`` with
    nothing at all to read.
    """
    if not PROJECTIONS.is_dir():
        return []
    graded = _graded_stamps()
    weeks: dict[tuple[str, int], list[tuple[str, Path]]] = {}
    for path in PROJECTIONS.glob("*.parquet"):
        match = SNAPSHOT_NAME.match(path.name)
        if match is None or not path.is_file():
            continue
        key = (match["season"], int(match["gw"]))
        weeks.setdefault(key, []).append((match["stamp"], path))
    out = []
    for key, snaps in weeks.items():
        named = graded.get(key)
        if named is None or named not in {stamp for stamp, _ in snaps}:
            continue
        out += [path for stamp, path in snaps if stamp != named]
    return sorted(out)


def candidates(older_than: int = 30) -> dict[str, list[Path]]:
    """``{"backtests": [...], "logs": [...], "projections": [...]}`` — what
    ``--apply`` would delete.

    ``older_than`` applies to ``logs/`` alone. An orphaned backtest log is
    orphaned whatever its age: the report it would have been paired with is
    never going to appear.

    Raises when ``logs/`` is absent, rather than reporting nothing to tidy. A
    glob over a directory that does not exist returns an empty list, which
    reads identically to "swept and clean" — and the way to be missing
    ``logs/`` is to run this from the wrong directory, which is exactly when a
    false all-clear is worst. ``data/live/`` is not checked the same way: a
    clone that has never run a replay legitimately has no such directory,
    while ``logs/`` is created by the first command that writes one.

    A negative ``older_than`` raises too: a cutoff in the future makes every
    log a candidate, including the ones being appended to right now.
    """
    if older_than < 0:
        raise ValueError(
            f"--older-than must not be negative (got {older_than}): a cutoff "
            f"in the future selects every log, including today's")
    if not LOGS.is_dir():
        raise FileNotFoundError(
            f"{LOGS}/ does not exist — run `gaffer tidy` from the project "
            f"root. Reporting nothing to tidy from the wrong directory would "
            f"look exactly like a tree that is already clean")
    backtests = [p for p in sorted(LIVE.glob(BACKTEST_GLOB))
                 if not _report_for(p).exists()]
    cutoff = time.time() - older_than * 86400
    logs = [p for p in sorted(LOGS.glob("*.log"))
            if p.name not in KEEP_LOGS and p.stat().st_mtime < cutoff]
    return {"backtests": backtests, "logs": logs,
            "projections": superseded_projections()}


def _size(paths) -> int:
    return sum(p.stat().st_size for p in paths)


def run_tidy(*, apply: bool = False, older_than: int = 30) -> dict:
    """Print what would go; delete it only under ``apply``."""
    found = candidates(older_than)
    every = found["backtests"] + found["logs"] + found["projections"]
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
