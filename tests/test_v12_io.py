"""One atomic write, and the three shapes of caller it has to fit.

Twenty sites in this tree write a file by putting it beside the destination and
renaming it. They fall into three families and the helper serves all three,
because a helper that only served the JSON one would leave the parquet writers
open-coding the same rename — which is how six copies became twenty.

The pid in the temp name is not decoration. Eight sites carry the same comment
explaining it: two writers sharing one ``.tmp`` each unlink the other's file in
their ``finally``, and the loser's ``os.replace`` then raises FileNotFoundError.
A nightly launchd job and a hand-run command are exactly two writers.

The ``finally`` is not decoration either. ``understat.py`` and
``chip_scenarios.py`` were written without one, so a write that raised between
the temp and the rename left the temp file behind for ever — permanently, in
understat's case, whose cache directory is never swept.
"""

from __future__ import annotations

import os

import pandas as pd
import pytest

from gaffer import io as gio


def test_text_lands_whole(tmp_path):
    path = tmp_path / "out.json"
    gio.atomic_write(path, '{"a": 1}')
    assert path.read_text() == '{"a": 1}'


def test_bytes_land_whole(tmp_path):
    """``routers/assets.py`` banks images; a str-only helper would have left
    that one site open-coded."""
    path = tmp_path / "shirt.png"
    gio.atomic_write(path, b"\x89PNG\r\n")
    assert path.read_bytes() == b"\x89PNG\r\n"


def test_the_parent_directory_is_created(tmp_path):
    path = tmp_path / "deep" / "deeper" / "out.json"
    gio.atomic_write(path, "{}")
    assert path.read_text() == "{}"


def test_the_temp_name_carries_the_pid(tmp_path):
    """Asserted on the name the context manager yields rather than on a
    leftover file, because there is never a leftover file to look at."""
    seen = []
    with gio.atomic_path(tmp_path / "out.json") as tmp:
        seen.append(tmp.name)
        tmp.write_text("{}")
    assert str(os.getpid()) in seen[0]
    assert seen[0].endswith(".tmp")
    assert seen[0].startswith("out.json.")


def test_no_temp_file_survives_a_successful_write(tmp_path):
    gio.atomic_write(tmp_path / "out.json", "{}")
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]


def test_no_temp_file_survives_a_failed_write(tmp_path):
    """The ``finally`` two of the twenty sites never had."""
    with pytest.raises(ValueError):
        with gio.atomic_path(tmp_path / "out.json") as tmp:
            tmp.write_text("half")
            raise ValueError("boom")
    assert list(tmp_path.iterdir()) == []


def test_a_failed_write_leaves_the_previous_file_exactly_as_it_was(tmp_path):
    """The whole point of the idiom, asserted once so the twenty call sites do
    not each have to."""
    path = tmp_path / "out.json"
    path.write_text("the old one")
    with pytest.raises(ValueError):
        with gio.atomic_path(path) as tmp:
            tmp.write_text("the new one")
            raise ValueError("boom")
    assert path.read_text() == "the old one"


def test_two_writers_do_not_share_a_temp_name(tmp_path, monkeypatch):
    """The failure the pid exists to prevent, reproduced by moving the pid."""
    names = set()
    for pid in (111, 222):
        monkeypatch.setattr(gio.os, "getpid", lambda pid=pid: pid)
        with gio.atomic_path(tmp_path / "out.json") as tmp:
            names.add(tmp.name)
            tmp.write_text("{}")
    assert len(names) == 2


def test_a_frame_lands_under_the_store_directory(tmp_path, monkeypatch):
    """The parquet family. ``store.DATA_DIR`` is read at call time, not bound
    at import, because four call sites say so in their docstrings: a test that
    redirects the data directory must redirect both paths together."""
    from gaffer.data import store

    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    gio.atomic_save(pd.DataFrame({"a": [1, 2]}), "live/thing.parquet")
    assert len(store.load("live/thing.parquet")) == 2


def test_a_failed_frame_write_leaves_the_banked_file_intact(tmp_path,
                                                            monkeypatch):
    """The reason the parquet writers rewrite through a temp at all: parquet
    has no append, so every daily write re-emits the whole log, and a write
    that died in place would cost a season to save an afternoon."""
    from gaffer.data import store

    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    gio.atomic_save(pd.DataFrame({"a": [1, 2]}), "live/thing.parquet")

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(store, "save", boom)
    with pytest.raises(OSError):
        gio.atomic_save(pd.DataFrame({"a": [9]}), "live/thing.parquet")
    assert len(store.load("live/thing.parquet")) == 2
    assert not list(tmp_path.glob("live/*.tmp"))
