"""The two reports end to end: log on disk -> artifact key -> terminal table.

The artifact is ``reports/evaluation.json``, not a file of their own. Spec
§3.1 names ``reports/evaluate/flag_latency.json``; that directory does not
exist, nothing would read it, and ``save_evaluation`` already merges
independent keys into one artifact through a temp file with allow_nan=False —
which is the discipline that stops a NaN becoming a 500 from /api/quality
three weeks later. The deviation is deliberate and recorded in the README.
"""

from __future__ import annotations

import json

import pandas as pd
from typer.testing import CliRunner

from gaffer import availability_eval as ae
from gaffer.cli import app

runner = CliRunner()


def _wire(monkeypatch, tmp_path, log, actuals, events):
    """Point every reader at frames, and the artifact at a temp directory."""
    from gaffer import evaluation
    from gaffer.config import Config

    monkeypatch.setattr(evaluation, "REPORTS", tmp_path)
    monkeypatch.setattr(evaluation, "EVALUATION_PATH",
                        tmp_path / "evaluation.json")
    monkeypatch.setattr(ae, "load_snapshot_log", lambda: log)
    monkeypatch.setattr(ae, "news_actuals", lambda: actuals)
    monkeypatch.setattr(ae, "load_events", lambda: events)
    monkeypatch.setattr(ae, "load_config",
                        lambda: Config(entry_id=1, league_id=2,
                                       current_season="2026-27"))
    return tmp_path / "evaluation.json"


def _log(gw, dates, verdict=None):
    rows = []
    for i, day in enumerate(dates):
        rows.append({"season": "2026-27", "gw": gw, "snap_date": day,
                     "code": 1, "status": "a" if i == 0 else "i",
                     "chance_of_playing": 100.0 if i == 0 else 0.0,
                     "llm_verdict": verdict, "llm_confidence": 0.9,
                     "source": "premierinjuries"})
    return pd.DataFrame(rows)


EVENTS = pd.DataFrame({"gw": [3],
                       "deadline_time": ["2026-09-04T17:30:00Z"]})
ACTUALS = pd.DataFrame({"gw": [3], "code": [1], "minutes": [0],
                        "starts": [0]})


def test_flag_latency_writes_its_key_into_the_one_artifact(monkeypatch,
                                                           tmp_path):
    dates = [f"2026-08-{d:02d}" for d in range(18, 32)] + ["2026-09-01"]
    path = _wire(monkeypatch, tmp_path, _log(3, dates), ACTUALS, EVENTS)
    result = runner.invoke(app, ["evaluate", "--flag-latency"])
    assert result.exit_code == 0
    stored = json.loads(path.read_text())
    assert stored["flag_latency"]["available"] is True
    assert stored["flag_latency"]["rows"] == 1


def test_presser_grades_writes_its_own_key_and_leaves_the_other_alone(
        monkeypatch, tmp_path):
    path = _wire(monkeypatch, tmp_path,
                 _log(3, ["2026-09-01"], verdict="ruled_out"), ACTUALS,
                 EVENTS)
    path.write_text(json.dumps({"flag_latency": {"kind": "flag_latency"}}))
    result = runner.invoke(app, ["evaluate", "--presser-grades"])
    assert result.exit_code == 0
    stored = json.loads(path.read_text())
    assert stored["presser_grades"]["rows"] == 1
    assert stored["flag_latency"] == {"kind": "flag_latency"}


def test_the_refusal_is_still_written_and_still_exit_zero(monkeypatch,
                                                          tmp_path):
    """An empty report is a measurement, not a failure. It is banked so the
    page can print what it is waiting for."""
    path = _wire(monkeypatch, tmp_path, _log(3, ["2026-09-01"]), ACTUALS,
                 EVENTS)
    result = runner.invoke(app, ["evaluate", "--flag-latency"])
    assert result.exit_code == 0
    stored = json.loads(path.read_text())
    assert stored["flag_latency"]["available"] is False
    assert "of 14" in stored["flag_latency"]["note"]


def test_the_terminal_table_prints_the_buckets_and_the_worst_flags():
    payload = {"kind": "flag_latency", "available": True, "rows": 2,
               "snap_dates": 15, "min_snap_dates": 14,
               "histogram": [{"bucket": "1-2d", "started": 1, "missed": 1}],
               "late_flags": [{"gw": 3, "code": 7, "lead_days": 1,
                               "final_status": "i", "started": True,
                               "first_change": "2026-09-03",
                               "from_status": "a",
                               "chance_of_playing": 0.0}],
               "run_at": "now", "git_sha": "abc1234"}
    from gaffer.evaluation import format_report

    text = format_report("flag_latency", payload)
    assert "1-2d" in text
    assert "code 7" in text


def test_the_terminal_table_says_what_it_is_waiting_for_when_empty():
    from gaffer.evaluation import format_report

    text = format_report("flag_latency",
                         {"kind": "flag_latency", "available": False,
                          "rows": 0, "note": "3 of 14 snapshot days banked.",
                          "run_at": "now", "git_sha": "abc1234"})
    assert "3 of 14" in text


def test_the_presser_table_prints_precision_per_class():
    from gaffer.evaluation import format_report

    text = format_report("presser_grades", {
        "kind": "presser_grades", "available": True, "rows": 4,
        "absent_rows": 3, "recall_population": "verdict-carrying rows",
        "per_class": [{"verdict": "ruled_out", "n": 4, "precision": 0.75,
                       "recall": 1.0}],
        "confusion": [{"verdict": "ruled_out", "n": 4, "started": 1,
                       "not_started": 3}],
        "by_source": [{"source": "premierinjuries", "rows": 4}],
        "run_at": "now", "git_sha": "abc1234"})
    assert "ruled_out" in text
    assert "0.75" in text


def test_recall_prints_a_dash_when_nobody_in_the_gameweek_was_absent():
    """The payload stores 0.0 because the artifact needs a number, but a
    column of 0.00 reads as a class that missed every absence rather than one
    that was asked about a gameweek with none."""
    from gaffer.evaluation import format_report

    text = format_report("presser_grades", {
        "kind": "presser_grades", "available": True, "rows": 1,
        "absent_rows": 0, "recall_population": "verdict-carrying rows",
        "per_class": [{"verdict": "rotation_risk", "n": 1, "precision": 0.0,
                       "recall": 0.0}],
        "confusion": [{"verdict": "rotation_risk", "n": 1, "started": 1,
                       "not_started": 0}],
        "by_source": [{"source": "premierinjuries", "rows": 1}],
        "run_at": "now", "git_sha": "abc1234"})
    assert "—" in text
    assert "0.00" in text          # precision still prints as a number
