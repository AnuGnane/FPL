"""The league safety strip, and the table it reads.

``league_live_table``'s ``projected`` column has always been
``pre_total + live``, and ``live`` applies no auto-subs. That understated
every entry with a finished blank in it — including, on a bad Saturday, only
mine. v8d lets a caller supply an auto-sub-aware gameweek score as
``projected_live`` and projects from that instead. The change is additive:
a row without the key behaves exactly as it did, which is why the CLI's
``run_live`` and the original table tests are untouched.
"""

from __future__ import annotations

from gaffer.live_gw import league_live_table, safety_margins


def test_projected_still_falls_back_to_live_when_no_projection_is_given():
    """The pinned behaviour, restated where the change is made."""
    rows = [{"entry": 1, "name": "You", "pre_total": 500, "live": 60}]
    assert league_live_table(rows)[0]["projected"] == 560


def test_projected_prefers_the_autosub_aware_score_when_the_caller_has_one():
    rows = [{"entry": 1, "name": "You", "pre_total": 500, "live": 60,
             "projected_live": 66},
            {"entry": 2, "name": "Rival", "pre_total": 505, "live": 60,
             "projected_live": 60}]
    table = league_live_table(rows)
    assert [r["entry"] for r in table] == [1, 2]      # 566 beats 565
    assert table[0]["projected"] == 566
    assert table[0]["delta"] == 1                     # and the arrow follows


def test_extra_row_keys_survive_the_table():
    """``race`` and ``remaining_ep`` ride along to the response model."""
    rows = [{"entry": 1, "name": "You", "pre_total": 1, "live": 1,
             "projected_live": 1, "remaining_ep": 4.5, "race": 5.5}]
    assert league_live_table(rows)[0]["race"] == 5.5


# --- the margins ------------------------------------------------------

TABLE = [
    {"entry": 4, "name": "Leader", "pre_total": 600, "live": 40,
     "projected": 640, "delta": 0},
    {"entry": 3, "name": "Above", "pre_total": 560, "live": 30,
     "projected": 590, "delta": 0},
    {"entry": 1, "name": "You", "pre_total": 540, "live": 40,
     "projected": 580, "delta": 0},
    {"entry": 2, "name": "Below", "pre_total": 520, "live": 45,
     "projected": 565, "delta": 0},
]


def test_the_strip_names_the_rival_above_the_rival_below_and_the_leader():
    strip = safety_margins(TABLE, entry=1)
    assert [s["role"] for s in strip] == ["above", "below", "leader"]
    assert [s["name"] for s in strip] == ["Above", "Below", "Leader"]


def test_a_rival_ahead_reports_what_it_takes_to_pass_him():
    above = safety_margins(TABLE, entry=1)[0]
    assert above["margin"] == 10          # they are ten in front
    assert above["need"] == 11            # eleven takes the place


def test_a_rival_behind_reports_a_negative_margin_and_needs_nothing():
    below = safety_margins(TABLE, entry=1)[1]
    assert below["margin"] == -15
    assert below["need"] == 0


def test_the_leader_is_not_repeated_when_he_is_the_man_immediately_above():
    table = [TABLE[1], TABLE[2], TABLE[3]]      # Above is now the leader
    strip = safety_margins(table, entry=1)
    assert [s["role"] for s in strip] == ["above", "below"]
    assert [s["entry"] for s in strip] == [3, 2]


def test_the_leader_gets_no_row_of_his_own_when_the_leader_is_me():
    strip = safety_margins(TABLE, entry=4)
    assert [s["role"] for s in strip] == ["below"]
    assert strip[0]["margin"] == -50


def test_the_bottom_of_the_league_has_nobody_below():
    strip = safety_margins(TABLE, entry=2)
    assert [s["role"] for s in strip] == ["above", "leader"]


def test_a_one_entry_table_has_no_margins_at_all():
    """No league configured: the players card still renders, the strip does
    not exist."""
    assert safety_margins([{"entry": 1, "name": "You", "projected": 10}],
                          entry=1) == []


def test_an_entry_not_in_the_table_has_no_margins():
    assert safety_margins(TABLE, entry=99) == []
