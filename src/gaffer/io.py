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
    """
    from gaffer.data import store

    dest = store.DATA_DIR / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_rel = f"{rel}.{os.getpid()}.tmp"
    tmp = store.DATA_DIR / tmp_rel
    try:
        store.save(frame, tmp_rel)
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    return dest
