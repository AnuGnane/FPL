"""Spec §3.1: how much warning a status change gave, and what happened next.

The unit is a (gw, code) whose status changed at least once in the
pre-deadline window. Its lead time is measured from the *first* change — the
first moment the log said something other than what it had been saying —
because that is the first moment a manager could have acted.

The outcome is "did he start", from ``evaluation.start_truth``, which reads
``starts`` where the feed has it and falls back to ``minutes >= 60``.

A "late flag" is a row where the final pre-deadline status and the outcome
disagree: the log said available and he did not start, or the log said
unavailable and he did. Ordered by lead days ascending, because the worst late
flag is the one that arrived latest.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer import availability_eval as ae

EVENTS = pd.DataFrame({
    "gw": [2, 3],
    "deadline_time": ["2026-08-28T17:30:00Z", "2026-09-04T17:30:00Z"],
})


def _log(rows):
    """``(gw, snap_date, code, status)`` tuples -> a snapshot-log frame."""
    return pd.DataFrame(
        [{"season": "2026-27", "gw": g, "snap_date": d, "code": c,
          "status": s, "chance_of_playing": p, "llm_verdict": None,
          "source": None}
         for g, d, c, s, p in rows])


def _actuals(rows):
    """``(gw, code, minutes, starts)`` tuples -> a results frame."""
    return pd.DataFrame(
        [{"gw": g, "code": c, "minutes": m, "starts": st}
         for g, c, m, st in rows])


def test_a_player_whose_status_never_changed_is_not_a_row():
    """The report is about changes. A player who was 'a' all week told the
    manager nothing new and has no lead time to measure."""
    log = _log([(3, "2026-09-01", 1, "a", 100.0),
                (3, "2026-09-02", 1, "a", 100.0)])
    out = ae.score_flag_latency(log, _actuals([(3, 1, 90, 1)]), EVENTS,
                                season="2026-27")
    assert out["rows"] == 0


def test_the_lead_time_is_measured_from_the_first_change():
    """Two changes; the first is the one a manager could have acted on."""
    log = _log([(3, "2026-08-30", 1, "a", 100.0),
                (3, "2026-09-01", 1, "d", 50.0),
                (3, "2026-09-03", 1, "i", 0.0)])
    out = ae.score_flag_latency(log, _actuals([(3, 1, 0, 0)]), EVENTS,
                                season="2026-27")
    assert out["rows"] == 1
    row = out["changes"][0]
    assert row["first_change"] == "2026-09-01"
    assert row["lead_days"] == pytest.approx(3.73, abs=0.01)
    assert row["final_status"] == "i"
    assert row["started"] is False


def test_post_deadline_snapshots_are_not_in_the_window():
    """A2. GW2's deadline is 2026-08-28; the live log's GW2 rows are all
    later, and a change 'seen' after the deadline gave nobody any warning."""
    log = _log([(2, "2026-08-30", 1, "a", 100.0),
                (2, "2026-08-31", 1, "i", 0.0)])
    out = ae.score_flag_latency(log, _actuals([(2, 1, 0, 0)]), EVENTS,
                                season="2026-27")
    assert out["rows"] == 0


def test_only_data_checked_gameweeks_are_scored():
    """Without the result there is no outcome to pair the lead time with, so
    the row waits rather than being scored against a zero."""
    log = _log([(3, "2026-09-01", 1, "a", 100.0),
                (3, "2026-09-02", 1, "i", 0.0)])
    out = ae.score_flag_latency(log, _actuals([(2, 1, 90, 1)]), EVENTS,
                                season="2026-27")
    assert out["rows"] == 0
    assert out["checked_covered_gws"] == []


def test_the_season_guard_drops_another_seasons_rows():
    """Element ids are re-issued every August and so is gameweek 3. The log
    outlives a rollover; the results file does not carry a season at all."""
    log = pd.concat([
        _log([(3, "2026-09-01", 1, "a", 100.0),
              (3, "2026-09-02", 1, "i", 0.0)]),
        _log([(3, "2025-09-01", 1, "a", 100.0),
              (3, "2025-09-02", 1, "i", 0.0)]).assign(season="2025-26")])
    out = ae.score_flag_latency(log, _actuals([(3, 1, 0, 0)]), EVENTS,
                                season="2026-27")
    assert out["rows"] == 1


def test_the_histogram_splits_lead_days_by_outcome():
    log = _log([(3, "2026-08-30", 1, "a", 100.0),
                (3, "2026-09-03", 1, "i", 0.0),      # 1.73 days -> "1-2d"
                (3, "2026-08-30", 2, "a", 100.0),
                (3, "2026-08-31", 2, "d", 50.0)])    # 4.73 days -> "3-5d"
    out = ae.score_flag_latency(log, _actuals([(3, 1, 0, 0), (3, 2, 90, 1)]),
                                EVENTS, season="2026-27")
    buckets = {b["bucket"]: b for b in out["histogram"]}
    assert buckets["1-2d"] == {"bucket": "1-2d", "started": 0, "missed": 1}
    assert buckets["3-5d"] == {"bucket": "3-5d", "started": 1, "missed": 0}
    assert sum(b["started"] + b["missed"] for b in out["histogram"]) == 2


def test_a_late_flag_is_a_disagreement_between_the_final_status_and_the_start():
    """Both directions. The log said 'i' and he started; the log said 'a' and
    he did not. Either way the manager was told the wrong thing."""
    log = _log([(3, "2026-08-30", 1, "a", 100.0),
                (3, "2026-09-03", 1, "i", 0.0),
                (3, "2026-08-30", 2, "i", 0.0),
                (3, "2026-09-03", 2, "a", 100.0)])
    out = ae.score_flag_latency(
        log, _actuals([(3, 1, 90, 1), (3, 2, 0, 0)]), EVENTS,
        season="2026-27")
    assert [r["code"] for r in out["late_flags"]] == [1, 2]
    assert out["late_flags"][0]["started"] is True
    assert out["late_flags"][0]["final_status"] == "i"


def test_late_flags_are_ordered_by_lead_days_and_capped_at_twenty():
    """Spec §3.1 asks for the twenty worst. The worst is the latest."""
    rows = []
    for i in range(25):
        rows += [(3, "2026-08-30", i, "a", 100.0),
                 (3, f"2026-09-{i % 3 + 1:02d}", i, "i", 0.0)]
    out = ae.score_flag_latency(
        _log(rows), _actuals([(3, i, 90, 1) for i in range(25)]), EVENTS,
        season="2026-27")
    leads = [r["lead_days"] for r in out["late_flags"]]
    assert len(leads) == 20
    assert leads == sorted(leads)


def test_the_gate_reports_both_numbers_even_when_it_refuses():
    """Spec §3.1: the empty state says both numbers. Three snapshot dates of
    fourteen, and how many covered gameweeks are graded."""
    log = _log([(3, "2026-09-01", 1, "a", 100.0),
                (3, "2026-09-02", 1, "i", 0.0)])
    out = ae.score_flag_latency(log, _actuals([(3, 1, 0, 0)]), EVENTS,
                                season="2026-27")
    assert out["available"] is False
    assert out["snap_dates"] == 2
    assert out["min_snap_dates"] == 14
    assert out["checked_covered_gws"] == [3]
    assert "2 of 14" in out["note"]


def test_the_gate_opens_on_fourteen_dates_and_one_graded_gameweek():
    rows = [(3, f"2026-08-{d:02d}", 1, "a", 100.0) for d in range(18, 32)]
    rows.append((3, "2026-09-01", 1, "i", 0.0))
    out = ae.score_flag_latency(_log(rows), _actuals([(3, 1, 0, 0)]), EVENTS,
                                season="2026-27")
    assert out["available"] is True
    assert out["snap_dates"] == 15
    assert out["rows"] == 1


def test_an_empty_log_is_a_refusal_and_never_a_crash():
    out = ae.score_flag_latency(pd.DataFrame(), pd.DataFrame(), EVENTS,
                                season="2026-27")
    assert out["available"] is False
    assert out["rows"] == 0
    assert out["histogram"] == []
    assert out["late_flags"] == []
