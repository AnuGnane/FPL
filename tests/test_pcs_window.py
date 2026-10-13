"""scripts/pcs_window.py, ``p_cs`` on a two-gameweek window (holiday F-26).

A temporary tree of graded rows, banked components and fixtures: two full
gameweeks with a double gameweek in the second, a gameweek whose artifact was
written after the whistle, and a gameweek with no artifact, so every reason
and both verdicts are seen to be reached.
"""

from __future__ import annotations

import json
import sys

import pandas as pd
import pytest

sys.path.insert(0, "scripts")

import pcs_window  # noqa: E402 — scripts/ is not a package; the path insert must come first

FUTURE = "2099-08-{day:02d}T14:00:00Z"
PAST = "2000-08-{day:02d}T14:00:00Z"


def _matches(gw, n, *, stamp=FUTURE, extra=()):
    """``n`` matches in ``gw``, club ``2i+1`` at home to ``2i+2``; the home
    side keeps a clean sheet, the away side concedes one. ``extra`` adds
    ``(home, away, day)`` matches, a double gameweek's second leg."""
    pairs = [(2 * i + 1, 2 * i + 2, gw) for i in range(n)] + list(extra)
    return [(h, a, stamp.format(day=day)) for h, a, day in pairs]


def _tree(tmp_path, weeks, *, components=None, season="2026-27"):
    """``weeks`` maps gw to its matches; ``components`` names the gameweeks
    that bank an artifact (all by default)."""
    truth, fixtures = [], []
    reports = tmp_path / "reports"
    reports.mkdir()
    for gw, matches in weeks.items():
        comp = []
        for home, away, kickoff in matches:
            fixtures.append({"gw": gw, "kickoff_time": kickoff})
            for club, opp, conceded in ((home, away, 0), (away, home, 1)):
                code = club * 100
                truth.append({"season": season, "gw": gw, "code": code,
                              "opp_code": opp, "kickoff_time": kickoff,
                              "minutes": 90, "gc": conceded})
                # A substitute who saw no goal: his gc must not decide it.
                truth.append({"season": season, "gw": gw, "code": code + 1,
                              "opp_code": opp, "kickoff_time": kickoff,
                              "minutes": 20, "gc": 0})
                for c in (code, code + 1):
                    comp.append({"code": c, "team_code": club,
                                 "opp_code": opp, "kickoff_time": kickoff,
                                 "p_cs": 0.5})
        if components is None or gw in components:
            pd.DataFrame(comp).to_parquet(reports / f"components_gw{gw}.parquet")
    live = tmp_path / "data" / "live"
    live.mkdir(parents=True)
    pd.DataFrame(truth).to_parquet(live / "player_gw.parquet")
    pd.DataFrame(fixtures).to_parquet(live / "fixtures_all.parquet")
    return tmp_path / "data", reports


def _lines(capsys):
    out = capsys.readouterr().out.splitlines()
    rows = [json.loads(line.split(" ", 1)[1]) for line in out[:-1]]
    assert [line.split(" ", 1)[0] for line in out] == (
        ["PCS_WINDOW"] * len(rows) + ["PCS_WINDOWS"])
    return rows, json.loads(out[-1].split(" ", 1)[1])


def test_two_full_gameweeks_with_a_double_clear_the_floor_and_read_card(
        tmp_path, capsys):
    data, reports = _tree(tmp_path, {
        1: _matches(1, 8),
        # Club 1 meets club 2 again on another day: two club-fixtures each.
        2: _matches(2, 7, extra=[(1, 2, 9)]),
    })
    pcs_window.main(data, reports)
    rows, summary = _lines(capsys)
    assert len(rows) == 1
    window = rows[0]
    assert window["gws"] == [1, 2] and window["complete"] is True
    assert window["n"] == 16 + 16
    assert window["mean_pred"] == 0.5 and window["observed"] == 0.5
    assert window["brier"] == 0.25
    assert window["log_loss"] == pytest.approx(0.6931, abs=1e-4)
    assert summary["verdict"] == "card" and summary["min_complete_n"] == 32
    assert summary["floor"] == 30 and summary["season"] == "2026-27"


def test_an_after_the_whistle_artifact_is_excluded_and_its_window_is_incomplete(
        tmp_path, capsys):
    data, reports = _tree(tmp_path, {
        1: _matches(1, 8), 2: _matches(2, 8),
        3: _matches(3, 8, stamp=PAST), 4: _matches(4, 8),
    })
    pcs_window.main(data, reports)
    rows, summary = _lines(capsys)
    assert [r["gws"] for r in rows] == [[1, 2], [3, 4]]
    assert rows[1]["complete"] is False and rows[1]["graded"] == [4]
    assert rows[1]["n"] == 16
    assert summary["excluded"] == [{"gw": 3,
                                    "reason": pcs_window.POST_HOC_REASON}]
    # The incomplete window's 16 does not count against the floor.
    assert summary["complete"] == 1 and summary["verdict"] == "card"


def test_a_complete_window_under_the_floor_reads_hold(tmp_path, capsys):
    data, reports = _tree(tmp_path, {1: _matches(1, 7), 2: _matches(2, 7)})
    pcs_window.main(data, reports)
    rows, summary = _lines(capsys)
    assert rows[0]["n"] == 28 and summary["verdict"] == "hold"


def test_missing_components_print_the_line_with_n_zero_and_a_reason(
        tmp_path, capsys):
    data, reports = _tree(tmp_path, {1: _matches(1, 8), 2: _matches(2, 8)},
                          components=())
    pcs_window.main(data, reports)
    rows, summary = _lines(capsys)
    assert rows[0]["n"] == 0 and rows[0]["reason"]
    assert summary["missing"] == [1, 2] and summary["n"] == 0
    assert summary["verdict"] == "insufficient" and summary["reason"]


def test_missing_results_print_the_summary_alone_with_a_reason(
        tmp_path, capsys):
    pcs_window.main(tmp_path / "data", tmp_path / "reports")
    rows, summary = _lines(capsys)
    assert rows == [] and summary["n"] == 0
    assert "player_gw.parquet" in summary["reason"]


def test_last_seasons_rows_are_not_graded_beside_this_seasons(
        tmp_path, capsys):
    data, reports = _tree(tmp_path, {1: _matches(1, 8), 2: _matches(2, 8)})
    path = data / "live" / "player_gw.parquet"
    frame = pd.read_parquet(path)
    old = frame.assign(season="2025-26", gw=frame["gw"] + 36)
    pd.concat([frame, old]).to_parquet(path)
    pcs_window.main(data, reports)
    rows, summary = _lines(capsys)
    assert [r["gws"] for r in rows] == [[1, 2]]
    assert summary["season"] == "2026-27" and summary["missing"] == []
