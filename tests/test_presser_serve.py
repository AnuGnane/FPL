"""scripts/presser_serve.py, the presser classifier's serving rule (holiday F-38).

A synthetic snapshot log, events and results: weeks in class order, a week
out of order and a week under twenty verdict rows, each graded through the
real ``score_presser_grades``.
"""

from __future__ import annotations

import json
import sys

import pandas as pd

sys.path.insert(0, "scripts")

import presser_serve  # noqa: E402 — scripts/ is not a package; the path insert must come first

SEASON = "2026-27"


def _week(gw, classes):
    """Log and result rows for one gameweek. ``classes`` maps a verdict to
    ``(n, absent)``; codes are unique per gameweek."""
    log, res = [], []
    code = gw * 1000
    for verdict, (n, absent) in classes.items():
        for i in range(n):
            code += 1
            log.append({"season": SEASON, "gw": gw, "code": code,
                        "snap_date": f"2026-09-{gw:02d}",
                        "status": "a", "llm_verdict": verdict,
                        "source": "premierinjuries"})
            res.append({"gw": gw, "code": code,
                        "minutes": 0 if i < absent else 90, "starts": None})
    return log, res


def _frames(weeks):
    log, res = [], []
    for gw, classes in weeks.items():
        week_log, week_res = _week(gw, classes)
        log += week_log
        res += week_res
    events = pd.DataFrame({
        "gw": list(weeks),
        "deadline_time": [f"2026-09-{gw + 3:02d}T17:30:00Z" for gw in weeks]})
    return pd.DataFrame(log), pd.DataFrame(res), events


IN_ORDER = {"ruled_out": (8, 8), "knock": (6, 2), "confirmed_starter": (10, 0)}
OUT_OF_ORDER = {"ruled_out": (8, 1), "knock": (6, 5),
                "confirmed_starter": (10, 0)}
SMALL = {"ruled_out": (3, 3), "confirmed_starter": (5, 0)}


def test_a_week_in_order_and_a_week_out_of_order_each_read_as_such():
    log, res, events = _frames({3: IN_ORDER, 4: OUT_OF_ORDER, 5: SMALL})
    weeks, serve = presser_serve.readings(log, res, events, SEASON)
    by = {w["gw"]: w for w in weeks}
    assert sorted(by) == [3, 4, 5]
    assert by[3]["n"] == 24 and by[3]["in_order"] is True
    assert by[3]["classes"]["ruled_out"]["precision"] == 1.0
    assert by[3]["classes"]["knock"]["precision"] == round(2 / 6, 4)
    assert by[3]["base_absence"] == round(10 / 24, 4)
    assert by[4]["in_order"] is False
    assert by[5]["n"] == 8 and by[5]["counts"] is False
    # Two counted weeks: the rule needs three.
    assert serve["counted_gws"] == [3, 4]
    assert serve["verdict"].startswith("insufficient")


def test_three_weeks_in_order_with_a_lift_read_worth_an_arm():
    log, res, events = _frames({3: IN_ORDER, 4: IN_ORDER, 6: IN_ORDER,
                                5: SMALL})
    _, serve = presser_serve.readings(log, res, events, SEASON)
    assert serve["counted_gws"] == [3, 4, 6]
    assert serve["pooled_top_precision"] == 1.0
    assert serve["pooled_base_absence"] == round(30 / 72, 4)
    assert serve["verdict"].startswith("worth an arm")


def test_one_counted_week_out_of_order_keeps_serving_off():
    log, res, events = _frames({3: IN_ORDER, 4: OUT_OF_ORDER, 6: IN_ORDER})
    _, serve = presser_serve.readings(log, res, events, SEASON)
    assert serve["out_of_order_gws"] == [4]
    assert serve["verdict"].startswith("stays off")


def test_a_tie_does_not_break_the_order_and_a_missing_class_is_skipped():
    assert presser_serve.in_order([
        {"verdict": "ruled_out", "precision": 0.5},
        {"verdict": "rotation_risk", "precision": 0.5},
        {"verdict": "irrelevant", "precision": 0.9}])
    assert not presser_serve.in_order([
        {"verdict": "assess", "precision": 0.2},
        {"verdict": "knock", "precision": 0.3}])


def test_an_ungraded_week_and_another_season_are_not_read():
    log, res, events = _frames({3: IN_ORDER, 4: IN_ORDER})
    res = res[res["gw"] == 3]
    other = log.assign(season="2025-26", gw=log["gw"] + 10)
    weeks, _ = presser_serve.readings(pd.concat([log, other]), res, events,
                                      SEASON)
    assert [w["gw"] for w in weeks] == [3]


def test_missing_inputs_print_a_reason_not_a_traceback():
    log, res, events = _frames({3: IN_ORDER})
    for args in ((None, res, events, SEASON), (log, None, events, SEASON),
                 (log, res, events, ""),
                 (log.drop(columns="llm_verdict"), res, events, SEASON)):
        weeks, serve = presser_serve.readings(*args)
        assert weeks == [] and serve["n"] == 0 and serve["reason"]


def test_main_prints_the_serve_line_on_an_empty_clone(capsys, monkeypatch):
    monkeypatch.setattr(presser_serve, "_season", lambda: SEASON)
    monkeypatch.setattr(presser_serve, "load_snapshot_log",
                        lambda: pd.DataFrame())
    assert presser_serve.main() == 0
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert line.startswith("PRESSER_SERVE ")
    payload = json.loads(line.removeprefix("PRESSER_SERVE "))
    assert payload["n"] == 0 and payload["reason"] == "no snapshot log banked"
