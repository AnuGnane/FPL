"""scripts/backfill_overall_rank.py, the ledger's null ranks filled (holiday F-33).

A temporary reports directory carries a ledger whose GW1 rank is null and
whose GW2 rank is banked; a temporary raw directory carries the entry
history with both gameweeks' ranks. The config view is the test's own.
"""

from __future__ import annotations

import json
import sys

import pytest

from gaffer import artifacts
from gaffer.config import Config
from gaffer.data.my_entry import my_history_path

sys.path.insert(0, "scripts")

import backfill_overall_rank as bf  # noqa: E402 — scripts/ is not a package; the path insert must come first

SEASON, ENTRY = "2026-27", 42
CFG = Config(entry_id=ENTRY, league_id=5, current_season=SEASON)

LEDGER = [
    {"gw": 1, "season": SEASON, "my_points": 61, "overall_rank": None,
     "projection_snapshot": None, "hindsight": {"captain": 2.0}},
    {"gw": 2, "season": SEASON, "my_points": 55, "overall_rank": 800_000,
     "projection_snapshot": "2026-27-gw2-x.parquet"},
    {"gw": 3, "season": SEASON, "my_points": 70, "overall_rank": None},
    {"gw": 1, "season": "2025-26", "my_points": 40, "overall_rank": None},
]
HISTORY = {"current": [
    {"event": 1, "points": 61, "overall_rank": 1_234_567},
    {"event": 2, "points": 55, "overall_rank": 999_999},
    {"event": 3, "points": 70, "overall_rank": None},
]}


@pytest.fixture()
def tree(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    reports.mkdir()
    monkeypatch.setattr(artifacts, "REPORTS", reports)
    monkeypatch.setattr("gaffer.config.config_in_force", lambda: CFG)
    raw = tmp_path / "raw"
    (reports / "decision_ledger.json").write_text(json.dumps({"gws": LEDGER}))
    path = my_history_path(SEASON, ENTRY, raw)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(HISTORY))
    return reports / "decision_ledger.json", raw


def _rows(ledger):
    return json.loads(ledger.read_text())["gws"]


def test_the_dry_run_names_the_null_cell_and_writes_nothing(tree):
    ledger, raw = tree
    before = ledger.read_text()
    lines = bf.backfill(SEASON, ENTRY, raw_dir=raw)
    assert lines[0] == "BACKFILL_RANK gw=1 was=null now=1234567"
    assert len([ln for ln in lines if ln.startswith("BACKFILL_RANK")]) == 1
    assert "dry run" in lines[-1]
    assert ledger.read_text() == before


def test_write_fills_the_null_cell_and_touches_nothing_else(tree):
    ledger, raw = tree
    bf.backfill(SEASON, ENTRY, write=True, raw_dir=raw)
    rows = {(r["season"], r["gw"]): r for r in _rows(ledger)}
    assert rows[(SEASON, 1)] == {**LEDGER[0], "overall_rank": 1_234_567}
    # A banked rank is not overwritten by the history's different one.
    assert rows[(SEASON, 2)] == LEDGER[1]
    # The history's own null leaves the cell null.
    assert rows[(SEASON, 3)] == LEDGER[2]
    # Another season's row is not this season's to fill.
    assert rows[("2025-26", 1)] == LEDGER[3]
    assert len(rows) == 4


def test_a_second_write_finds_nothing_to_fill(tree):
    ledger, raw = tree
    bf.backfill(SEASON, ENTRY, write=True, raw_dir=raw)
    after = ledger.read_text()
    lines = bf.backfill(SEASON, ENTRY, write=True, raw_dir=raw)
    assert lines == ["no graded row with a null overall_rank that the "
                     "history can fill"]
    assert ledger.read_text() == after


def test_an_absent_rank_key_reads_as_null(tree):
    ledger, raw = tree
    rows = _rows(ledger)
    del rows[0]["overall_rank"]
    ledger.write_text(json.dumps({"gws": rows}))
    assert bf.backfill(SEASON, ENTRY, raw_dir=raw)[0] == \
        "BACKFILL_RANK gw=1 was=null now=1234567"


def test_a_missing_history_prints_a_sentence_and_exits_zero(tree, monkeypatch,
                                                            capsys):
    ledger, raw = tree
    my_history_path(SEASON, ENTRY, raw).unlink()
    before = ledger.read_text()
    monkeypatch.setattr("gaffer.data.my_entry.RAW_LEAGUE", raw)
    assert bf.main(["--write"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1 and "no banked entry history" in out[0]
    assert ledger.read_text() == before


def test_an_unreadable_history_is_the_same_sentence(tree):
    _, raw = tree
    my_history_path(SEASON, ENTRY, raw).write_text("{not json")
    lines = bf.backfill(SEASON, ENTRY, raw_dir=raw)
    assert len(lines) == 1 and "missing or unreadable" in lines[0]


def test_main_reads_the_season_and_entry_in_force(tree, monkeypatch, capsys):
    ledger, raw = tree
    monkeypatch.setattr("gaffer.data.my_entry.RAW_LEAGUE", raw)
    assert bf.main([]) == 0
    out = capsys.readouterr().out
    assert "BACKFILL_RANK gw=1 was=null now=1234567" in out
    assert _rows(ledger)[0]["overall_rank"] is None
