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

from gaffer import io
from gaffer.data import store

ROOTS = ["live", "raw/field", "raw/tier_eo"]
"""Archived under ``store.DATA_DIR``, in this order, plus :data:`TREE_ROOTS`.

Read through ``store.DATA_DIR`` rather than as a literal ``data/live``:
``store.DATA_DIR`` is itself relative to the process's cwd (``Path("data")``),
so the indirection does not make this cwd-independent — what it buys is that a
test can point the whole module at a fixture tree by redirecting the one
attribute, and that this module reads the data tree from the module that owns
it rather than guessing a second time. A root that does not exist is skipped;
a tree with *no* root at all writes nothing."""

TREE_ROOTS = ["reports", "models"]
"""The two archived roots that are not under the data tree. Project-relative,
because that is where ``artifacts.REPORTS`` and the trainer write them."""

NAME_GLOB = "gaffer-*.tar.gz"
"""What :func:`prune` is allowed to consider. Never ``*``: the destination may
be a directory the user also keeps their own files in, and a retention rule
that deletes by "everything here" is a data loss with a schedule."""


def archive_name(now: datetime | None = None) -> str:
    """``gaffer-<YYYYmmdd-HHMMSS>.tar.gz``, in UTC.

    Seconds, not minutes: two runs inside one minute — a scheduled 23:45 job
    and a hand ``gaffer backup`` while checking on it — would otherwise pick
    the same name, and the second would overwrite the first. UTC, so the name
    does not go backwards over a DST fold and the sort order is the write
    order.
    """
    return "gaffer-{}.tar.gz".format(
        (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S"))


def archived_roots() -> list[tuple[Path, str]]:
    """The roots that exist as ``(path on disk, name inside the tar)``.

    In :data:`ROOTS` then :data:`TREE_ROOTS` order. The arcname is written out
    explicitly — ``data/<r>`` and ``<r>`` — rather than derived from the path,
    so that the layout inside the archive is the project's layout whatever
    ``store.DATA_DIR`` happens to be. Derived from the path, a redirected
    ``DATA_DIR`` (a test fixture, or a tree moved onto another volume) would
    put an absolute or foreign prefix in the tar, and the restore instructions
    in the README — extract at the project root — would silently be wrong.
    """
    every = [(store.DATA_DIR / r, f"data/{r}") for r in ROOTS] + \
        [(Path(r), r) for r in TREE_ROOTS]
    return [(p, arc) for p, arc in every if p.exists()]


def run_backup(*, to: Path | str, rsync: str | None = None,
               keep: int = 14, now: datetime | None = None) -> Path | None:
    """Write one archive, optionally copy it, prune the local directory.

    Never raises on a write that fails: it returns ``None`` with a message.
    ``None`` when there was nothing to archive at all — an empty tar looks
    exactly like a successful backup and restores to nothing, which is the
    worst of the available outcomes — and ``None`` again when the write itself
    failed, with the half-written file removed rather than left where the next
    run's ``prune`` would count it as an archive.
    """
    roots = archived_roots()
    if not roots:
        print("backup: nothing to archive — no data/, reports/ or models/")
        return None
    dest = Path(to)
    dest.mkdir(parents=True, exist_ok=True)
    # Stamped once. Two calls a second apart would name the part file and the
    # archive differently, and the rename would then be a move rather than the
    # in-place publish it is meant to be.
    name = archive_name(now)
    path = dest / name
    # Written to a temp sibling and renamed, rather than straight to the final
    # name: a tar interrupted by a full disk or a Ctrl-C leaves a truncated
    # .tar.gz that matches NAME_GLOB, which makes it the newest "archive" the
    # Health line reports and the newest one `prune` keeps. `io.atomic_path`
    # is the tree's one copy of that idiom; its temp is
    # `gaffer-….tar.gz.<pid>.tmp`, which matches neither NAME_GLOB nor
    # anything `latest_backup` looks at, and its `finally` removes the temp on
    # any exit — including the KeyboardInterrupt that a hand-run `gaffer
    # backup` is most likely to die of.
    try:
        with io.atomic_path(path) as part:
            # dereference=True: `models/` and `reports/` are ordinary
            # directories here, but a user who has symlinked one onto another
            # volume — which is exactly what somebody short of disk does —
            # would otherwise get an archive of dangling links that restores
            # to nothing. It is not free: a symlink cycle inside an archived
            # root recurses until tarfile runs out of stack or disk, and a
            # large tree symlinked in is archived by value rather than as the
            # one-line link it is on disk.
            with tarfile.open(part, "w:gz", dereference=True) as tar:
                for root, arcname in roots:
                    tar.add(root, arcname=arcname)
    except OSError as exc:
        print(f"backup: failed to write {path} ({exc}) — no archive was "
              f"written, and the previous ones are untouched")
        return None
    if rsync:
        # `--` before the paths: an rsync target is a user-supplied string and
        # one beginning with a dash would otherwise be read as an option.
        result = subprocess.run(["rsync", "-a", "--", str(path), rsync],
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
    # By mtime, like `latest_backup`: the two must agree about which archive
    # is newest, or the one the Health line shows is the one the prune deletes.
    # The name usually orders the same way, and does not when the clock is set
    # back or a file is copied in from elsewhere.
    # The name breaks a tie, because two archives can share an mtime on a
    # filesystem with a coarse clock and `glob` order is the directory's, not
    # anything a reader could predict.
    found = sorted(Path(dest).glob(NAME_GLOB),
                   key=lambda p: (p.stat().st_mtime, p.name))
    doomed = found[:-keep] if len(found) > keep else []
    for path in doomed:
        path.unlink(missing_ok=True)
    return doomed


def latest_backup(dest: Path | str) -> dict | None:
    """``{"path", "modified_at", "bytes"}`` for the newest archive, or None.

    ``None`` is the Health line's "never". Never a zero-byte dict: a size of
    zero would render as a backup that happened and was empty.
    """
    found = sorted(Path(dest).glob(NAME_GLOB),
                   key=lambda p: (p.stat().st_mtime, p.name))
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
