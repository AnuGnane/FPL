"""Spec §3.2: the classifier's four verdicts against what happened.

The event being predicted is **absence** — "he did not start" — because that
is what every one of the four classes claims to some degree: ruled_out claims
it outright, knock and assess and rotation_risk claim it with less confidence.
Precision is then "of the players it called X, how many indeed did not start",
and the readout worth having is whether precision falls in the order the
classes are named in.

Recall is reported over the *verdict-carrying population* and labelled that
way on the payload. Recall over every absent player in the gameweek would be a
different and much harsher number — it would count every player the classifier
was never shown — and reporting it under the same word would be dishonest
about what was measured.
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
    """``(gw, snap_date, code, verdict, source)`` -> a snapshot-log frame."""
    return pd.DataFrame(
        [{"season": "2026-27", "gw": g, "snap_date": d, "code": c,
          "status": "d", "llm_verdict": v, "llm_confidence": 0.8,
          "source": s}
         for g, d, c, v, s in rows])


def _actuals(rows):
    return pd.DataFrame([{"gw": g, "code": c, "minutes": m, "starts": st}
                         for g, c, m, st in rows])


def test_the_population_is_the_verdict_column_and_not_the_source_column():
    """A3. 160 of the live log's 169 verdict rows say source=premierinjuries
    and 9 say llm. Filtering on source would grade 5% of the evidence."""
    log = _log([(3, "2026-09-01", 1, "ruled_out", "premierinjuries"),
                (3, "2026-09-01", 2, "ruled_out", "llm"),
                (3, "2026-09-01", 3, None, "lineups")])
    out = ae.score_presser_grades(
        log, _actuals([(3, 1, 0, 0), (3, 2, 0, 0), (3, 3, 90, 1)]), EVENTS,
        season="2026-27")
    assert out["rows"] == 2


def test_the_source_travels_as_a_breakdown_rather_than_a_filter():
    log = _log([(3, "2026-09-01", 1, "ruled_out", "premierinjuries"),
                (3, "2026-09-01", 2, "ruled_out", "llm")])
    out = ae.score_presser_grades(
        log, _actuals([(3, 1, 0, 0), (3, 2, 0, 0)]), EVENTS,
        season="2026-27")
    assert out["by_source"] == [{"source": "llm", "rows": 1},
                                {"source": "premierinjuries", "rows": 1}]


def test_the_confusion_matrix_counts_starts_against_each_class():
    log = _log([(3, "2026-09-01", 1, "ruled_out", "premierinjuries"),
                (3, "2026-09-01", 2, "ruled_out", "premierinjuries"),
                (3, "2026-09-01", 3, "assess", "premierinjuries")])
    out = ae.score_presser_grades(
        log, _actuals([(3, 1, 0, 0), (3, 2, 90, 1), (3, 3, 0, 0)]), EVENTS,
        season="2026-27")
    matrix = {r["verdict"]: r for r in out["confusion"]}
    assert matrix["ruled_out"] == {"verdict": "ruled_out", "started": 1,
                                   "not_started": 1, "n": 2}
    assert matrix["assess"]["not_started"] == 1


def test_precision_is_absence_given_the_verdict():
    log = _log([(3, "2026-09-01", i, "ruled_out", "premierinjuries")
                for i in range(4)])
    out = ae.score_presser_grades(
        log, _actuals([(3, 0, 0, 0), (3, 1, 0, 0), (3, 2, 0, 0),
                       (3, 3, 90, 1)]), EVENTS, season="2026-27")
    row = next(r for r in out["per_class"] if r["verdict"] == "ruled_out")
    assert row["precision"] == 0.75
    assert row["n"] == 4


def test_recall_is_over_the_verdict_carrying_population_and_says_so():
    """Three absent players carried a verdict; two of them were ruled_out."""
    log = _log([(3, "2026-09-01", 1, "ruled_out", "premierinjuries"),
                (3, "2026-09-01", 2, "ruled_out", "premierinjuries"),
                (3, "2026-09-01", 3, "knock", "premierinjuries")])
    out = ae.score_presser_grades(
        log, _actuals([(3, 1, 0, 0), (3, 2, 0, 0), (3, 3, 0, 0)]), EVENTS,
        season="2026-27")
    row = next(r for r in out["per_class"] if r["verdict"] == "ruled_out")
    assert row["recall"] == pytest.approx(2 / 3)
    assert out["recall_population"] == "verdict-carrying rows"


def test_a_class_nobody_got_right_reports_zero_and_not_null():
    log = _log([(3, "2026-09-01", 1, "rotation_risk", "premierinjuries")])
    out = ae.score_presser_grades(log, _actuals([(3, 1, 90, 1)]), EVENTS,
                                  season="2026-27")
    row = next(r for r in out["per_class"] if r["verdict"] == "rotation_risk")
    assert row["precision"] == 0.0
    assert row["n"] == 1


def test_the_classes_are_read_off_the_data_and_not_hard_coded():
    """A fifth class from a prompt change must show up as a row, not vanish."""
    log = _log([(3, "2026-09-01", 1, "suspended_appeal", "premierinjuries")])
    out = ae.score_presser_grades(log, _actuals([(3, 1, 0, 0)]), EVENTS,
                                  season="2026-27")
    assert [r["verdict"] for r in out["per_class"]] == ["suspended_appeal"]


def test_the_last_pre_deadline_verdict_is_the_one_graded():
    """Same rule ``score_news_shadow`` applies with ``.last()``: the verdict
    that stood when the deadline came is the one the manager acted on."""
    log = _log([(3, "2026-09-01", 1, "ruled_out", "premierinjuries"),
                (3, "2026-09-03", 1, "assess", "premierinjuries")])
    out = ae.score_presser_grades(log, _actuals([(3, 1, 90, 1)]), EVENTS,
                                  season="2026-27")
    assert out["rows"] == 1
    assert [r["verdict"] for r in out["per_class"]] == ["assess"]


def test_post_deadline_verdicts_are_not_graded_and_the_note_says_so():
    """A3, and the state of the live log today: every banked verdict was
    recorded after its gameweek's deadline, so the report is empty even though
    GW2 is data_checked."""
    log = _log([(2, "2026-08-30", 1, "ruled_out", "premierinjuries"),
                (2, "2026-08-31", 2, "assess", "premierinjuries")])
    out = ae.score_presser_grades(
        log, _actuals([(2, 1, 0, 0), (2, 2, 90, 1)]), EVENTS,
        season="2026-27")
    assert out["available"] is False
    assert out["rows"] == 0
    assert out["verdicts_banked"] == 2
    assert "before a deadline" in out["note"]


def test_an_ungraded_gameweek_waits_rather_than_scoring():
    log = _log([(3, "2026-09-01", 1, "ruled_out", "premierinjuries")])
    out = ae.score_presser_grades(log, _actuals([(2, 1, 0, 0)]), EVENTS,
                                  season="2026-27")
    assert out["available"] is False
    assert "data_checked" in out["note"]


def test_the_season_guard_drops_another_seasons_verdicts():
    log = pd.concat([
        _log([(3, "2026-09-01", 1, "ruled_out", "premierinjuries")]),
        _log([(3, "2025-09-01", 1, "assess", "premierinjuries")])
        .assign(season="2025-26")])
    out = ae.score_presser_grades(log, _actuals([(3, 1, 0, 0)]), EVENTS,
                                  season="2026-27")
    assert out["rows"] == 1


def test_a_log_with_no_verdict_column_at_all_is_a_refusal():
    """A log banked before the classifier existed. Not a crash."""
    log = _log([(3, "2026-09-01", 1, None, "lineups")]).drop(
        columns=["llm_verdict"])
    out = ae.score_presser_grades(log, _actuals([(3, 1, 0, 0)]), EVENTS,
                                  season="2026-27")
    assert out["available"] is False
    assert out["rows"] == 0
