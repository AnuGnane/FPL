"""What the review reads before it grades anything.

Three readers and no arithmetic: the realized points frame shaped the way
``backtest.score_gw`` wants it, what the model said before the deadline, and
what I actually did. Each answers ``None`` rather than a guess when its source
is not there, because a lane graded against a fabricated counterfactual is
worse than a lane not graded at all.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from gaffer.artifacts import ADVICE_HISTORY
from gaffer.data import store
from gaffer.data.my_entry import my_picks_path
from gaffer.review import (actuals_for_gw, code_of_element, model_decisions,
                           my_decisions, reviewable_gws)

# code 100 plays twice in GW2 (a double gameweek): the frame must come back
# with one row per code, points and minutes summed.
PLAYER_GW = pd.DataFrame([
    {"season_idx": 4, "gw": 2, "code": 100, "element": 7, "position": "MID",
     "total_points": 9, "minutes": 90},
    {"season_idx": 4, "gw": 2, "code": 100, "element": 7, "position": "MID",
     "total_points": 4, "minutes": 62},
    {"season_idx": 4, "gw": 2, "code": 101, "element": 8, "position": "DEF",
     "total_points": 2, "minutes": 90},
    {"season_idx": 4, "gw": 1, "code": 100, "element": 7, "position": "MID",
     "total_points": 6, "minutes": 90},
    {"season_idx": 3, "gw": 2, "code": 100, "element": 7, "position": "MID",
     "total_points": 99, "minutes": 90},
])

PLAYERS = pd.DataFrame([{"code": 100, "element": 7},
                        {"code": 101, "element": 8}])

ADVICE = {
    "gw": 2,
    "deadline": "2026-08-21T17:30:00Z",
    "xi": [{"code": 100, "name": "Salah", "position": "MID"}],
    "bench": [{"code": 101, "name": "Dud", "position": "DEF"}],
    "captain": {"code": 100, "name": "Salah", "position": "MID"},
    "vice": {"code": 101, "name": "Dud", "position": "DEF"},
    "buys": [{"code": 100, "name": "Salah", "position": "MID"}],
    "sells": [{"code": 101, "name": "Dud", "position": "DEF"}],
    "hits": 1,
    "chip_table": [{"chip": "bboost", "gw": 2, "play_now": True},
                   {"chip": "3xc", "gw": 4, "play_now": False}],
}

MY_PICKS = [
    {"element": 7, "position": 1, "multiplier": 2, "is_captain": True,
     "is_vice_captain": False},
    {"element": 8, "position": 12, "multiplier": 0, "is_captain": False,
     "is_vice_captain": True},
]

HISTORY = {"current": [{"event": 2, "points": 20, "total_points": 20,
                        "event_transfers": 1, "event_transfers_cost": 4,
                        "points_on_bench": 3}],
           "chips": [{"name": "3xc", "event": 2}]}


@pytest.fixture()
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr("gaffer.data.my_entry.RAW_LEAGUE",
                        tmp_path / "data/raw/league")
    return tmp_path


def _results():
    store.save(PLAYER_GW, "live/player_gw.parquet")
    store.save(PLAYERS, "live/players.parquet")


def _advice(payload=None, stamp="2026-08-21T09:00:00"):
    payload = ADVICE if payload is None else payload
    ADVICE_HISTORY.mkdir(parents=True, exist_ok=True)
    (ADVICE_HISTORY / f"gw{payload['gw']}-{stamp}.json").write_text(
        json.dumps(payload))


def _mine(season="2026-27", entry=42, gw=2, picks=None, history=None):
    path = my_picks_path(season, entry, gw)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(MY_PICKS if picks is None else picks))
    (path.parent / f"{entry}-history.json").write_text(
        json.dumps(HISTORY if history is None else history))


def test_the_actuals_carry_exactly_the_columns_score_gw_reads(here):
    _results()
    out = actuals_for_gw(2)
    assert list(out.columns) == ["code", "total_points", "minutes", "position"]


def test_a_double_gameweek_is_one_row_per_code_with_the_totals_added(here):
    """``score_gw`` looks a code up in a dict built off this frame, so two
    rows for one code would silently drop one of the two matches — which is
    exactly the join ``backtest`` documents having learned the hard way."""
    _results()
    out = actuals_for_gw(2).set_index("code")
    assert out.loc[100, "total_points"] == 13
    assert out.loc[100, "minutes"] == 152
    assert out.loc[100, "position"] == "MID"


def test_only_the_newest_season_is_read(here):
    """The training frame holds several seasons and a code plays in more than
    one of them. GW2 of 2022-23 is not GW2 of this season."""
    _results()
    assert int(actuals_for_gw(2).set_index("code").loc[100,
                                                       "total_points"]) == 13


def test_a_gameweek_with_no_results_is_an_empty_frame_with_the_columns(here):
    _results()
    out = actuals_for_gw(9)
    assert out.empty
    assert list(out.columns) == ["code", "total_points", "minutes", "position"]


def test_no_results_file_at_all_is_an_empty_frame(here):
    out = actuals_for_gw(2)
    assert out.empty


def test_the_reviewable_gameweeks_are_the_ones_with_final_results(here):
    """``refresh_live`` drops every gameweek FPL has not marked
    ``data_checked``, so the presence of a gameweek in this file *is* the
    data_checked gate (artifacts.ingested_through's reasoning)."""
    _results()
    assert reviewable_gws() == [1, 2]


def test_a_clone_with_no_results_reviews_nothing(here):
    assert reviewable_gws() == []


def test_the_element_to_code_map_comes_from_the_players_table(here):
    _results()
    assert code_of_element() == {7: 100, 8: 101}


def test_the_model_side_is_the_last_run_that_beat_the_deadline(here):
    _results()
    _advice()
    out = model_decisions(2)
    assert out["xi"] == [100]
    assert out["bench"] == [101]
    assert out["captain"] == 100
    assert out["vice"] == 101
    assert out["buys"] == [100]
    assert out["sells"] == [101]
    assert out["hits"] == 1
    assert out["post_deadline"] is False


def test_the_model_chip_is_the_one_the_table_says_to_play_now(here):
    _results()
    _advice()
    assert model_decisions(2)["chip"] == "bboost"


def test_a_chip_table_with_nothing_to_play_now_is_no_chip(here):
    _results()
    payload = {**ADVICE, "chip_table": [{"chip": "bboost", "gw": 5,
                                         "play_now": False}]}
    _advice(payload)
    assert model_decisions(2)["chip"] is None


def test_a_run_banked_after_the_deadline_carries_the_late_flag(here):
    """``latest_run_per_gw`` verbatim (spec D3): a run written after kickoff
    saw the team news and must not pass itself off as foresight."""
    _results()
    _advice(stamp="2026-08-22T09:00:00")
    assert model_decisions(2)["post_deadline"] is True


def test_a_gameweek_with_no_banked_advice_is_none(here):
    """``ADVICE_HISTORY_KEEP`` is 20 and global, so this is not an edge case
    — it is what GW1 looks like by October (spec D2)."""
    _results()
    assert model_decisions(2) is None


def test_the_model_names_come_along_for_the_grade_cards(here):
    _results()
    _advice()
    assert model_decisions(2)["names"][100] == "Salah"


def test_my_side_is_read_off_the_bank_not_off_the_api(here):
    _results()
    _mine()
    out = my_decisions(2, season="2026-27", entry_id=42)
    assert out["xi"] == [100]
    assert out["bench"] == [101]
    assert out["captain"] == 100
    assert out["vice"] == 101
    assert out["chip"] == "3xc"
    assert out["hits"] == 1
    assert out["points_on_bench"] == 3
    assert out["official_gross"] == 20
    assert out["official_cost"] == 4


def test_my_bench_keeps_the_order_the_api_listed_it_in(here):
    """Bench order is a graded lane, so 12-13-14-15 is data, not a set."""
    _results()
    picks = [{"element": 7, "position": 1, "multiplier": 1,
              "is_captain": True, "is_vice_captain": False},
             {"element": 8, "position": 14, "multiplier": 0,
              "is_captain": False, "is_vice_captain": False},
             {"element": 7, "position": 12, "multiplier": 0,
              "is_captain": False, "is_vice_captain": True}]
    _mine(picks=picks)
    assert my_decisions(2, season="2026-27", entry_id=42)["bench"] \
        == [100, 101]


def test_an_unbanked_gameweek_of_mine_is_none(here):
    _results()
    assert my_decisions(2, season="2026-27", entry_id=42) is None


def test_a_pick_whose_element_the_players_table_does_not_know_is_dropped(here):
    """A player who left the game between the gameweek and the review has no
    code to score. Dropping him costs his points; inventing a code would cost
    somebody else's."""
    _results()
    _mine(picks=[{"element": 7, "position": 1, "multiplier": 2,
                  "is_captain": True, "is_vice_captain": False},
                 {"element": 999, "position": 2, "multiplier": 1,
                  "is_captain": False, "is_vice_captain": False}])
    out = my_decisions(2, season="2026-27", entry_id=42)
    assert out["xi"] == [100]
    assert "1 pick could not be resolved to a player" in out["notices"][0]
