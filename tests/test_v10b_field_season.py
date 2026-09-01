"""``latest_field_eo`` can be told which season it is reading.

The log is keyed ``(season, gw, snap_date, element)`` and the reader consults
three of those four. ``field.py:225`` takes ``int(frame["gw"].max())`` over the
whole file, which is right for as long as the file holds one season and wrong
the moment it holds two: in August 2027 the newest rows are GW2 of 2027-28 and
the largest ``gw`` is 38, from the season before.

That is not a display bug. ``FIELD_EO_COLS``' own docstring says why
(``field.py:49-52``): *"a pick names a season-scoped element"*. Element 411 in
2026-27 and element 411 in 2027-28 are two different footballers, so a stale
season does not produce a missing number — it produces a **confident number
about the wrong player**, which is the exact failure v10b §Gates asks to be
guarded against.

The keyword defaults to ``None`` and ``None`` is today's behaviour to the
byte, so ``routers/players.py`` is not touched by this cycle and does not need
re-testing. The explorer's own switch is a residual, recorded in the README.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.data import store
from gaffer.data.field import FIELD_EO_COLS, latest_field_eo


@pytest.fixture()
def two_seasons(tmp_path, monkeypatch):
    """A log spanning a season boundary, with one element reused across it."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    rows = pd.DataFrame([
        # last season, late: the largest gw in the file
        {"season": "2026-27", "gw": 38, "snap_date": "2027-05-24",
         "element": 411, "eo": 71.0, "se": 2.0, "n": 300},
        # this season, early: the newest rows, and a *different* player at 411
        {"season": "2027-28", "gw": 2, "snap_date": "2027-08-22",
         "element": 411, "eo": 12.0, "se": 1.5, "n": 300},
    ], columns=FIELD_EO_COLS)
    store.save(rows, "live/field_eo_log.parquet")
    return tmp_path


def test_without_a_season_it_reads_the_largest_gameweek_as_it_always_has(
        two_seasons):
    """The degradation direction, pinned first. ``routers/players.py`` calls
    this with no arguments and must get exactly what it got yesterday —
    including, for now, the wrong answer across a season boundary."""
    assert latest_field_eo()[411]["eo"] == 71.0


def test_naming_the_season_reads_that_seasons_newest_scrape(two_seasons):
    """The fix. 2027-28 has one gameweek in the file and it is GW2."""
    table = latest_field_eo(season="2027-28")
    assert table[411]["eo"] == 12.0
    assert table[411]["gw"] == 2


def test_naming_the_season_and_the_gameweek_together(two_seasons):
    assert latest_field_eo(gw=38, season="2026-27")[411]["eo"] == 71.0


def test_a_season_with_no_rows_is_an_empty_dict_not_a_fallback(two_seasons):
    """The one temptation worth refusing. Falling back to "whatever is newest"
    when the named season is absent would put us straight back into the
    wrong-player failure, on the pre-season Friday when the new log is empty
    and the old one is full."""
    assert latest_field_eo(season="2028-29") == {}


def test_a_log_with_no_season_column_still_answers_the_unseasoned_call(
        tmp_path, monkeypatch):
    """A log banked before the column existed. ``None`` must still work; a
    named season over such a log is an empty dict, not a KeyError."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    store.save(pd.DataFrame([{"gw": 2, "snap_date": "2026-08-31",
                              "element": 7, "eo": 40.0, "se": 1.0, "n": 300}]),
               "live/field_eo_log.parquet")
    assert latest_field_eo()[7]["eo"] == 40.0
    assert latest_field_eo(season="2026-27") == {}


def test_every_failure_is_still_an_empty_dict(tmp_path, monkeypatch):
    """``field.py:210-212``'s standing contract, unchanged by the keyword."""
    monkeypatch.chdir(tmp_path)
    assert latest_field_eo(season="2026-27") == {}
