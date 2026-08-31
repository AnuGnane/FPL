"""The two field stores: what they hold, and what they refuse to hold.

The sample store is a permanent per-gameweek fact (the precedent is
``fetch_rival_picks_history``); the EO log is the growing instrument
(``snapshot.py``'s append-by-rewrite). The one hard rule across both is
anonymity: an entry id may never reach disk.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from gaffer.data import store
from gaffer.data.field import (FIELD_EO_COLS, FIELD_EO_PATH, RAW_FIELD,
                               append_field_eo, field_eo_rows,
                               field_sample_path, latest_field_eo,
                               load_field_eo, load_field_sample,
                               save_field_sample)

PICKS = [
    [{"element": 7, "position": 1, "multiplier": 2},
     {"element": 8, "position": 12, "multiplier": 0}],
    [{"element": 7, "position": 1, "multiplier": 1},
     {"element": 9, "position": 2, "multiplier": 1}],
]

TABLE = {7: {"eo": 150.0, "se": 3.2, "n": 2},
         9: {"eo": 50.0, "se": 2.1, "n": 2}}


@pytest.fixture()
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    return tmp_path


def test_the_sample_lands_at_the_documented_path(here):
    save_field_sample(PICKS, 3, "2026-27")
    assert field_sample_path("2026-27", 3).is_file()
    assert field_sample_path("2026-27", 3) == RAW_FIELD / "2026-27" / "gw3.json"


def test_the_stored_sample_carries_no_entry_id(here):
    """Spec §6: sample indices replace entry ids, and we keep no register of
    who was sampled. The test greps the raw bytes rather than the parsed
    object so a stray key cannot hide inside a nested dict."""
    save_field_sample(PICKS, 3, "2026-27")
    raw = field_sample_path("2026-27", 3).read_text()
    assert "entry" not in raw
    payload = json.loads(raw)
    assert [e["i"] for e in payload["entries"]] == [0, 1]


def test_the_sample_round_trips_as_the_picks_it_was_given(here):
    save_field_sample(PICKS, 3, "2026-27")
    assert load_field_sample("2026-27", 3) == PICKS


def test_an_absent_sample_is_none_not_an_empty_list(here):
    """``None`` is "never scraped"; ``[]`` would be "scraped and nobody was
    readable", and the scrape's idempotence check reads the difference."""
    assert load_field_sample("2026-27", 3) is None


def test_saving_twice_does_not_rewrite_the_first_answer(here):
    save_field_sample(PICKS, 3, "2026-27")
    before = field_sample_path("2026-27", 3).read_text()
    save_field_sample([[{"element": 1, "position": 1, "multiplier": 1}]],
                      3, "2026-27")
    assert field_sample_path("2026-27", 3).read_text() == before


def test_the_eo_rows_carry_the_log_schema_with_settled_dtypes(here):
    rows = field_eo_rows(TABLE, 3, "2026-27", day="2026-09-12")
    assert list(rows.columns) == FIELD_EO_COLS
    assert rows["element"].dtype == "int64"
    assert rows["n"].dtype == "int64"
    assert rows["eo"].dtype == "float64"
    assert set(rows["element"]) == {7, 9}


def test_an_empty_table_is_zero_rows_not_a_raise(here):
    assert len(field_eo_rows({}, 3, "2026-27", day="2026-09-12")) == 0


def test_the_log_appends_and_reads_back(here):
    n = append_field_eo(field_eo_rows(TABLE, 3, "2026-27", day="2026-09-12"))
    assert n == 2
    assert len(load_field_eo()) == 2
    assert store.exists(FIELD_EO_PATH)


def test_a_second_scrape_of_the_same_day_replaces_rather_than_doubles(here):
    append_field_eo(field_eo_rows(TABLE, 3, "2026-27", day="2026-09-12"))
    append_field_eo(field_eo_rows(TABLE, 3, "2026-27", day="2026-09-12"))
    assert len(load_field_eo()) == 2


def test_a_later_day_accumulates_beside_the_first(here):
    append_field_eo(field_eo_rows(TABLE, 3, "2026-27", day="2026-09-12"))
    append_field_eo(field_eo_rows(TABLE, 4, "2026-27", day="2026-09-19"))
    log = load_field_eo()
    assert len(log) == 4
    assert set(log["gw"]) == {3, 4}


def test_the_rewrite_leaves_no_temp_file_behind(here):
    append_field_eo(field_eo_rows(TABLE, 3, "2026-27", day="2026-09-12"))
    assert not (store.DATA_DIR / (FIELD_EO_PATH + ".tmp")).exists()


def test_an_absent_log_reads_as_an_empty_frame_with_the_columns(here):
    out = load_field_eo()
    assert out.empty
    assert list(out.columns) == FIELD_EO_COLS


def test_the_latest_read_answers_the_newest_gameweek(here):
    append_field_eo(field_eo_rows(TABLE, 3, "2026-27", day="2026-09-12"))
    append_field_eo(field_eo_rows({7: {"eo": 10.0, "se": 1.0, "n": 2}},
                                  4, "2026-27", day="2026-09-19"))
    latest = latest_field_eo()
    assert set(latest) == {7}
    assert latest[7]["eo"] == 10.0
    assert latest[7]["gw"] == 4


def test_the_latest_read_of_an_absent_log_is_an_empty_dict(here):
    assert latest_field_eo() == {}


def test_two_scrapes_of_one_gameweek_keep_only_the_later_day(here):
    """The log is per (gw, snap_date); the *latest* view is one row per
    element, so a Saturday and a Sunday scrape of one gameweek must not both
    reach the sword/shield column."""
    append_field_eo(field_eo_rows(TABLE, 3, "2026-27", day="2026-09-12"))
    append_field_eo(field_eo_rows({7: {"eo": 99.0, "se": 1.0, "n": 2}},
                                  3, "2026-27", day="2026-09-13"))
    assert len(load_field_eo()) == 3
    assert latest_field_eo()[7]["eo"] == 99.0
