"""One atomic write, for the twenty places that were doing it themselves.

Spec §1 and §2.11 (specs/2026-09-01-gaffer-v12-program-design.md). The spec
said six copies; there were twenty, in three families — JSON and text through
``write_text``, parquet through ``store.save``, and raw bytes — and a helper
serving only the first would have left the other two open-coded, which is how
six became twenty.

Two things in here are load-bearing and were arrived at the hard way by the
sites this replaces:

* **the pid in the temp name.** Two writers sharing one ``.tmp`` each unlink
  the other's file in their ``finally``, and the loser's ``os.replace`` then
  raises ``FileNotFoundError``. A nightly launchd job and a hand-run command
  are exactly two writers, and ``data/live/presser_log.parquet`` was written
  without a pid until this change;
* **the ``finally``.** A write that raises between the temp and the rename
  leaves the temp behind for ever otherwise. ``understat.py`` and
  ``chip_scenarios.py`` were both written without one, and understat's cache
  is permanent by design, so its orphans were too.

``os.replace`` is atomic within a directory on POSIX, which is why the temp is
always a *sibling* of the destination and never in ``/tmp``.

Two things the copies this replaces did not all do, stated once here:

* **missing parent directories are created.** Twelve of the migrated call
  sites did their own ``mkdir(parents=True, exist_ok=True)`` first and the
  rest did not; the helper does it, so they all behave alike now. That is the
  one behavioural change against the old copies — a write into a directory
  that does not exist used to raise in some places and now succeeds
  everywhere. ``tests/test_v10b_chip_scenarios.py`` records where that showed;
* **"whole" means crash-atomic, not power-loss durable.** A reader never sees
  a half-written file, and a process that dies mid-write leaves the old
  destination intact. There is no ``fsync`` of the temp or of the directory,
  so a machine that loses power right after the rename may come back with
  either version. Every caller here writes derived data that a refresh can
  regenerate, which is the trade being made.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pandas as pd


@contextmanager
def atomic_path(path: Path | str) -> Iterator[Path]:
    """Yield a sibling temp path; replace ``path`` with it on a clean exit.

    The caller writes to the yielded path however it likes — text, bytes, a
    parquet writer, anything that takes a filename. On a clean exit the temp
    replaces the destination in one step; on any exception the destination is
    left exactly as it was and the temp is removed.

    ``path``'s parent directories are created if they are missing. The rename
    is crash-atomic and not power-loss durable: nothing is ``fsync``ed, so a
    reader never sees a partial file but a machine that loses power just after
    the rename may come back with either version.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.{os.getpid()}.tmp")
    try:
        yield tmp
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)


def atomic_write(path: Path | str, data: str | bytes) -> Path:
    """Write ``data`` whole, or leave what was there untouched."""
    dest = Path(path)
    with atomic_path(dest) as tmp:
        if isinstance(data, bytes):
            tmp.write_bytes(data)
        else:
            tmp.write_text(data)
    return dest


def atomic_save(frame: pd.DataFrame, rel: str) -> Path:
    """``store.save`` a frame at a store-relative path, atomically.

    ``store.DATA_DIR`` is read here rather than bound at import, so a test
    that redirects the data directory redirects the temp and the destination
    together — the trade four of the migrated call sites state in their own
    docstrings.

    The pid-in-the-name and the ``finally`` live in ``atomic_path``; this
    function only has to hand ``store.save`` the temp's *store-relative* name,
    which is what makes it a wrapper rather than a second copy of the idiom.
    """
    from gaffer.data import store

    dest = store.DATA_DIR / rel
    with atomic_path(dest) as tmp:
        store.save(frame, str(tmp.relative_to(store.DATA_DIR)))
    return dest
