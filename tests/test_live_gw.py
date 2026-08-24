import httpx
import pytest

from gaffer.config import Config
from gaffer.errors import GafferError
from gaffer.live_gw import (
    active_gameweek,
    entry_live_points,
    league_live_table,
    provisional_bonus,
    run_live,
)

# --- provisional bonus -------------------------------------------------


def _el(eid, fixture, bps, points=0, bonus=0, minutes=90):
    """One element of the event/{gw}/live/ payload.

    `stats` holds the season-to-date-in-this-GW totals; `explain` carries one
    entry per fixture the player featured in, and its `stats` list is where
    the per-fixture `bps` lives (identifier/value pairs).
    """
    return {
        "id": eid,
        "stats": {"total_points": points, "bps": bps, "bonus": bonus,
                  "minutes": minutes},
        "explain": [{"fixture": fixture,
                     "stats": [{"identifier": "minutes", "points": 2,
                                "value": minutes},
                               {"identifier": "bps", "points": 0,
                                "value": bps}]}],
    }


def _fx(fid, started=True, finished=False):
    return {"id": fid, "event": 7, "started": started, "finished": finished}


def test_provisional_bonus_tied_first_pushes_third_to_one_point():
    els = [_el(1, 10, 50), _el(2, 10, 50), _el(3, 10, 40)]
    assert provisional_bonus(els, [_fx(10)]) == {1: 3, 2: 3, 3: 1}


def test_provisional_bonus_tied_second_both_get_two():
    els = [_el(1, 10, 50), _el(2, 10, 40), _el(3, 10, 40)]
    assert provisional_bonus(els, [_fx(10)]) == {1: 3, 2: 2, 3: 2}


def test_provisional_bonus_triple_tie_consumes_every_slot():
    els = [_el(1, 10, 50), _el(2, 10, 50), _el(3, 10, 50), _el(4, 10, 30)]
    assert provisional_bonus(els, [_fx(10)]) == {1: 3, 2: 3, 3: 3, 4: 0}


def test_provisional_bonus_zero_bps_and_outside_top_three_score_nothing():
    els = [_el(1, 10, 30), _el(2, 10, 20), _el(3, 10, 10), _el(4, 10, 5),
           _el(5, 10, 0)]
    bonus = provisional_bonus(els, [_fx(10)])
    assert bonus == {1: 3, 2: 2, 3: 1, 4: 0, 5: 0}


def test_provisional_bonus_is_per_fixture():
    els = [_el(1, 10, 30), _el(2, 10, 20), _el(3, 11, 12), _el(4, 11, 9)]
    bonus = provisional_bonus(els, [_fx(10), _fx(11)])
    assert bonus == {1: 3, 2: 2, 3: 3, 4: 2}


def test_provisional_bonus_skips_fixtures_that_have_not_kicked_off():
    els = [_el(1, 10, 0, minutes=0), _el(2, 10, 0, minutes=0)]
    assert provisional_bonus(els, [_fx(10, started=False)]) == {1: 0, 2: 0}


def test_provisional_bonus_stands_down_once_real_bonus_is_awarded():
    """FPL folds the real bonus into total_points when the match is settled;
    adding a provisional value on top would double-count it."""
    els = [_el(1, 10, 50, bonus=3), _el(2, 10, 40, bonus=2),
           _el(3, 10, 30, bonus=1)]
    assert provisional_bonus(els, [_fx(10, finished=True)]) == {1: 0, 2: 0, 3: 0}


def test_provisional_bonus_falls_back_to_element_bps_when_explain_lacks_it():
    els = [{"id": 1, "stats": {"bps": 40, "bonus": 0, "total_points": 8},
            "explain": [{"fixture": 10, "stats": []}]},
           {"id": 2, "stats": {"bps": 20, "bonus": 0, "total_points": 4},
            "explain": [{"fixture": 10, "stats": []}]}]
    assert provisional_bonus(els, [_fx(10)]) == {1: 3, 2: 2}


def test_provisional_bonus_ignores_elements_with_no_fixture_to_map_to():
    """No explain entry means no fixture, and the live payload carries no team
    id to fall back on — such an element simply scores no provisional bonus."""
    els = [_el(1, 10, 50), {"id": 2, "stats": {"bps": 99}, "explain": []}]
    assert provisional_bonus(els, [_fx(10)]) == {1: 3, 2: 0}


def test_provisional_bonus_ignores_fixtures_from_another_gameweek():
    els = [_el(1, 10, 50), _el(2, 99, 60)]
    assert provisional_bonus(els, [_fx(10)]) == {1: 3, 2: 0}


# --- entry live points -------------------------------------------------


def test_entry_live_points_doubles_the_captain_and_drops_the_bench():
    picks = [
        {"element": 1, "multiplier": 2, "position": 1},   # captain
        {"element": 2, "multiplier": 1, "position": 2},
        {"element": 3, "multiplier": 1, "position": 3},
        {"element": 4, "multiplier": 0, "position": 12},  # bench
    ]
    points = {1: 6, 2: 2, 3: 5, 4: 9}
    bonus = {1: 3, 3: 1}
    # 2*(6+3) + 1*(2+0) + 1*(5+1) = 18 + 2 + 6 = 26; bench 9 ignored
    assert entry_live_points(picks, points, bonus) == 26


def test_entry_live_points_handles_triple_captain_and_missing_elements():
    picks = [{"element": 1, "multiplier": 3, "position": 1},
             {"element": 77, "multiplier": 1, "position": 2}]
    assert entry_live_points(picks, {1: 4}, {1: 3}) == 21


def test_entry_live_points_of_an_untouched_squad_is_zero():
    picks = [{"element": 1, "multiplier": 1, "position": 1}]
    assert entry_live_points(picks, {1: 0}, {}) == 0


# --- projected league table --------------------------------------------


def test_league_live_table_orders_by_projected_total_and_reports_movement():
    rows = [
        {"name": "You", "pre_total": 500, "live": 60},      # 560 -> 1st (was 2nd)
        {"name": "Rival A", "pre_total": 510, "live": 30},  # 540 -> 2nd (was 1st)
        {"name": "Rival B", "pre_total": 480, "live": 20},  # 500 -> 3rd (was 3rd)
    ]
    table = league_live_table(rows)

    assert [r["name"] for r in table] == ["You", "Rival A", "Rival B"]
    assert [r["projected"] for r in table] == [560, 540, 500]
    assert table[0]["delta"] == 1     # climbed one place
    assert table[1]["delta"] == -1    # dropped one place
    assert table[2]["delta"] == 0


def test_league_live_table_leaves_the_input_untouched():
    rows = [{"name": "A", "pre_total": 1, "live": 1}]
    league_live_table(rows)
    assert rows == [{"name": "A", "pre_total": 1, "live": 1}]


def test_league_live_table_handles_no_rows():
    assert league_live_table([]) == []


# --- event status ------------------------------------------------------


def test_active_gameweek_reads_the_event_in_play():
    status = {"status": [{"bonus_added": False, "date": "2026-08-22",
                          "event": 7, "points": "l"}],
              "leagues": "Updating"}
    assert active_gameweek(status) == 7


def test_active_gameweek_is_none_once_the_week_is_settled():
    status = {"status": [{"bonus_added": True, "date": "2026-08-22",
                          "event": 7, "points": "r"}],
              "leagues": "Updated"}
    assert active_gameweek(status) is None


def test_active_gameweek_is_none_for_an_empty_payload():
    assert active_gameweek({"status": [], "leagues": "Updated"}) is None
    assert active_gameweek({}) is None


def test_active_gameweek_stays_live_while_bonus_is_outstanding():
    status = {"status": [{"bonus_added": True, "event": 7, "points": "r"},
                         {"bonus_added": False, "event": 7, "points": "r"}],
              "leagues": "Updated"}
    assert active_gameweek(status) == 7


# --- run_live ----------------------------------------------------------


CFG = Config(entry_id=1, league_id=5)


class _FakeClient:
    """A GW7 in play: three fixtures' worth of nothing but the bits we read."""

    SETTLED = {"status": [{"bonus_added": True, "event": 7, "points": "r"}],
               "leagues": "Updated"}
    LIVE = {"status": [{"bonus_added": False, "event": 7, "points": "l"}],
            "leagues": "Updating"}

    def __init__(self, status=None):
        self.status = status or self.LIVE

    def get_event_status(self):
        return self.status

    def get_event_live(self, gw):
        assert gw == 7
        return {"elements": [_el(1, 10, 50, points=9),
                             _el(2, 10, 40, points=6),
                             _el(3, 10, 12, points=2),
                             _el(4, 11, 30, points=5)]}

    def get_fixtures(self):
        return [_fx(10), _fx(11), {"id": 12, "event": 8, "started": False}]

    def get_league_standings(self, league_id, page=1):
        return {"standings": {"has_next": False, "results": [
            {"entry": 1, "entry_name": "Mine", "player_name": "Me",
             "rank": 1, "last_rank": 1, "total": 510, "event_total": 0},
            {"entry": 2, "entry_name": "Rival A", "player_name": "A",
             "rank": 2, "last_rank": 2, "total": 505, "event_total": 0},
            {"entry": 3, "entry_name": "Ghost", "player_name": "G",
             "rank": 3, "last_rank": 3, "total": 400, "event_total": 0},
        ]}}

    def get_entry_picks(self, entry_id, gw):
        if entry_id == 3:                    # joined late — picks not public
            raise httpx.HTTPStatusError(
                "Not Found", request=httpx.Request("GET", "http://x"),
                response=httpx.Response(404))
        if entry_id == 1:
            return {"entry_history": {"event": 7, "points": 24,
                                      "total_points": 524},
                    "picks": [{"element": 1, "multiplier": 2, "position": 1},
                              {"element": 3, "multiplier": 1, "position": 2},
                              {"element": 4, "multiplier": 0, "position": 12}]}
        return {"entry_history": {"event": 7, "points": 8, "total_points": 513},
                "picks": [{"element": 2, "multiplier": 1, "position": 1},
                          {"element": 4, "multiplier": 1, "position": 2}]}


def test_run_live_reports_my_points_and_the_projected_table(capsys):
    table = run_live(CFG, _FakeClient())
    out = capsys.readouterr().out

    # bonus: fixture 10 -> 1:3, 2:2, 3:1; fixture 11 -> 4:3 (only player)
    # mine  = 2*(9+3) + 1*(2+1) = 27, bench (element 4) ignored
    # rival = 1*(6+2) + 1*(5+3) = 16
    assert [(r["name"], r["live"], r["projected"]) for r in table] == [
        ("You", 27, 527), ("Rival A", 16, 521)]
    assert "GW7" in out
    assert "27" in out and "527" in out
    assert "Rival A" in out and "16" in out and "521" in out
    assert "Ghost" not in out          # 404 picks -> skipped, no crash


def test_run_live_refuses_when_no_gameweek_is_in_progress():
    with pytest.raises(GafferError, match="no gameweek in progress"):
        run_live(CFG, _FakeClient(status=_FakeClient.SETTLED))


def test_run_live_works_with_an_empty_league(capsys):
    class _NoLeague(_FakeClient):
        def get_league_standings(self, league_id, page=1):
            return {"standings": {"has_next": False, "results": []}}

    table = run_live(CFG, _NoLeague())
    assert [r["name"] for r in table] == ["You"]
    assert "27" in capsys.readouterr().out


def test_league_live_table_ranks_duplicate_entry_names_separately():
    """Mini-league entry names are not unique. Keying the pre-gameweek rank
    by name collapsed two rivals called the same thing into one rank, so both
    got the same (wrong) movement arrow."""
    rows = [{"name": "You", "entry": 1, "pre_total": 100, "live": 0},
            {"name": "Twin", "entry": 2, "pre_total": 90, "live": 60},
            {"name": "Twin", "entry": 3, "pre_total": 80, "live": 0}]
    table = league_live_table(rows)
    by_entry = {r["entry"]: r for r in table}
    # Pre order: You(0), Twin#2(1), Twin#3(2).
    # Projected:  Twin#2 150, You 100, Twin#3 80.
    assert [r["entry"] for r in table] == [2, 1, 3]
    assert by_entry[2]["delta"] == 1        # up one
    assert by_entry[1]["delta"] == -1       # down one
    assert by_entry[3]["delta"] == 0        # still last


def test_league_live_table_still_ranks_by_name_without_ids():
    rows = [{"name": "You", "pre_total": 100, "live": 0},
            {"name": "Rival", "pre_total": 90, "live": 60}]
    table = league_live_table(rows)
    assert [r["name"] for r in table] == ["Rival", "You"]
    assert table[0]["delta"] == 1 and table[1]["delta"] == -1


def test_run_live_rows_carry_the_entry_id():
    """Source-level seam: the unique key has to reach league_live_table."""
    import inspect

    from gaffer.live_gw import run_live

    src = inspect.getsource(run_live)
    assert '"entry": int(rival.entry)' in src
    assert '"entry": cfg.entry_id' in src
