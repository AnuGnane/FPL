"""scripts/b1_status_age.py, the start share by status age (holiday F-21).

A synthetic snapshot log over two gameweeks: a flag set two days out, one set
ten days out, one never changed, and a gameweek with no results yet, so each
of the age, censoring and grading rules is seen to bite.
"""

from __future__ import annotations

import json
import sys

import pandas as pd

from gaffer.data import store
from gaffer.snapshot import SNAPSHOT_COLS

sys.path.insert(0, "scripts")

import b1_status_age  # noqa: E402 — scripts/ is not a package; the path insert must come first

SEASON = "2026-27"
EVENTS = pd.DataFrame({"gw": [5, 6],
                       "deadline_time": ["2026-09-13T17:30:00Z",
                                         "2026-09-20T17:30:00Z"]})


def _gw(day: int) -> int:
    return 5 if day <= 14 else 6


def _log(spec, days=range(1, 19), season=SEASON):
    """``spec`` maps code to a function of the day giving (status, chance)."""
    rows = []
    for day in days:
        for code, fn in spec.items():
            got = fn(day)
            if got is None:
                continue
            status, chance = got
            rows.append({"season": season, "gw": _gw(day),
                         "snap_date": f"2026-09-{day:02d}", "code": code,
                         "status": status, "chance_of_playing": chance})
    return pd.DataFrame(rows).reindex(columns=SNAPSHOT_COLS)


SPEC = {
    # Flagged doubtful on the 11th, two days before the 13th's deadline.
    1: lambda d: ("a", None) if d < 11 else ("d", 75.0),
    # Injured on the 3rd, ten days out.
    2: lambda d: ("a", None) if d < 3 else ("i", 0.0),
    # Never changed: the log cannot say when it was set.
    3: lambda d: ("a", None),
}

RESULTS = pd.DataFrame({
    "gw": [5, 5, 5, 5],
    "code": [1, 2, 3, 3],
    "minutes": [70, 0, 0, 90],
    "starts": [1, 0, 0, 1],
})
"""Gameweek 5 only: 6 is not graded. Code 3 has a double, starting one."""


def _rows(log=None, results=RESULTS, shadow=None, season=SEASON):
    return b1_status_age.graded_rows(
        _log(SPEC) if log is None else log, results, EVENTS, shadow,
        season).set_index("code")


def test_a_flag_set_two_days_out_is_young_and_ten_days_out_is_old():
    rows = _rows()
    # The last pre-deadline row is the 12th (the deadline day goes whole).
    assert rows.loc[1, "snap_date"] == "2026-09-12"
    assert rows.loc[1, "age_days"] == 1
    assert rows.loc[1, "age_bucket"] == "0-1"
    assert rows.loc[1, "status"] == "d"
    assert rows.loc[2, "age_days"] == 9
    assert rows.loc[2, "age_bucket"] == "8+"


def test_a_never_changed_status_reads_censored_not_zero():
    rows = _rows()
    assert pd.isna(rows.loc[3, "age_days"])
    assert rows.loc[3, "age_bucket"] == "censored"


def test_an_ungraded_gameweek_is_not_scored_and_a_double_is_one_row():
    rows = _rows()
    assert set(rows["gw"]) == {5}
    assert len(rows) == 3
    assert bool(rows.loc[3, "started"]) is True
    assert bool(rows.loc[2, "started"]) is False


def test_a_player_entering_mid_season_reads_censored_until_he_changes():
    spec = {**SPEC, 4: lambda d: None if d < 6 else (
        ("a", None) if d < 12 else ("d", 50.0))}
    results = pd.concat([RESULTS, pd.DataFrame(
        {"gw": [5], "code": [4], "minutes": [90], "starts": [1]})])
    rows = _rows(log=_log(spec), results=results)
    assert rows.loc[4, "age_days"] == 0
    spec[4] = lambda d: None if d < 6 else ("a", None)
    rows = _rows(log=_log(spec), results=results)
    assert rows.loc[4, "age_bucket"] == "censored"


def test_a_chance_change_alone_restarts_the_age_and_a_null_is_a_value():
    spec = {1: lambda d: ("d", 75.0) if d < 9 else ("d", 50.0),
            2: lambda d: ("d", 75.0) if d < 10 else ("d", None)}
    rows = _rows(log=_log(spec))
    assert rows.loc[1, "age_days"] == 3
    assert rows.loc[2, "age_days"] == 2


def test_last_seasons_rows_never_meet_this_seasons_results():
    old = _log({1: lambda d: ("i", 0.0)}, season="2025-26")
    rows = _rows(log=pd.concat([old, _log(SPEC)], ignore_index=True))
    assert rows.loc[1, "status"] == "d"
    assert rows.loc[1, "age_days"] == 1


def test_the_shadow_flags_side_is_averaged_beside_the_share():
    shadow = pd.DataFrame({"season": [SEASON, SEASON, SEASON],
                           "gw": [5, 5, 5], "code": [1, 1, 2],
                           "p_play_flags": [0.1, 0.6, 0.05]})
    out = b1_status_age.status_age_reading(_log(SPEC), RESULTS, EVENTS,
                                           shadow, SEASON)
    d = out["statuses"]["d"]["buckets"]["0-1"]
    # The last banked run of a key is the one kept.
    assert d == {"n": 1, "start_share": 1.0, "n_flags": 1,
                 "mean_p_play_flags": 0.6}
    assert out["statuses"]["a"]["buckets"]["censored"]["n_flags"] == 0
    assert out["verdict"].startswith("insufficient")


def _big(young_share: float, old_share: float):
    """60 players flagged doubtful: 30 two days out, 30 ten days out."""
    spec, codes = {}, []
    for code in range(100, 160):
        start = 11 if code < 130 else 3
        spec[code] = (lambda s: lambda d: ("a", None) if d < s
                      else ("d", 75.0))(start)
        codes.append(code)
    young = int(round(young_share * 30))
    old = int(round(old_share * 30))
    starts = [1 if (c < 130 and c - 100 < young)
              or (c >= 130 and c - 130 < old) else 0 for c in codes]
    results = pd.DataFrame({"gw": 5, "code": codes,
                            "minutes": [90 * s for s in starts],
                            "starts": starts})
    return _log(spec), results


def test_a_wide_gap_within_a_status_is_worth_an_arm():
    log, results = _big(0.8, 0.5)
    out = b1_status_age.status_age_reading(log, results, EVENTS, None, SEASON)
    rule = out["statuses"]["d"]["rule"]
    assert rule == {"young": "0-1", "old": "8+", "gap": 0.3, "passes": True}
    assert out["verdict"].startswith("worth an arm: d 0-1 vs 8+")


def test_a_gap_of_exactly_a_tenth_passes_and_just_under_does_not():
    log, results = _big(0.6, 0.5)
    out = b1_status_age.status_age_reading(log, results, EVENTS, None, SEASON)
    assert out["statuses"]["d"]["rule"]["gap"] == 0.1
    assert out["statuses"]["d"]["rule"]["passes"] is True
    log, results = _big(0.6, 16 / 30)
    out = b1_status_age.status_age_reading(log, results, EVENTS, None, SEASON)
    assert out["statuses"]["d"]["rule"]["passes"] is False


def test_a_double_summed_to_two_starts_still_reads_as_one_start():
    results = RESULTS.assign(starts=[2, 0, 0, 1])
    out = b1_status_age.status_age_reading(_log(SPEC), results, EVENTS,
                                           None, SEASON)
    assert out["statuses"]["d"]["buckets"]["0-1"]["start_share"] == 1.0


def test_a_flat_share_is_not_worth_an_arm():
    log, results = _big(0.6, 0.6)
    out = b1_status_age.status_age_reading(log, results, EVENTS, None, SEASON)
    assert out["statuses"]["d"]["rule"]["passes"] is False
    assert out["verdict"].startswith("not worth an arm")


def test_no_season_reads_no_reading_rather_than_an_uncut_join():
    out = b1_status_age.status_age_reading(_log(SPEC), RESULTS, EVENTS,
                                           None, "")
    assert out["n"] == 0 and "season" in out["reason"]


def test_a_log_without_a_status_column_is_named_not_raised():
    out = b1_status_age.status_age_reading(
        _log(SPEC).drop(columns=["status"]), RESULTS, EVENTS, None, SEASON)
    assert out["n"] == 0 and "status" in out["reason"]


def test_no_readable_deadline_prints_its_reason():
    out = b1_status_age.status_age_reading(
        _log(SPEC), RESULTS, pd.DataFrame(columns=["gw", "deadline_time"]),
        None, SEASON)
    assert out["n"] == 0 and "deadline" in out["reason"]


def test_a_missing_log_prints_the_line_with_n_zero_not_a_traceback(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(b1_status_age, "_season", lambda: SEASON)
    assert b1_status_age.main() == 0
    line = capsys.readouterr().out.strip()
    assert line.startswith("B1_STATUS_AGE ")
    payload = json.loads(line.split(" ", 1)[1])
    assert payload["n"] == 0
    assert payload["reason"] == "no availability snapshots banked"
