"""Banking my own entry: the one thing gaffer has never kept about itself.

``fetch_my_team`` fetches my squad every Thursday and throws it away the
moment the solver has read it, so by December there is no record of what I
actually played in September. The review cannot grade a decision nobody wrote
down, so this module writes it down — in the *same* file layout
``fetch_rival_picks_history`` already uses for everybody else in the league,
because my entry is one of the fifty and there is no reason for it to have a
private format.

Everything here is called from a launchd job, so nothing here raises.
"""

from __future__ import annotations

import json

import pytest

from gaffer.data.my_entry import (bank_my_entry, bank_my_gw, bank_my_history,
                                  bank_my_transfers, chip_for_gw,
                                  gw_history_row, load_my_gw, load_my_history,
                                  load_my_transfers, my_history_path,
                                  my_picks_path, my_transfers_for_gw,
                                  my_transfers_path)

PICKS = [{"element": 7, "position": 1, "multiplier": 2, "is_captain": True,
          "is_vice_captain": False},
         {"element": 8, "position": 12, "multiplier": 0, "is_captain": False,
          "is_vice_captain": True}]

HISTORY = {
    "current": [
        {"event": 1, "points": 62, "total_points": 62, "rank": 1436685,
         "overall_rank": 1436683, "event_transfers": 0,
         "event_transfers_cost": 0, "points_on_bench": 8},
        # points is GROSS of the hit; total_points is cumulative NET.
        # 62 + 101 - 4 == 159, which is the arithmetic the reconciliation
        # gate is built on.
        {"event": 2, "points": 101, "total_points": 159, "rank": 355490,
         "overall_rank": 378985, "event_transfers": 2,
         "event_transfers_cost": 4, "points_on_bench": 0},
    ],
    "chips": [{"name": "bboost", "event": 2,
               "time": "2026-08-28T07:52:00Z"}],
}

TRANSFERS = [
    {"element_in": 9, "element_out": 8, "event": 2, "entry": 42},
    {"element_in": 11, "element_out": 10, "event": 2, "entry": 42},
    {"element_in": 3, "element_out": 4, "event": 3, "entry": 42},
]


class FakeClient:
    def __init__(self, *, dead=False):
        self.dead = dead
        self.picks_calls = []

    def get_entry_picks(self, entry_id, gw):
        self.picks_calls.append((entry_id, gw))
        if self.dead:
            raise RuntimeError("FPL is down")
        return {"picks": PICKS, "active_chip": None,
                "entry_history": HISTORY["current"][1]}

    def get_entry_history(self, entry_id):
        if self.dead:
            raise RuntimeError("FPL is down")
        return HISTORY

    def get_entry_transfers(self, entry_id):
        if self.dead:
            raise RuntimeError("FPL is down")
        return TRANSFERS


@pytest.fixture()
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("gaffer.data.my_entry.RAW_LEAGUE",
                        tmp_path / "data/raw/league")
    return tmp_path


def test_my_picks_land_where_every_other_entry_in_the_league_lands(here):
    """The layout claim, asserted rather than asserted-in-prose: my entry is
    one of the fifty, and ``fetch_rival_picks_history`` must find my file
    already cached rather than fetch it again."""
    bank_my_gw(FakeClient(), 42, "2026-27", 2)
    assert my_picks_path("2026-27", 42, 2) \
        == here / "data/raw/league/2026-27/42-2.json"
    assert my_picks_path("2026-27", 42, 2).is_file()


def test_the_banked_picks_are_the_bare_list_the_rival_cache_holds(here):
    """Not ``{"picks": [...]}``. ``fetch_rival_picks_history`` writes
    ``payload["picks"]`` and reads the file straight back as a list, so a
    dict here would break the very reader this layout exists to share."""
    bank_my_gw(FakeClient(), 42, "2026-27", 2)
    assert json.loads(my_picks_path("2026-27", 42, 2).read_text()) == PICKS


def test_a_banked_gameweek_is_never_fetched_twice(here):
    client = FakeClient()
    bank_my_gw(client, 42, "2026-27", 2)
    bank_my_gw(client, 42, "2026-27", 2)
    assert client.picks_calls == [(42, 2)]


def test_the_picks_read_back_as_they_went_in(here):
    bank_my_gw(FakeClient(), 42, "2026-27", 2)
    assert load_my_gw("2026-27", 42, 2) == PICKS


def test_an_unbanked_gameweek_is_none_not_an_empty_list(here):
    """``None`` is "never banked"; ``[]`` would be "banked and I fielded
    nobody". ``run_review`` reads the difference and skips rather than
    grading a squad of no players."""
    assert load_my_gw("2026-27", 42, 2) is None


def test_a_dead_api_banks_nothing_and_prints_one_line(here, capsys):
    assert bank_my_gw(FakeClient(dead=True), 42, "2026-27", 2) is None
    assert not my_picks_path("2026-27", 42, 2).exists()
    assert "picks for GW2 not banked" in capsys.readouterr().out


def test_the_history_is_replaced_on_write_rather_than_cached(here):
    """The picks of a finished gameweek are a fact; the *history* is
    cumulative and grows a row every week, so caching it permanently would
    freeze the season at whatever week it was first written."""
    bank_my_history(FakeClient(), 42, "2026-27")
    my_history_path("2026-27", 42).write_text(json.dumps({"current": []}))
    bank_my_history(FakeClient(), 42, "2026-27")
    assert len(load_my_history("2026-27", 42)["current"]) == 2


def test_the_history_rewrite_leaves_no_temp_file_behind(here):
    bank_my_history(FakeClient(), 42, "2026-27")
    assert not list(my_history_path("2026-27", 42).parent.glob("*.tmp"))


def test_an_absent_history_reads_as_none(here):
    assert load_my_history("2026-27", 42) is None


def test_a_corrupt_history_reads_as_none_rather_than_raising(here):
    path = my_history_path("2026-27", 42)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    assert load_my_history("2026-27", 42) is None


def test_a_dead_api_leaves_the_history_alone(here, capsys):
    bank_my_history(FakeClient(), 42, "2026-27")
    assert bank_my_history(FakeClient(dead=True), 42, "2026-27") is None
    assert len(load_my_history("2026-27", 42)["current"]) == 2
    assert "entry history not banked" in capsys.readouterr().out


def test_the_gameweek_row_is_the_one_the_reconciliation_reads(here):
    row = gw_history_row(HISTORY, 2)
    assert row["points"] == 101
    assert row["event_transfers_cost"] == 4
    assert row["points_on_bench"] == 0


def test_a_gameweek_the_history_has_no_row_for_is_none(here):
    assert gw_history_row(HISTORY, 9) is None
    assert gw_history_row(None, 2) is None


def test_the_chip_is_read_off_the_history_not_off_the_picks(here):
    """The picks payload carries ``active_chip`` too, but the history's
    ``chips`` list is the one that survives being banked once and read all
    season — and it is the only source for a gameweek whose picks the API
    will no longer serve."""
    assert chip_for_gw(HISTORY, 2) == "bboost"
    assert chip_for_gw(HISTORY, 1) is None
    assert chip_for_gw(None, 2) is None


def test_the_transfers_bank_and_read_back(here):
    bank_my_transfers(FakeClient(), 42, "2026-27")
    assert my_transfers_path("2026-27", 42).is_file()
    assert load_my_transfers("2026-27", 42) == TRANSFERS


def test_the_transfers_are_replaced_on_write_like_the_history(here):
    bank_my_transfers(FakeClient(), 42, "2026-27")
    my_transfers_path("2026-27", 42).write_text("[]")
    bank_my_transfers(FakeClient(), 42, "2026-27")
    assert len(load_my_transfers("2026-27", 42)) == 3


def test_one_gameweeks_transfers_are_the_ones_stamped_with_its_event(here):
    out = my_transfers_for_gw(TRANSFERS, 2)
    assert [(t["element_out"], t["element_in"]) for t in out] \
        == [(8, 9), (10, 11)]


def test_a_gameweek_with_no_transfers_is_an_empty_list(here):
    assert my_transfers_for_gw(TRANSFERS, 1) == []
    assert my_transfers_for_gw(None, 1) == []


def test_banking_the_lot_returns_all_three_pieces(here):
    out = bank_my_entry(FakeClient(), 42, "2026-27", 2)
    assert out["picks"] == PICKS
    assert out["chip"] == "bboost"
    assert out["hits"] == 1
    assert out["history_row"]["points"] == 101
    assert [t["element_in"] for t in out["transfers"]] == [9, 11]


def test_banking_the_lot_with_a_dead_api_is_a_dict_of_nothings(here, capsys):
    """A launchd Tuesday with no network must not take the review down; the
    gameweeks already banked are still gradeable, and this one is not."""
    out = bank_my_entry(FakeClient(dead=True), 42, "2026-27", 2)
    assert out["picks"] is None
    assert out["chip"] is None
    assert out["hits"] == 0
    assert out["history_row"] is None
    assert out["transfers"] == []
    assert "FPL is down" in capsys.readouterr().out
