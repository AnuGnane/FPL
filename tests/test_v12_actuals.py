"""The three shared readers both availability reports stand on.

``news_actuals`` is lifted out of ``evaluate_news_shadow`` unchanged — spec
§3.2 says the presser report shares that loader, and sharing a loader means
one function, not two copies that agree today.

``deadlines`` and ``pre_deadline`` are the pair the spec does not mention and
neither report can do without. The availability log stamps each snapshot with
``next_unfinished_gw`` — the first gameweek not yet *finished* — so a Saturday
evening snapshot of a gameweek in play carries that gameweek's number even
though its deadline is two days gone. Measured on the live log: every GW2 row
is dated 2026-08-30 or 2026-08-31 against a deadline of 2026-08-28. "Days
before the deadline" over those rows is a negative number, and a histogram of
negative lead times is not a late flag, it is a category error.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer import availability_eval as ae


@pytest.fixture()
def events():
    return pd.DataFrame({
        "gw": [1, 2, 3],
        "deadline_time": ["2026-08-21T17:30:00Z", "2026-08-28T17:30:00Z",
                          "2026-09-04T17:30:00Z"],
    })


def test_deadlines_are_utc_timestamps_keyed_by_gameweek(events):
    out = ae.deadlines(events)
    assert out[2] == pd.Timestamp("2026-08-28T17:30:00Z")
    assert set(out) == {1, 2, 3}


def test_a_gameweek_with_an_unreadable_deadline_is_absent_not_guessed(events):
    """A guessed deadline manufactures a lead time out of nothing."""
    broken = events.assign(deadline_time=["2026-08-21T17:30:00Z", "soon",
                                          None])
    assert set(ae.deadlines(broken)) == {1}


def test_deadlines_of_a_frame_without_the_column_is_empty(events):
    assert ae.deadlines(events.drop(columns=["deadline_time"])) == {}
    assert ae.deadlines(pd.DataFrame()) == {}


def test_pre_deadline_keeps_only_snapshots_at_or_before_the_deadline(events):
    log = pd.DataFrame({
        "season": ["2026-27"] * 4,
        "gw": [2, 2, 2, 3],
        "snap_date": ["2026-08-26", "2026-08-28", "2026-08-30", "2026-09-01"],
        "code": [1, 1, 1, 1],
    })
    kept = ae.pre_deadline(log, ae.deadlines(events))
    assert list(kept["snap_date"]) == ["2026-08-26", "2026-08-28",
                                       "2026-09-01"]


def test_pre_deadline_computes_lead_days_from_midnight_utc(events):
    """``snap_date`` is a date with no clock in it, so the day is taken at
    00:00 UTC and the figure is the calendar distance to the deadline. Two
    decimals, because the deadline's own 17:30 is real and dropping it would
    make a Friday flag and a Thursday one the same number."""
    log = pd.DataFrame({"season": ["2026-27"], "gw": [2],
                        "snap_date": ["2026-08-26"], "code": [1]})
    kept = ae.pre_deadline(log, ae.deadlines(events))
    assert kept["lead_days"].iloc[0] == pytest.approx(2.73, abs=0.01)


def test_pre_deadline_drops_a_gameweek_with_no_deadline_at_all(events):
    log = pd.DataFrame({"season": ["2026-27"], "gw": [9],
                        "snap_date": ["2026-08-26"], "code": [1]})
    assert ae.pre_deadline(log, ae.deadlines(events)).empty


def test_checked_gws_is_presence_in_the_results_file():
    """``review.py:140``: presence in ``player_gw.parquet`` *is* the
    ``data_checked`` gate. Not a flag on the events frame — FPL sets that one
    late, and the results are the thing both reports actually join to."""
    actuals = pd.DataFrame({"gw": [1, 1, 2], "code": [1, 2, 1],
                            "minutes": [90, 0, 45]})
    assert ae.checked_gws(actuals) == {1, 2}
    assert ae.checked_gws(pd.DataFrame(columns=["gw"])) == set()
    assert ae.checked_gws(None) == set()


def test_news_actuals_reads_the_results_parquet(monkeypatch):
    from gaffer import evaluation
    from gaffer.data import store as store_mod

    frame = pd.DataFrame({"gw": [2], "code": [7], "minutes": [90]})
    monkeypatch.setattr(store_mod, "exists",
                        lambda p: p == "live/player_gw.parquet")
    monkeypatch.setattr(store_mod, "load", lambda p: frame)
    assert evaluation.news_actuals()["minutes"].iloc[0] == 90


def test_news_actuals_with_no_file_is_an_empty_frame_with_the_join_keys(
        monkeypatch):
    from gaffer import evaluation
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "exists", lambda p: False)
    out = evaluation.news_actuals()
    assert out.empty
    assert {"gw", "code", "minutes"} <= set(out.columns)
