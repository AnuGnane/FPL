"""v8b's rails: what the decision loop does when its inputs are not there.

Gate G2 (spec §4). The distinction every case here defends is the one the
whole cycle turns on: **null is not zero**. A lane the model had no opinion on
must not read as a lane the model agreed with me on, because the second is a
grade and the first is an absence of one, and a season summary that adds
absences up as zeros reports discipline the manager never showed.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import ADVICE_HISTORY, REPORTS
from gaffer.config import Config
from gaffer.data import store
from gaffer.review import (grade_gw, load_ledger, reviewable_gws, run_review,
                           season_summary)
from gaffer.web import job_kinds
from gaffer.web.app import create_app

CFG = Config(entry_id=42, league_id=5, current_season="2026-27", sim_n=50)

RESULTS = pd.DataFrame(
    [{"season_idx": 4, "gw": 1, "code": 100 + i, "element": 7 + i,
      "position": pos, "total_points": pts, "minutes": 90}
     for i, (pos, pts) in enumerate(
         [("GKP", 3), ("GKP", 1), ("DEF", 6), ("DEF", 2), ("DEF", 1),
          ("DEF", 0), ("DEF", 4), ("MID", 9), ("MID", 2), ("MID", 1),
          ("MID", 5), ("MID", 0), ("FWD", 7), ("FWD", 1), ("FWD", 2)])])

PLAYERS = pd.DataFrame([{"code": 100 + i, "element": 7 + i}
                        for i in range(15)])

# A legal 4-4-2 out of the fifteen, armband on index 7. See
# tests/test_review_ledger.py for the same fixture and its arithmetic: the
# eleven scores 41, the armband adds 9, and FPL's own gross is therefore 50
# with no hit — so the reconciliation is exact and `reconciled` is True.
XI_INDEX = [0, 2, 3, 4, 6, 7, 8, 9, 10, 12, 13]
BENCH_INDEX = [1, 5, 11, 14]

PICKS = (
    [{"element": 7 + idx, "position": 1 + slot,
      "multiplier": 2 if idx == 7 else 1,
      "is_captain": idx == 7, "is_vice_captain": idx == 12}
     for slot, idx in enumerate(XI_INDEX)]
    + [{"element": 7 + idx, "position": 12 + slot, "multiplier": 0,
        "is_captain": False, "is_vice_captain": False}
       for slot, idx in enumerate(BENCH_INDEX)])

HISTORY = {"current": [{"event": 1, "points": 50, "total_points": 50,
                        "event_transfers": 0, "event_transfers_cost": 0,
                        "points_on_bench": 3}], "chips": []}


class Client:
    def __init__(self, dead=False):
        self.dead = dead

    def get_entry_picks(self, entry_id, gw):
        if self.dead:
            raise RuntimeError("FPL is down")
        return {"picks": PICKS}

    def get_entry_history(self, entry_id):
        if self.dead:
            raise RuntimeError("FPL is down")
        return HISTORY

    def get_entry_transfers(self, entry_id):
        if self.dead:
            raise RuntimeError("FPL is down")
        return []

    def get_league_standings(self, league_id, page=1):
        raise RuntimeError("no league in this fixture")


@pytest.fixture()
def bare(tmp_path, monkeypatch):
    """A clone with results and players, and nothing else at all."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr("gaffer.data.my_entry.RAW_LEAGUE",
                        tmp_path / "data/raw/league")
    store.save(RESULTS, "live/player_gw.parquet")
    store.save(PLAYERS, "live/players.parquet")
    return tmp_path


def _bank(tmp_path, entry=42, season="2026-27", gw=1):
    base = tmp_path / "data/raw/league" / season
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{entry}-{gw}.json").write_text(json.dumps(PICKS))
    (base / f"{entry}-history.json").write_text(json.dumps(HISTORY))


def test_no_banked_picks_and_no_api_reviews_nothing_and_says_so(bare, capsys):
    """The review never invents a squad. A gameweek it cannot read is a
    gameweek it does not grade."""
    assert run_review(CFG, client=Client(dead=True)) == []
    assert load_ledger() == []
    assert "skipped" in capsys.readouterr().out


def test_a_dead_api_still_grades_the_gameweeks_already_banked(bare, capsys):
    """Banking is the only step that needs the network. Once a week is
    banked it is gradeable forever, which is the whole reason for D1."""
    _bank(bare)
    assert run_review(CFG, client=Client(dead=True)) == [1]
    assert [r["gw"] for r in load_ledger()] == [1]


def test_a_gameweek_with_no_surviving_advice_is_null_not_zero(bare):
    """``ADVICE_HISTORY_KEEP`` is 20 and global (spec D2), so this is what
    every early gameweek looks like by October."""
    _bank(bare)
    row = grade_gw(1, cfg=CFG, client=Client())
    assert row["no_advice"] is True
    assert row["model_points"] is None
    assert row["accuracy"] is None
    assert [lane["delta_pts"] for lane in row["lanes"]] == [None] * 4
    assert [lane["label"] for lane in row["lanes"]] == [None] * 4


def test_a_null_lane_adds_nothing_to_the_season_sums(bare):
    _bank(bare)
    run_review(CFG, client=Client())
    summary = season_summary(load_ledger())
    assert summary["lanes"]["captaincy"]["graded"] == 0
    assert summary["lanes"]["captaincy"]["pts"] == 0


def test_the_reconciliation_and_the_hindsight_survive_a_pruned_history(bare):
    """The half of the row that owes nothing to the model stays true."""
    _bank(bare)
    row = grade_gw(1, cfg=CFG, client=Client())
    assert row["reconciled"] is True
    assert row["hindsight"]["points"] > 0


def test_a_gameweek_that_is_not_data_checked_is_never_reviewed(bare, capsys):
    """GW2 is not in the results frame, which is exactly how ``refresh_live``
    represents "FPL has not finalised it"."""
    _bank(bare, gw=2)
    assert run_review(CFG, gw=2, client=Client()) == []
    assert "no final results" in capsys.readouterr().out


def test_a_clone_that_has_never_refreshed_reviews_nothing(tmp_path,
                                                          monkeypatch,
                                                          capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    assert reviewable_gws() == []
    assert run_review(CFG, client=Client()) == []


def test_a_corrupt_ledger_is_rewritten_rather_than_crashing_the_review(bare):
    _bank(bare)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "decision_ledger.json").write_text("{ half a file")
    assert run_review(CFG, client=Client()) == [1]
    assert [r["gw"] for r in load_ledger()] == [1]


def test_a_corrupt_ledger_is_an_empty_state_rather_than_a_router_crash(
        bare):
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "decision_ledger.json").write_text("{ half a file")
    response = TestClient(create_app(),
                          raise_server_exceptions=False).get("/api/review")
    assert response.status_code == 200
    assert response.json() == {"gws": [], "summary": None}


def test_the_empty_review_endpoint_is_a_two_hundred(bare):
    response = TestClient(create_app(),
                          raise_server_exceptions=False).get("/api/review")
    assert response.status_code == 200


def test_the_title_odds_degrade_without_taking_the_grade_with_them(bare):
    """No league, no component parquet, a standings endpoint that raises —
    the row still carries every points number and says why it carries no
    percentage points (spec D4)."""
    _bank(bare)
    ADVICE_HISTORY.mkdir(parents=True, exist_ok=True)
    (ADVICE_HISTORY / "gw1-2026-08-14T09:00:00.json").write_text(json.dumps({
        "gw": 1, "deadline": "2026-08-14T17:30:00Z",
        "xi": [{"code": 100 + i, "name": f"P{i}"} for i in range(11)],
        "bench": [{"code": 111, "name": "P11"}], "captain": {"code": 112},
        "vice": {"code": 107}, "buys": [], "sells": [], "hits": 0,
        "chip_table": []}))
    row = grade_gw(1, cfg=CFG, client=Client())
    assert row["my_points"] is not None
    assert all(lane["delta_pwin"] in (None, 0.0) for lane in row["lanes"])
    assert any("title odds not priced" in n for n in row["notices"])


def test_the_review_job_kind_survives_a_review_that_grades_nothing(bare):
    assert job_kinds.JOB_KINDS["review"]() == {"gws": 0}


def test_the_job_kind_count_is_pinned_on_this_side_too():
    """The frontend pins nine in ``src/types.test.ts``; a kind added on one
    side and not the other is a button that 404s."""
    assert len(job_kinds.JOB_KINDS) == 9


def test_the_protected_ordering_rails_are_carried_forward():
    """Copied from v8a/v8c: the chip table is ordered by gameweek and the
    advice payload's XI is ordered by position, and the review reads both by
    index. A silent reorder upstream would regrade a season."""
    from gaffer.review import LANES, PWIN_LANES

    assert LANES == ("transfers", "captaincy", "bench", "chip")
    assert PWIN_LANES == ("transfers", "captaincy")
