"""The daily availability log: what the news said, stamped with the day."""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.artifacts import AVAILABILITY_COLS
from gaffer.errors import GafferError
from gaffer.snapshot import (SNAPSHOT_COLS, SNAPSHOT_PATH, append_snapshot,
                             load_snapshot_log, next_unfinished_gw, snap_date,
                             snapshot_rows)


def _avail() -> pd.DataFrame:
    """A news-sharpened availability frame, in availability_frame's shape."""
    return pd.DataFrame({
        "code": [1, 2],
        "status": ["d", "a"],
        "chance_of_playing": [50.0, None],
        "injury_type": ["hamstring", None],
        "expected_return_gw": [4.0, None],
        "p_start_hint": [0.4, None],
        "source": ["ffs", None],
        "fetched_at": ["2026-08-30T09:00:00+00:00", None]})


def _events() -> pd.DataFrame:
    return pd.DataFrame({"gw": [1, 2, 3], "finished": [True, False, False]})


def test_the_log_columns_are_the_availability_columns_stamped():
    """The log reuses artifacts' column contract rather than restating it, so
    a column added to the availability frame lands here for free."""
    assert SNAPSHOT_COLS == ["season", "gw", "snap_date"] + AVAILABILITY_COLS


def test_the_snapshot_gameweek_is_the_first_unfinished_one():
    """``is_next`` goes false in the hours a gameweek is being played, and a
    snapshot taken then still belongs to that week's news cycle."""
    assert next_unfinished_gw(_events()) == 2


def test_a_finished_season_has_no_gameweek_to_snapshot():
    with pytest.raises(GafferError):
        next_unfinished_gw(pd.DataFrame({"gw": [1], "finished": [True]}))


def test_the_rows_carry_the_season_the_gameweek_and_the_day():
    rows = snapshot_rows(_avail(), gw=2, season="2026-27", day="2026-08-30")
    assert list(rows.columns) == SNAPSHOT_COLS
    assert set(rows["season"]) == {"2026-27"}
    assert set(rows["gw"]) == {2}
    assert set(rows["snap_date"]) == {"2026-08-30"}
    assert sorted(rows["code"]) == [1, 2]
    assert rows.set_index("code").loc[1, "injury_type"] == "hamstring"


def test_a_flags_only_frame_still_writes_the_full_schema():
    """News off, or every source down: the log keeps one shape all season, so
    the corrector reads one table rather than a union of weekly shapes."""
    flags = pd.DataFrame({"code": [1], "status": ["a"],
                          "chance_of_playing": [None]})
    rows = snapshot_rows(flags, gw=2, season="2026-27", day="2026-08-30")
    assert list(rows.columns) == SNAPSHOT_COLS
    assert rows["source"].isna().all()
    assert rows["p_start_hint"].isna().all()


def test_the_day_is_utc_and_dashed():
    day = snap_date()
    assert len(day) == 10 and day[4] == "-" and day[7] == "-"


def test_an_absent_log_reads_as_an_empty_frame(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    out = load_snapshot_log()
    assert out.empty
    assert list(out.columns) == SNAPSHOT_COLS


def test_the_first_write_creates_the_log(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    rows = snapshot_rows(_avail(), gw=2, season="2026-27", day="2026-08-30")
    assert append_snapshot(rows) == 2
    assert (tmp_path / SNAPSHOT_PATH).exists()
    assert len(load_snapshot_log()) == 2


def test_a_second_run_the_same_day_replaces_that_days_rows(tmp_path,
                                                           monkeypatch):
    """The job can be re-run by hand, and a duplicated afternoon would weight
    that day twice in whatever trains on this log. The later run wins: it is
    the news that stood at the end of the day."""
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    append_snapshot(snapshot_rows(_avail(), gw=2, season="2026-27",
                                  day="2026-08-30"))
    later = _avail()
    later.loc[0, "status"] = "i"
    append_snapshot(snapshot_rows(later, gw=2, season="2026-27",
                                  day="2026-08-30"))
    out = load_snapshot_log()
    assert len(out) == 2
    assert set(out["snap_date"]) == {"2026-08-30"}
    assert out.set_index("code").loc[1, "status"] == "i"


def test_a_later_day_appends_rather_than_replaces(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    append_snapshot(snapshot_rows(_avail(), gw=2, season="2026-27",
                                  day="2026-08-30"))
    append_snapshot(snapshot_rows(_avail(), gw=2, season="2026-27",
                                  day="2026-08-31"))
    out = load_snapshot_log()
    assert len(out) == 4
    assert sorted(set(out["snap_date"])) == ["2026-08-30", "2026-08-31"]
