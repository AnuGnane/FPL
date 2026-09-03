"""v12 W5 §6.4 degradation — every way the projections directory can be wrong.

Spec §1: missing file, malformed file, empty result, partial result — each a
named behaviour, none a crash.
"""
from __future__ import annotations

import pandas as pd
import pytest

from gaffer.artifacts import (PROJECTIONS, latest_projection_before,
                              projection_snapshots, save_projection_snapshot)

DEADLINE = "2026-09-04T17:30:00+00:00"


@pytest.fixture(autouse=True)
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_no_directory_at_all_is_an_empty_list(here):
    assert projection_snapshots("2026-27", 5) == []
    assert latest_projection_before("2026-27", 5, DEADLINE) is None


def test_an_empty_directory_is_an_empty_list(here):
    PROJECTIONS.mkdir(parents=True)
    assert projection_snapshots("2026-27", 5) == []


def test_a_file_that_is_not_a_snapshot_is_ignored(here):
    PROJECTIONS.mkdir(parents=True)
    (PROJECTIONS / "notes.txt").write_text("hello")
    (PROJECTIONS / "2026-27-gw5.parquet").write_bytes(b"")
    assert projection_snapshots("2026-27", 5) == []


def test_a_snapshot_that_will_not_parse_is_still_listed_and_named(here):
    """Listing is a filename operation and must not read the file: a corrupt
    parquet is the caller's problem to report, with a path to point at."""
    PROJECTIONS.mkdir(parents=True)
    (PROJECTIONS / "2026-27-gw5-20260901T090000Z.parquet").write_bytes(b"junk")
    snaps = projection_snapshots("2026-27", 5)
    assert len(snaps) == 1
    with pytest.raises(Exception):
        pd.read_parquet(snaps[0].path)


def test_an_empty_season_writes_nothing_and_says_so(here, capsys):
    out = save_projection_snapshot(pd.DataFrame({"code": [1]}), 5,
                                   "2026-09-01T09:00:00+00:00", "")
    assert out is None
    assert "current_season" in capsys.readouterr().out
    assert not PROJECTIONS.exists()


def test_an_unwritable_directory_is_a_line_and_not_a_crash(here, capsys,
                                                           monkeypatch):
    monkeypatch.setattr(pd.DataFrame, "to_parquet",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("full")))
    out = save_projection_snapshot(pd.DataFrame({"code": [1]}), 5,
                                   "2026-09-01T09:00:00+00:00", "2026-27")
    assert out is None
    assert "no snapshot kept" in capsys.readouterr().out


def test_an_unparseable_generated_at_still_writes_under_now(here):
    path = save_projection_snapshot(pd.DataFrame({"code": [1]}), 5,
                                    "not a date", "2026-27")
    assert path is not None and path.exists()


def test_an_empty_pool_is_written_rather_than_skipped(here):
    """"The solver had no candidates" is a fact worth freezing. A skipped
    snapshot would read later as "no run happened"."""
    path = save_projection_snapshot(pd.DataFrame({"code": []}), 5,
                                    "2026-09-01T09:00:00+00:00", "2026-27")
    assert path is not None
    assert len(pd.read_parquet(path)) == 0
