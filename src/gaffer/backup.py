"""``gaffer backup`` — one tar of the things no command can rebuild.

Spec §2.1 (specs/2026-09-01-gaffer-v12-program-design.md), with one correction
made deliberately and recorded here rather than in a commit nobody re-reads.

The spec's set is ``data/live/``, ``reports/`` and ``models/``, on the grounds
that the field EO samples live in ``data/live/field_eo_log.parquet``. The
*log* does. The sampled *squads* do not: ``data.field.save_field_sample``
writes ``data/raw/field/<season>/gw<N>.json``, and ``data/field.py:43`` says
why they sit under ``raw/`` — they are API payloads, not derived frames. A
past gameweek's top-10k picks cannot be fetched again from anywhere, which
makes them and ``data/raw/tier_eo/`` the only genuinely irreplaceable bytes in
the tree. They are in the archive.

What is deliberately **out**, and what rebuilds it:

* ``data/history/`` (3 MB) — ``gaffer build-history``
* ``data/raw/understat/`` (12 MB) — ``gaffer understat``, slowly
* ``data/raw/vaastav/`` (24 MB) — a download
* ``data/raw/news/`` (67 MB) — a scrape cache. The *derived* corpus that
  matters, ``data/live/availability_log.parquet`` and
  ``live/presser_log.parquet``, is inside the set.
* the timestamped API snapshots under ``data/raw/`` (~34 MB) — a record of
  calls made, not a record of anything the tool needs.

That is ~16 MB in and ~140 MB out, so ``keep = 14`` costs a few hundred
megabytes rather than two gigabytes.
"""

from __future__ import annotations

import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

ROOTS = ["data/live", "data/raw/field", "data/raw/tier_eo", "reports",
         "models"]
"""Archived, in this order. A root that does not exist is skipped."""

NAME_GLOB = "gaffer-*.tar.gz"
"""What :func:`prune` is allowed to consider. Never ``*``: the destination may
be a directory the user also keeps their own files in, and a retention rule
that deletes by "everything here" is a data loss with a schedule."""


def archive_name(now: datetime | None = None) -> str:
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M")
    return f"gaffer-{stamp}.tar.gz"


def run_backup(*, to: Path | str, rsync: str | None = None,
               keep: int = 14, now: datetime | None = None) -> Path | None:
    """Write one archive, optionally copy it, prune the local directory.

    ``None`` when there was nothing to archive at all — an empty tar looks
    exactly like a successful backup and restores to nothing, which is the
    worst of the available outcomes.
    """
    roots = [Path(r) for r in ROOTS if Path(r).exists()]
    if not roots:
        print("backup: nothing to archive — no data/, reports/ or models/")
        return None
    dest = Path(to)
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / archive_name(now)
    # Written to its final name rather than through gaffer.io.atomic_write:
    # the archive is a new file every minute, so there is no previous version
    # for a torn write to destroy, and streaming a tarball through a temp
    # would double the peak disk for no gain.
    with tarfile.open(path, "w:gz") as tar:
        for root in roots:
            tar.add(root, arcname=str(root))
    if rsync:
        result = subprocess.run(["rsync", "-a", str(path), rsync],
                                capture_output=True, text=True)
        if result.returncode != 0:
            # Never fatal. The local archive exists and is the thing that
            # matters; raising here would tell the user nothing was backed up,
            # which would be false.
            print(f"backup: rsync to {rsync} failed "
                  f"({result.stderr.strip() or result.returncode}) — the "
                  f"local archive at {path} is written")
    prune(dest, keep=keep)
    return path


def prune(dest: Path | str, *, keep: int = 14) -> list[Path]:
    """Delete all but the newest ``keep`` archives **in the local directory**.

    Never across ``--rsync``: that is a path on a machine this tool does not
    own, reached over a protocol with no undo, and a retention rule that
    crossed it would be deleting somebody else's files on a timer.

    ``keep <= 0`` keeps everything. There is no legitimate reason to ask this
    command to keep nothing, and a misread config key should not empty a
    backup directory.
    """
    if keep <= 0:
        return []
    found = sorted(Path(dest).glob(NAME_GLOB), key=lambda p: p.name)
    doomed = found[:-keep] if len(found) > keep else []
    for path in doomed:
        path.unlink(missing_ok=True)
    return doomed


def latest_backup(dest: Path | str) -> dict | None:
    """``{"path", "modified_at", "bytes"}`` for the newest archive, or None.

    ``None`` is the Health line's "never". Never a zero-byte dict: a size of
    zero would render as a backup that happened and was empty.
    """
    found = sorted(Path(dest).glob(NAME_GLOB), key=lambda p: p.stat().st_mtime)
    if not found:
        return None
    newest = found[-1]
    stat = newest.stat()
    return {"path": str(newest),
            "modified_at": datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc).isoformat(),
            "bytes": int(stat.st_size)}


def backup_dir(configured: str = "") -> Path:
    """``[backup] dir``, or ``~/gaffer-backups``. Expanded, never relative to
    the project: a backup inside the tree it is backing up is not a backup."""
    return Path(configured).expanduser() if configured \
        else Path.home() / "gaffer-backups"
