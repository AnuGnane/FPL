"""scripts/b8_understat_cover.py, whether Understat still feeds the banked xG
(holiday F-80).

Synthetic frames over three weekly gameweeks: rows for every gameweek with
results, a gameweek with results and no rows for seven days, one whose gap
is younger than that, and no parquet at all.
"""

from __future__ import annotations

import json
import sys

import pandas as pd

from gaffer.data import store

sys.path.insert(0, "scripts")

import b8_understat_cover  # noqa: E402 — scripts/ is not a package; the path insert must come first

EVENTS = pd.DataFrame({
    "gw": [1, 2, 3],
    "deadline_time": ["2026-08-14T17:30:00Z", "2026-08-21T17:30:00Z",
                      "2026-08-28T17:30:00Z"],
})
RESULTS = pd.DataFrame({"gw": [1, 2, 3], "code": 1, "minutes": 90,
                        "total_points": 2})
TEAM = pd.DataFrame({"season": ["2026-27", "2026-27", "2025-26"],
                     "date": ["2026-08-16", "2026-08-23", "2026-08-30"]})
PLAYER = pd.DataFrame({"match_id": [1, 2, 3],
                       "date": ["2026-08-16", "2026-08-30", "2025-08-30"]})


def _read(team, player, today):
    return b8_understat_cover.understat_reading(
        team, player, EVENTS, RESULTS, "2026-27", pd.Timestamp(today))


def test_every_gameweek_with_results_carrying_rows_reads_up():
    out = _read(TEAM, PLAYER, "2026-10-01")
    assert out["team"]["gws"] == [1, 2] and out["player"]["gws"] == [1, 3]
    assert out["player"]["rows"] == 2 and out["team"]["newest"] == "2026-08-23"
    assert out["gaps"] == [] and out["verdict"] == "Understat is up"


def test_a_seven_day_gap_earns_the_fallback_a_spec():
    # GW3 has results and only a last-season player row; it ends 7 days
    # after its deadline (the last), on 2026-09-04.
    out = _read(TEAM, PLAYER.iloc[[0]], "2026-09-11")
    assert out["gaps"] == [{"gw": 3, "days": 7}]
    assert out["verdict"].startswith("the fallback earns a spec")


def test_a_gap_younger_than_seven_days_still_reads_up():
    out = _read(TEAM, PLAYER.iloc[[0]], "2026-09-08")
    assert out["gaps"] == [{"gw": 3, "days": 4}]
    assert out["verdict"] == "Understat is up"


def test_no_parquet_names_the_reason():
    out = _read(None, None, "2026-09-11")
    assert out["reason"] == "no Understat parquet banked"
    assert [g["gw"] for g in out["gaps"]] == [1, 2, 3]


def test_no_season_or_no_deadlines_reads_as_no_reading():
    out = b8_understat_cover.understat_reading(
        TEAM, PLAYER, EVENTS, RESULTS, "", pd.Timestamp("2026-09-11"))
    assert out["verdict"] is None and "season" in out["reason"]
    out = b8_understat_cover.understat_reading(
        TEAM, PLAYER, None, RESULTS, "2026-27", pd.Timestamp("2026-09-11"))
    assert out["verdict"] is None and "deadline" in out["reason"]


def test_main_on_an_empty_store_prints_one_line_and_exits_clean(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(b8_understat_cover, "_season", lambda: "2026-27")
    assert b8_understat_cover.main() == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1 and lines[0].startswith("B8_UNDERSTAT ")
    payload = json.loads(lines[0].removeprefix("B8_UNDERSTAT "))
    assert payload["reason"]
