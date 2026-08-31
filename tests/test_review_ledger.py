"""``gaffer review``: what it banks, what it refuses to bank twice, and the
season sums it adds up.

Grades are banked at review time and never re-derived (spec D2), because
``ADVICE_HISTORY_KEEP`` is 20 runs *globally* — GW1's advice is gone by
October and a May season review that recomputed from history would find
nothing to recompute from.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from gaffer.artifacts import ADVICE_HISTORY, REPORTS
from gaffer.config import Config
from gaffer.data import store
from gaffer.review import (append_ledger, format_review, ledger_path,
                           load_ledger, run_review, season_summary)

CFG = Config(entry_id=42, league_id=5, current_season="2026-27", sim_n=50)

PLAYER_GW = pd.DataFrame(
    [{"season_idx": 4, "gw": gw, "code": 100 + i, "element": 7 + i,
      "position": pos, "total_points": pts, "minutes": 90}
     for gw in (1, 2)
     for i, (pos, pts) in enumerate(
         [("GKP", 3), ("GKP", 1), ("DEF", 6), ("DEF", 2), ("DEF", 1),
          ("DEF", 0), ("DEF", 4), ("MID", 9), ("MID", 2), ("MID", 1),
          ("MID", 5), ("MID", 0), ("FWD", 7), ("FWD", 1), ("FWD", 2)])])

PLAYERS = pd.DataFrame([{"code": 100 + i, "element": 7 + i}
                        for i in range(15)])

# The eleven I fielded, as indices into the fifteen above: one keeper, four
# defenders, four midfielders, two forwards — a legal 4-4-2. Codes are
# 100 + index. The armband is on index 7 (a midfielder, nine points).
XI_INDEX = [0, 2, 3, 4, 6, 7, 8, 9, 10, 12, 13]
BENCH_INDEX = [1, 5, 11, 14]

MY_PICKS = (
    [{"element": 7 + idx, "position": 1 + slot,
      "multiplier": 2 if idx == 7 else 1,
      "is_captain": idx == 7, "is_vice_captain": idx == 12}
     for slot, idx in enumerate(XI_INDEX)]
    + [{"element": 7 + idx, "position": 12 + slot, "multiplier": 0,
        "is_captain": False, "is_vice_captain": False}
       for slot, idx in enumerate(BENCH_INDEX)])

# My eleven scores 3+6+2+1+4+9+2+1+5+7+1 = 41, plus 9 again for the armband
# = 50. ``points`` is gross of the hit and there is no hit, so the official
# net is 50 and the reconciliation is exact. The bench is 1+0+0+2 = 3.
HISTORY = {"current": [
    {"event": 1, "points": 50, "total_points": 50, "event_transfers": 0,
     "event_transfers_cost": 0, "points_on_bench": 3},
    {"event": 2, "points": 50, "total_points": 100, "event_transfers": 0,
     "event_transfers_cost": 0, "points_on_bench": 3}], "chips": []}

ADVICE = {"gw": 2, "deadline": "2026-08-21T17:30:00Z",
          "xi": [{"code": 100 + i, "name": f"P{i}",
                  "position": PLAYER_GW.iloc[i]["position"]}
                 for i in range(11)],
          "bench": [{"code": 111, "name": "P11", "position": "MID"},
                    {"code": 112, "name": "P12", "position": "FWD"},
                    {"code": 113, "name": "P13", "position": "FWD"},
                    {"code": 101, "name": "P1", "position": "GKP"}],
          "captain": {"code": 112, "name": "P12"},
          "vice": {"code": 107, "name": "P7"},
          "buys": [], "sells": [], "hits": 0, "chip_table": []}


class FakeClient:
    def get_entry_picks(self, entry_id, gw):
        return {"picks": MY_PICKS}

    def get_entry_history(self, entry_id):
        return HISTORY

    def get_entry_transfers(self, entry_id):
        return []

    def get_league_standings(self, league_id, page=1):
        raise RuntimeError("no league in this fixture")


@pytest.fixture()
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr("gaffer.data.my_entry.RAW_LEAGUE",
                        tmp_path / "data/raw/league")
    store.save(PLAYER_GW, "live/player_gw.parquet")
    store.save(PLAYERS, "live/players.parquet")
    ADVICE_HISTORY.mkdir(parents=True, exist_ok=True)
    (ADVICE_HISTORY / "gw2-2026-08-21T09:00:00.json").write_text(
        json.dumps(ADVICE))
    return tmp_path


def test_the_ledger_starts_empty_rather_than_missing(here):
    assert load_ledger() == []


def test_a_row_lands_under_reports_and_reads_back(here):
    append_ledger({"gw": 3, "my_points": 50})
    assert ledger_path() == REPORTS / "decision_ledger.json"
    assert load_ledger() == [{"gw": 3, "my_points": 50}]


def test_a_second_row_for_one_gameweek_replaces_the_first(here):
    """``append_sim_history``'s rule: a gameweek is reviewed once, and a
    re-review supersedes rather than duplicates."""
    append_ledger({"gw": 3, "my_points": 50})
    append_ledger({"gw": 3, "my_points": 61})
    assert [r["my_points"] for r in load_ledger()] == [61]


def test_the_ledger_stays_sorted_by_gameweek(here):
    append_ledger({"gw": 5, "my_points": 1})
    append_ledger({"gw": 2, "my_points": 2})
    assert [r["gw"] for r in load_ledger()] == [2, 5]


def test_the_write_is_atomic_and_leaves_no_temp_file(here):
    append_ledger({"gw": 3, "my_points": 50})
    assert not list(REPORTS.glob("decision_ledger.json*.tmp"))


def test_a_corrupt_ledger_is_rebuilt_rather_than_crashing_anything(here):
    REPORTS.mkdir(exist_ok=True)
    ledger_path().write_text("{ this is not json")
    assert load_ledger() == []
    append_ledger({"gw": 3, "my_points": 50})
    assert [r["gw"] for r in load_ledger()] == [3]


def test_a_nan_never_reaches_the_ledger(here):
    """``allow_nan=False``: NaN is not JSON, and a file the browser cannot
    parse is a Model hub that shows nothing at all."""
    with pytest.raises(ValueError):
        append_ledger({"gw": 3, "my_points": float("nan")})


def test_the_review_grades_every_finished_gameweek(here, capsys):
    done = run_review(CFG, client=FakeClient())
    assert done == [1, 2]
    assert [r["gw"] for r in load_ledger()] == [1, 2]
    out = capsys.readouterr().out
    assert out.count("GW1") >= 1
    assert "GW2" in out


def test_the_review_banks_my_picks_before_it_grades_them(here):
    run_review(CFG, client=FakeClient())
    assert (here / "data/raw/league/2026-27/42-2.json").is_file()
    assert (here / "data/raw/league/2026-27/42-history.json").is_file()


def test_a_gameweek_with_no_surviving_advice_is_marked_rather_than_skipped(
        here):
    """GW1's advice was pruned weeks ago (spec D2). The row still carries the
    reconciliation and the hindsight eleven, which need no model at all."""
    run_review(CFG, client=FakeClient())
    row = next(r for r in load_ledger() if r["gw"] == 1)
    assert row["no_advice"] is True
    assert row["accuracy"] is None
    assert row["hindsight"]["points"] > 0


def test_a_second_run_reviews_nothing_and_says_so(here, capsys):
    run_review(CFG, client=FakeClient())
    capsys.readouterr()
    assert run_review(CFG, client=FakeClient()) == []
    assert "already reviewed" in capsys.readouterr().out


def test_naming_a_gameweek_re_reviews_it(here):
    run_review(CFG, client=FakeClient())
    assert run_review(CFG, gw=2, client=FakeClient()) == [2]


def test_a_gameweek_whose_results_are_not_final_is_never_reviewed(here,
                                                                  capsys):
    """Only ``data_checked`` weeks (spec §6). GW3 is not in the results
    frame, so there is nothing to grade and nothing to bank."""
    assert run_review(CFG, gw=3, client=FakeClient()) == []
    assert "no final results" in capsys.readouterr().out


def test_an_unbanked_and_unfetchable_gameweek_is_skipped_not_fabricated(
        here, capsys):
    class Dead(FakeClient):
        def get_entry_picks(self, entry_id, gw):
            raise RuntimeError("FPL is down")

    assert run_review(CFG, client=Dead()) == []
    assert load_ledger() == []
    assert "skipped" in capsys.readouterr().out


def test_the_review_never_raises_whatever_happens(here, capsys):
    class Exploding:
        def get_entry_picks(self, *a, **kw):
            raise RuntimeError("boom")

        def get_entry_history(self, *a, **kw):
            raise RuntimeError("boom")

        def get_entry_transfers(self, *a, **kw):
            raise RuntimeError("boom")

    assert run_review(CFG, client=Exploding()) == []


def test_the_summary_of_an_empty_ledger_is_none(here):
    assert season_summary([]) is None


def test_the_summary_sums_each_lane_in_both_currencies():
    ledger = [
        {"gw": 1, "my_points": 50, "accuracy": 90, "points_on_bench": 3,
         "our_bench_points": 3, "hindsight": {"gap": 8}, "reconciled": True,
         "lanes": [{"lane": "transfers", "delta_pts": -3, "delta_pwin": -0.4,
                    "label": "Inaccuracy"},
                   {"lane": "captaincy", "delta_pts": 5, "delta_pwin": 0.2,
                    "label": "Brilliant"},
                   {"lane": "bench", "delta_pts": 0, "delta_pwin": 0.0,
                    "label": "Aligned"},
                   {"lane": "chip", "delta_pts": None, "delta_pwin": None,
                    "label": None}]},
        {"gw": 2, "my_points": 61, "accuracy": 100, "points_on_bench": 5,
         "our_bench_points": 5, "hindsight": {"gap": 4}, "reconciled": False,
         "lanes": [{"lane": "transfers", "delta_pts": -6, "delta_pwin": -0.1,
                    "label": "Blunder"},
                   {"lane": "captaincy", "delta_pts": 1, "delta_pwin": None,
                    "label": "Good"},
                   {"lane": "bench", "delta_pts": -2, "delta_pwin": 0.0,
                    "label": "Inaccuracy"},
                   {"lane": "chip", "delta_pts": 0, "delta_pwin": 0.0,
                    "label": "Aligned"}]},
    ]
    out = season_summary(ledger)
    assert out["lanes"]["transfers"]["pts"] == -9
    assert out["lanes"]["transfers"]["pwin"] == pytest.approx(-0.5)
    assert out["lanes"]["captaincy"]["pts"] == 6
    assert out["lanes"]["chip"]["pts"] == 0


def test_an_ungraded_lane_adds_nothing_and_is_counted_separately():
    """A null lane is not a zero. Summing it as zero would report a season of
    perfect chip discipline to a manager whose chip weeks were never
    gradeable."""
    ledger = [{"gw": 1, "my_points": 1, "accuracy": None,
               "points_on_bench": 0, "our_bench_points": 0,
               "hindsight": {"gap": 0}, "reconciled": True,
               "lanes": [{"lane": "chip", "delta_pts": None,
                          "delta_pwin": None, "label": None}]}]
    out = season_summary(ledger)
    assert out["lanes"]["chip"]["pts"] == 0
    assert out["lanes"]["chip"]["graded"] == 0


def test_the_summary_names_the_best_and_the_worst_single_decision():
    ledger = [
        {"gw": 1, "my_points": 50, "accuracy": 90, "points_on_bench": 0,
         "our_bench_points": 0, "hindsight": {"gap": 0}, "reconciled": True,
         "lanes": [{"lane": "captaincy", "delta_pts": 12, "delta_pwin": 1.0,
                    "label": "Brilliant"}]},
        {"gw": 2, "my_points": 40, "accuracy": 70, "points_on_bench": 0,
         "our_bench_points": 0, "hindsight": {"gap": 0}, "reconciled": True,
         "lanes": [{"lane": "transfers", "delta_pts": -11, "delta_pwin": -2.0,
                    "label": "Blunder"}]},
    ]
    out = season_summary(ledger)
    assert (out["best"]["gw"], out["best"]["lane"]) == (1, "captaincy")
    assert (out["worst"]["gw"], out["worst"]["lane"]) == (2, "transfers")


def test_the_summary_carries_the_accuracy_series_and_the_totals():
    ledger = [{"gw": 1, "my_points": 50, "accuracy": 90,
               "points_on_bench": 3, "our_bench_points": 4,
               "hindsight": {"gap": 8}, "reconciled": True, "lanes": []},
              {"gw": 2, "my_points": 61, "accuracy": None,
               "points_on_bench": 5, "our_bench_points": 5,
               "hindsight": {"gap": 4}, "reconciled": False, "lanes": []}]
    out = season_summary(ledger)
    assert out["accuracy"] == [{"gw": 1, "accuracy": 90}]
    assert out["points_on_bench"] == 8
    assert out["hindsight_gap"] == 12
    assert out["reconciled_gws"] == 1
    assert out["unreconciled_gws"] == 1


def test_the_printed_line_names_the_gameweek_and_its_worst_lane(here):
    row = {"gw": 2, "my_points": 61, "model_points": 68, "accuracy": 89,
           "reconciled": True, "no_advice": False,
           "lanes": [{"lane": "transfers", "delta_pts": -7,
                      "label": "Blunder", "mine": "no move",
                      "model": "Blank->Guehi", "delta_pwin": -0.3}]}
    line = format_review(row)
    assert "GW2" in line
    assert "61" in line
    assert "transfers" in line


def test_the_printed_line_flags_a_row_that_did_not_reconcile():
    row = {"gw": 2, "my_points": 61, "model_points": 68, "accuracy": 89,
           "reconciled": False, "official_points": 63, "no_advice": False,
           "lanes": []}
    assert "did not reconcile" in format_review(row)
