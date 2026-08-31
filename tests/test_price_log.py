"""The daily price bank: what FPL's own predictor said, kept.

``gaffer prices`` has always printed tonight's likely changes and forgotten
them, which makes the one question worth asking unanswerable — "what was the
predictor saying about him three days before he rose?". These tests are the
snapshot log's tests asked about a different frame: the same idempotency key,
the same append-by-rewrite, the same atomic replace, and the same absolute
refusal to raise on a scheduled job's behalf.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.data import store
from gaffer.price_log import (PRICE_LOG_COLS, PRICE_LOG_PATH, append_prices,
                              bank_prices, load_price_log, price_rows)

PLAYERS = pd.DataFrame({
    "code": [11, 22, 33, 44],
    "name": ["Saka", "Haaland", "Rice", "Locked"],
    "now_cost": [101, 150, 65, 45],
    "price_change_percent": [98.5, -100.0, 0.0, float("nan")],
    "price_change_calibrating": [False, False, True, False],
})


@pytest.fixture(autouse=True)
def _tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    (tmp_path / "data" / "live").mkdir(parents=True)


def test_every_player_is_banked_not_only_the_alerts():
    """The whole reason to bank rather than print: the interesting row is the
    one that was *not* an alert on the day it was written."""
    rows = price_rows(PLAYERS, day="2026-08-31")
    assert len(rows) == 4
    assert list(rows.columns) == PRICE_LOG_COLS


def test_the_direction_is_three_valued_here_and_null_is_not_flat():
    """A1: ``flat`` is a reading, null is the absence of one, and collapsing
    them would hide "the predictor published nothing about him"."""
    rows = price_rows(PLAYERS, day="2026-08-31").set_index("code")
    assert rows.loc[11, "direction"] == "rise"
    assert rows.loc[22, "direction"] == "drop"
    assert rows.loc[33, "direction"] == "flat"
    assert pd.isna(rows.loc[44, "direction"])
    assert pd.isna(rows.loc[44, "price_change_percent"])


def test_the_calibrating_flag_rides_along():
    rows = price_rows(PLAYERS, day="2026-08-31").set_index("code")
    assert bool(rows.loc[33, "calibrating"]) is True
    assert bool(rows.loc[11, "calibrating"]) is False


def test_a_missing_calibrating_column_is_false_not_a_crash():
    """The bootstrap gained the field mid-season once already; a frame from an
    older cache must bank as "not calibrating" rather than fail the job."""
    rows = price_rows(PLAYERS.drop(columns=["price_change_calibrating"]),
                      day="2026-08-31")
    assert not rows["calibrating"].any()


def test_re_running_the_same_day_replaces_rather_than_accumulates():
    append_prices(price_rows(PLAYERS, day="2026-08-31"))
    append_prices(price_rows(PLAYERS, day="2026-08-31"))
    assert len(load_price_log()) == 4


def test_a_second_day_is_kept_beside_the_first():
    append_prices(price_rows(PLAYERS, day="2026-08-30"))
    append_prices(price_rows(PLAYERS, day="2026-08-31"))
    log = load_price_log()
    assert len(log) == 8
    assert set(log["snap_date"]) == {"2026-08-30", "2026-08-31"}


def test_the_two_days_share_one_dtype_per_column():
    """A quiet day and a busy one must not write two incompatible schemas
    into one growing file — the trade ``snapshot_rows`` makes."""
    quiet = PLAYERS.assign(price_change_percent=float("nan"))
    append_prices(price_rows(quiet, day="2026-08-30"))
    append_prices(price_rows(PLAYERS, day="2026-08-31"))
    log = load_price_log()
    assert str(log["price_change_percent"].dtype) == "float64"
    assert str(log["code"].dtype) == "int64"


def test_the_rewrite_leaves_no_temp_file_behind():
    append_prices(price_rows(PLAYERS, day="2026-08-31"))
    assert not (store.DATA_DIR / (PRICE_LOG_PATH + ".tmp")).exists()


def test_an_empty_log_reads_as_the_right_shape():
    assert list(load_price_log().columns) == PRICE_LOG_COLS
    assert load_price_log().empty


def test_banking_answers_the_row_count():
    assert bank_prices(PLAYERS, day="2026-08-31") == 4


def test_an_unwritable_store_costs_the_day_and_nothing_else(monkeypatch,
                                                            capsys):
    """The nightly job's contract. ``prices`` still printed its alerts before
    this ran (A2), so a failure here must be a printed line, not an
    exception."""
    def boom(*_args, **_kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr("gaffer.price_log.append_prices", boom)
    assert bank_prices(PLAYERS, day="2026-08-31") is None
    assert "price log not written" in capsys.readouterr().out


@pytest.mark.parametrize("frame", [None, pd.DataFrame(),
                                   pd.DataFrame({"code": [1]})])
def test_an_unusable_frame_banks_nothing(frame, capsys):
    assert bank_prices(frame, day="2026-08-31") is None
    assert "price log not written" in capsys.readouterr().out


def test_the_day_comes_from_the_snapshot_logs_own_clock():
    """One definition of "today" across both daily logs, or the two drift
    apart in exactly the week somebody wants to join them."""
    import gaffer.price_log as pl
    import gaffer.snapshot as snap

    assert pl.snap_date is snap.snap_date


def test_banking_with_no_day_stamps_today(monkeypatch):
    monkeypatch.setattr("gaffer.price_log.snap_date", lambda: "2026-12-25")
    bank_prices(PLAYERS)
    assert set(load_price_log()["snap_date"]) == {"2026-12-25"}
