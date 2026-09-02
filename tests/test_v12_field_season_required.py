"""Which season's ownership is on the page.

`element` is a season-scoped id — FIELD_EO_COLS says so — so a log holding two
seasons holds two different footballers under one number. The reader used to
take `season` as an optional keyword, which meant a caller could forget it and
get "whatever gameweek number is largest", which after a rollover is last
season's final week.

Required, now. The failure this prevents is silent: every ownership figure on
the players page would be a real number about the wrong player, and nothing on
the page could say so.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.data import store
from gaffer.data.field import FIELD_EO_COLS, latest_field_eo, load_field_eo


@pytest.fixture()
def two_seasons(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    store.save(pd.DataFrame([
        {"season": "2025-26", "gw": 38, "snap_date": "2026-05-24",
         "element": 411, "eo": 90.0, "se": 1.0, "n": 300},
        {"season": "2025-26", "gw": 38, "snap_date": "2026-05-24",
         "element": 7, "eo": 55.0, "se": 2.0, "n": 300},
        {"season": "2026-27", "gw": 2, "snap_date": "2026-08-31",
         "element": 411, "eo": 10.0, "se": 1.0, "n": 300},
    ], columns=FIELD_EO_COLS), "live/field_eo_log.parquet")
    return tmp_path


def test_the_reader_returns_only_the_named_seasons_rows(two_seasons):
    """The spec's own test: two seasons, overlapping element ids, one answer."""
    assert set(latest_field_eo(season="2026-27")) == {411}
    assert latest_field_eo(season="2026-27")[411]["eo"] == 10.0


def test_the_other_season_is_still_readable_and_is_not_the_default(two_seasons):
    table = latest_field_eo(season="2025-26")
    assert set(table) == {411, 7}
    assert table[411]["eo"] == 90.0


def test_the_larger_gameweek_number_does_not_win(two_seasons):
    """The whole bug in one line: 38 > 2, and 38 is last season's."""
    assert latest_field_eo(season="2026-27")[411]["gw"] == 2


def test_the_keyword_cannot_be_omitted(two_seasons):
    with pytest.raises(TypeError):
        latest_field_eo()


def test_a_season_with_no_rows_is_empty_and_never_falls_back(two_seasons):
    """No fallback, restated as a test: "whatever is newest" is exactly the
    answer this keyword exists to prevent."""
    assert latest_field_eo(season="2027-28") == {}


def test_the_raw_reader_filters_too(two_seasons):
    assert len(load_field_eo()) == 3
    assert len(load_field_eo(season="2026-27")) == 1
    assert len(load_field_eo(season="2027-28")) == 0


def test_a_log_written_before_the_season_column_reads_empty_for_any_season(
        tmp_path, monkeypatch):
    """The older-log case. Empty rather than everything, for the same reason
    there is no fallback: a log that cannot say which season it is about
    cannot answer a question about one season."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    store.save(pd.DataFrame([
        {"gw": 2, "snap_date": "2026-08-31", "element": 411,
         "eo": 10.0, "se": 1.0, "n": 300}]), "live/field_eo_log.parquet")
    assert load_field_eo(season="2026-27").empty
    assert latest_field_eo(season="2026-27") == {}


def test_no_log_at_all_is_empty_rather_than_a_raise(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert latest_field_eo(season="2026-27") == {}
    assert load_field_eo(season="2026-27").empty
