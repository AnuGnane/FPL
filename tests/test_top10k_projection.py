"""scripts/top10k_projection.py, F-6's projection rule backtested (holiday F-35).

The three rules on a series computed by hand, a missed scrape week included,
then the verdict rule at its edges and the waiting sentence.
"""

from __future__ import annotations

import json
import sys

import pytest

sys.path.insert(0, "scripts")

import top10k_projection as tp

# gw5 was never scraped: gw6's rises span the two-week gap.
SERIES = {1: 60, 2: 120, 3: 190, 4: 250, 6: 400}


def test_the_three_rules_on_a_hand_computed_series():
    # gw3 from [1, 2]: one rise of 60, so every rule reads 120 + 60.
    assert tp.project(SERIES, 3) == {"f6": 180.0, "last_rise": 180.0,
                                     "median_rise": 180.0}
    # gw4 from [1, 2, 3]: mean rise (190 - 60) / 2 = 65; last 70; median of
    # [60, 70] = 65.
    assert tp.project(SERIES, 4) == {"f6": 255.0, "last_rise": 260.0,
                                     "median_rise": 255.0}
    # gw6 from [1, 2, 3, 4], two weeks ahead: mean (250 - 60) / 3; last 60;
    # median of [60, 70, 60] = 60.
    p6 = tp.project(SERIES, 6)
    assert p6["f6"] == pytest.approx(250 + 2 * 190 / 3)
    assert p6["last_rise"] == 370.0 and p6["median_rise"] == 370.0


def test_a_rise_across_a_missed_week_is_per_gameweek():
    series = {1: 0, 3: 100, 4: 160}
    # The 1 -> 3 rise is 50 a week, not 100; gw5's last rise is 60.
    assert tp.project(series, 5) == {"f6": 160 + 160 / 3,
                                     "last_rise": 220.0, "median_rise": 215.0}


def test_the_line_scores_every_week_with_two_weeks_before_it():
    out = tp.reading(SERIES, include_latest=True)
    assert out["n"] == 3 and out["banked"] == 5 and out["reason"] is None
    assert [w["gw"] for w in out["weeks"]] == [3, 4, 6]
    assert out["weeks"][0] == {"gw": 3, "banked": 190, "f6": 180.0,
                               "last_rise": 180.0, "median_rise": 180.0,
                               "scored": True}
    # f6 errors: -10, +5, 250 + 380/3 - 400 = -23.33; last_rise -10, +10, -30.
    assert out["rules"]["f6"]["mae"] == pytest.approx((10 + 5 + 70 / 3) / 3,
                                                      abs=0.01)
    assert out["rules"]["f6"]["bias"] == pytest.approx((-10 + 5 - 70 / 3) / 3,
                                                       abs=0.01)
    assert out["rules"]["last_rise"] == {"mae": pytest.approx(50 / 3, abs=0.01),
                                         "bias": pytest.approx(-10.0)}
    assert out["verdict"] == "insufficient"


def test_fewer_than_three_banked_weeks_prints_the_waiting_sentence():
    out = tp.reading({1: 60, 2: 120})
    assert out["n"] == 0 and out["verdict"] == "waiting"
    assert out["reason"].startswith("2 banked gameweeks;")
    assert tp.reading({1: 60})["reason"].startswith("1 banked gameweek;")
    assert tp.reading({})["verdict"] == "waiting"


def test_the_newest_week_is_listed_but_not_scored_by_default():
    out = tp.reading(SERIES)
    assert [(w["gw"], w["scored"]) for w in out["weeks"]] == [
        (3, True), (4, True), (6, False)]
    assert out["n"] == 2
    # f6 over gw3 and gw4 alone: errors -10 and +5.
    assert out["rules"]["f6"] == {"mae": 7.5, "bias": -2.5}


def test_three_banked_weeks_wait_on_the_newest_unless_it_is_included():
    out = tp.reading({1: 60, 2: 120, 3: 190})
    assert out["verdict"] == "waiting" and out["n"] == 0
    assert "gw3" in out["reason"] and len(out["weeks"]) == 1
    assert tp.reading({1: 60, 2: 120, 3: 190}, include_latest=True)["n"] == 1


@pytest.mark.parametrize(("other", "verdict"), [
    (9.0, "ruling: last_rise beats f6"),     # 10 % below: clears the bar
    (8.0, "ruling: last_rise beats f6"),
    (9.5, "f6 stays"),                       # 5 % below: does not
    (11.0, "f6 stays"),
])
def test_the_verdict_needs_ten_percent_over_five_weeks(other, verdict):
    mae = {"f6": 10.0, "last_rise": other, "median_rise": 12.0}
    assert tp._verdict(5, mae) == verdict
    assert tp._verdict(4, mae) == "insufficient"


def test_both_alternatives_clearing_the_bar_are_both_named():
    assert tp._verdict(5, {"f6": 10.0, "last_rise": 8.0,
                           "median_rise": 9.0}) == (
        "ruling: last_rise and median_rise beat f6")


def test_two_perfect_rules_leave_f6_in_place():
    assert tp._verdict(6, {"f6": 0.0, "last_rise": 0.0,
                           "median_rise": 0.0}) == "f6 stays"


def test_a_steady_rise_over_enough_weeks_keeps_f6():
    series = {gw: 60 * gw for gw in range(1, 10)}
    out = tp.reading(series)
    assert out["n"] == 6 and out["verdict"] == "f6 stays"
    assert out["rules"]["f6"] == {"mae": 0.0, "bias": 0.0}


def test_main_prints_the_line_for_a_season_with_no_log(monkeypatch, capsys):
    monkeypatch.setattr(tp, "threshold_series", lambda season: {})
    assert tp.main(["--season", "2026-27"]) == 0
    line = capsys.readouterr().out.strip()
    assert line.startswith("TOP10K_PROJ ")
    payload = json.loads(line.removeprefix("TOP10K_PROJ "))
    assert payload["season"] == "2026-27" and payload["verdict"] == "waiting"
