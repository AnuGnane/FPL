"""scripts/c1_news_buckets.py, the news layer against flags by bucket (holiday F-19).

A synthetic shadow log and results: a zero the flags side called, a blank
the news side called, a double gameweek and a shadow row with no result, so
each join rule is seen to bite.
"""

from __future__ import annotations

import json
import sys

import pandas as pd
import pytest

from gaffer.data import store
from gaffer.news_shadow import SHADOW_COLS, SHADOW_PATH

sys.path.insert(0, "scripts")

import c1_news_buckets


def _shadow(rows, season="2026-27"):
    out = []
    for gw, code, pn, pf, en, ef in rows:
        out.append({"season": season, "gw": gw, "code": code,
                    "p_play_news": pn, "p_play_flags": pf,
                    "e_min_news": en, "e_min_flags": ef,
                    "p_play_presser": pn, "run_at": "2026-10-01T00:00:00"})
    return pd.DataFrame(out, columns=SHADOW_COLS)


def _results(rows):
    return pd.DataFrame(rows, columns=["gw", "code", "minutes",
                                       "total_points"])


SHADOW = _shadow([
    # A zero the flags side called: he sat, flags said 0.1, news said 0.9.
    (5, 1, 0.9, 0.1, 80.0, 10.0),
    # A blank the news side called: a cameo, news said 0.8, flags 0.2.
    (5, 2, 0.8, 0.2, 30.0, 5.0),
    # A double gameweek: two fixtures, one shadow row, two result rows.
    (5, 3, 1.0, 1.0, 180.0, 180.0),
    # No result yet for gameweek 6.
    (6, 1, 0.5, 0.5, 45.0, 45.0),
])

RESULTS = _results([
    (5, 1, 0, 0),
    (5, 2, 15, 1),
    (5, 3, 90, 6),
    (5, 3, 90, 3),
])


def test_each_row_lands_in_its_bucket_and_the_unplayed_week_is_not_scored():
    out = c1_news_buckets.buckets_reading(SHADOW, RESULTS, "2026-27")
    b = out["buckets"]
    assert out["n"] == 3
    assert b["all"]["n"] == 3
    assert b["zeros"]["n"] == 1 and b["blanks"]["n"] == 1
    # The double gameweek sums to 9 points and 180 minutes: one hauler row.
    assert b["haulers"]["n"] == 1 and b["tickers"]["n"] == 0
    assert b["haulers"]["mae_news"] == 0.0


def test_the_zero_favours_flags_and_the_blank_favours_news():
    b = c1_news_buckets.buckets_reading(SHADOW, RESULTS, "2026-27")["buckets"]
    assert b["zeros"]["brier_news"] == pytest.approx(0.81)
    assert b["zeros"]["brier_flags"] == pytest.approx(0.01)
    assert b["blanks"]["brier_news"] == pytest.approx(0.04)
    assert b["blanks"]["brier_flags"] == pytest.approx(0.64)
    assert b["zeros"]["mae_flags"] == pytest.approx(10.0)
    assert b["blanks"]["mae_news"] == pytest.approx(15.0)
    # Both rows disagree by more than 0.05; the double gameweek agrees.
    assert b["zeros"]["disagree"]["n"] == 1
    assert b["haulers"]["disagree"]["n"] == 0
    assert b["haulers"]["disagree"]["brier_news"] is None


def test_too_few_disagreeing_rows_reads_insufficient():
    out = c1_news_buckets.buckets_reading(SHADOW, RESULTS, "2026-27")
    assert out["verdict"].startswith("insufficient: zeros has 1")


def test_last_seasons_rows_are_cut_and_the_last_run_of_a_key_is_kept():
    old = _shadow([(5, 1, 0.0, 0.0, 0.0, 0.0)], season="2025-26")
    rerun = _shadow([(5, 1, 0.0, 0.1, 0.0, 10.0)])
    shadow = pd.concat([old, SHADOW, rerun], ignore_index=True)
    b = c1_news_buckets.buckets_reading(shadow, RESULTS, "2026-27")["buckets"]
    assert b["zeros"]["n"] == 1
    assert b["zeros"]["brier_news"] == pytest.approx(0.0)


def _many(n, news_zero, news_blank):
    """``n`` disagreeing zeros and blanks, the news side at the given p."""
    shadow, results = [], []
    for i in range(n):
        shadow.append((5, 100 + i, news_zero, 0.5, 0.0, 0.0))
        results.append((5, 100 + i, 0, 0))
        shadow.append((5, 500 + i, news_blank, 0.5, 30.0, 30.0))
        results.append((5, 500 + i, 20, 2))
    return _shadow(shadow), _results(results)


def test_a_news_side_better_on_both_buckets_keeps_its_place():
    shadow, results = _many(30, 0.2, 0.9)
    out = c1_news_buckets.buckets_reading(shadow, results, "2026-27")
    assert out["verdict"].startswith("keeps its place")


def test_a_news_side_worse_on_the_zeros_is_a_retire_candidate():
    shadow, results = _many(30, 0.8, 0.9)
    out = c1_news_buckets.buckets_reading(shadow, results, "2026-27")
    assert out["verdict"].startswith("retire candidate")
    assert "zeros" in out["verdict"] and "blanks" not in out["verdict"]


def test_a_missing_log_prints_the_line_with_n_zero_not_a_traceback(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    assert c1_news_buckets.main() == 0
    line = capsys.readouterr().out.strip()
    assert line.startswith("C1_BUCKETS ")
    payload = json.loads(line.removeprefix("C1_BUCKETS "))
    assert payload["n"] == 0 and payload["reason"] == "no news shadow log banked"


def test_missing_results_print_the_line_with_their_reason(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    store.save(SHADOW, SHADOW_PATH)
    assert c1_news_buckets.main() == 0
    payload = json.loads(capsys.readouterr().out.strip()
                         .removeprefix("C1_BUCKETS "))
    assert payload["n"] == 0 and payload["reason"].startswith("no results")


def test_results_without_points_are_named_not_raised():
    out = c1_news_buckets.buckets_reading(
        SHADOW, RESULTS.drop(columns="total_points"), "2026-27")
    assert out["n"] == 0 and "total_points" in out["reason"]


def test_a_row_with_a_null_prediction_is_neither_counted_nor_scored():
    nulled = pd.concat([SHADOW, _shadow([(5, 9, float("nan"), 0.5, 0.0,
                                          0.0)])], ignore_index=True)
    results = pd.concat([RESULTS, _results([(5, 9, 0, 0)])],
                        ignore_index=True)
    out = c1_news_buckets.buckets_reading(nulled, results, "2026-27")
    assert out["n"] == 3 and out["buckets"]["zeros"]["n"] == 1


def test_the_bar_is_read_on_the_unrounded_gain():
    buckets = {name: {"disagree": {"n": 30, "_brier_news": 0.10004,
                                   "_brier_flags": 0.1020,
                                   "brier_news": 0.1000,
                                   "brier_flags": 0.1020}}
               for name in c1_news_buckets.RULE_BUCKETS}
    # The rounded figures show 0.0020; the exact gain is 0.00196.
    assert c1_news_buckets._verdict(buckets).startswith("retire candidate")
