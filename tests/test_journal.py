"""The decision journal: what the model said against what you actually did.

A computed join, never manual entry (spec §6.4). Source A is the banked advice
history, source B is the FPL entry API, and the scoring is realized points of
each side's XI and captain.
"""

import json

import pandas as pd
import pytest

from gaffer.artifacts import ADVICE_HISTORY
from gaffer.data import store
from gaffer.journal import (JOURNAL_PATH, build_journal, latest_run_per_gw,
                            xi_points)


class FakeClient:
    def __init__(self, picks):
        self._picks = picks
        self.asked = []

    def get_entry_picks(self, entry_id, gw):
        self.asked.append((entry_id, gw))
        if gw not in self._picks:
            raise RuntimeError(f"no picks for GW{gw}")
        return {"picks": self._picks[gw]}


def _advice(gw, xi_codes, captain_code, buys=()):
    return {
        "gw": gw,
        "xi": [{"code": c, "name": f"P{c}"} for c in xi_codes],
        "captain": {"code": captain_code, "name": f"P{captain_code}"},
        "buys": [{"code": c, "name": f"P{c}"} for c in buys],
        "sells": [],
    }


@pytest.fixture()
def tree(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    ADVICE_HISTORY.mkdir(parents=True, exist_ok=True)
    (ADVICE_HISTORY / "gw3-2026-08-20T09:00:00.json").write_text(
        json.dumps(_advice(3, [1, 2], 1)))
    (ADVICE_HISTORY / "gw3-2026-08-21T09:00:00.json").write_text(
        json.dumps(_advice(3, [1, 3], 3, buys=[3])))
    store.save(pd.DataFrame([
        {"code": 1, "gw": 3, "total_points": 4, "value": 100},
        {"code": 2, "gw": 3, "total_points": 2, "value": 50},
        {"code": 3, "gw": 3, "total_points": 9, "value": 80},
    ]), "live/player_gw.parquet")
    store.save(pd.DataFrame([
        {"code": 1, "element": 11, "name": "P1", "position": "MID",
         "team_id": 1, "team_code": 300, "now_cost": 100, "status": "a",
         "news": "", "chance_of_playing": None, "selected_by_percent": 1.0,
         "form": 1.0, "points_per_game": 1.0, "ep_next": 1.0,
         "price_change_percent": 0.0, "price_change_calibrating": False,
         "penalties_order": None, "direct_freekicks_order": None,
         "corners_and_indirect_freekicks_order": None},
        {"code": 2, "element": 12, "name": "P2", "position": "DEF",
         "team_id": 1, "team_code": 300, "now_cost": 50, "status": "a",
         "news": "", "chance_of_playing": None, "selected_by_percent": 1.0,
         "form": 1.0, "points_per_game": 1.0, "ep_next": 1.0,
         "price_change_percent": 0.0, "price_change_calibrating": False,
         "penalties_order": None, "direct_freekicks_order": None,
         "corners_and_indirect_freekicks_order": None},
        {"code": 3, "element": 13, "name": "P3", "position": "FWD",
         "team_id": 1, "team_code": 300, "now_cost": 80, "status": "a",
         "news": "", "chance_of_playing": None, "selected_by_percent": 1.0,
         "form": 1.0, "points_per_game": 1.0, "ep_next": 1.0,
         "price_change_percent": 0.0, "price_change_calibrating": False,
         "penalties_order": None, "direct_freekicks_order": None,
         "corners_and_indirect_freekicks_order": None},
    ]), "live/players.parquet")
    return tmp_path


def test_xi_points_doubles_the_captain():
    assert xi_points([1, 2], 1, {1: 4, 2: 2}) == 10
    assert xi_points([1, 2], 2, {1: 4, 2: 2}) == 8


def test_xi_points_treats_an_unscored_player_as_zero():
    assert xi_points([1, 9], 1, {1: 4}) == 8


def test_the_newest_run_of_a_gameweek_is_the_one_scored(tree):
    runs = latest_run_per_gw()
    assert set(runs) == {3}
    # Friday's re-run, not Thursday's: it is the last thing the model said
    # before that deadline.
    assert runs[3]["captain"]["code"] == 3


def test_the_journal_scores_the_model_against_what_you_actually_did(tree):
    client = FakeClient({3: [{"element": 11, "is_captain": True,
                              "multiplier": 2, "position": 1},
                             {"element": 12, "is_captain": False,
                              "multiplier": 1, "position": 2}]})
    out = build_journal(client, entry_id=7)
    row = out["rows"][0]
    assert row["gw"] == 3
    # Model: P1 (4) + P3 (9) with P3 captained -> 4 + 9 + 9 = 22
    assert row["model_pts"] == 22
    # Actual: P1 (4, captained) + P2 (2) -> 4 + 4 + 2 = 10
    assert row["actual_pts"] == 10
    assert row["delta"] == 12
    assert row["model_captain"] == "P3"
    assert row["actual_captain"] == "P1"


def test_the_cumulative_series_runs_alongside_the_rows(tree):
    client = FakeClient({3: [{"element": 11, "is_captain": True,
                              "multiplier": 2, "position": 1}]})
    out = build_journal(client, entry_id=7)
    assert out["cumulative"] == [{"gw": 3, "model": 22, "actual": 8,
                                  "delta": 14}]


def test_the_model_transfers_are_listed(tree):
    client = FakeClient({3: [{"element": 11, "is_captain": True,
                              "multiplier": 2, "position": 1}]})
    out = build_journal(client, entry_id=7)
    assert out["rows"][0]["model_buys"] == ["P3"]


def test_a_gameweek_the_api_cannot_answer_is_skipped_not_fatal(tree):
    client = FakeClient({})
    out = build_journal(client, entry_id=7)
    assert out["rows"] == [] and out["cumulative"] == []


def test_a_gameweek_with_no_results_yet_is_skipped(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    ADVICE_HISTORY.mkdir(parents=True, exist_ok=True)
    (ADVICE_HISTORY / "gw9-2026-08-20T09:00:00.json").write_text(
        json.dumps(_advice(9, [1], 1)))
    out = build_journal(FakeClient({}), entry_id=7)
    assert out["rows"] == []


def test_a_cold_clone_builds_an_empty_journal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    out = build_journal(FakeClient({}), entry_id=7)
    assert out == {"rows": [], "cumulative": [], "built_at": out["built_at"]}
    assert not JOURNAL_PATH.exists()
