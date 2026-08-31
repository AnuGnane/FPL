"""The auto-sub projection: the substitution FPL *would* make if the rest of
the afternoon went the way it has gone so far.

The real game applies auto-subs once, at full time. ``entry_live_points``
therefore applies none at all, because mid-gameweek a starter on zero minutes
is indistinguishable from one whose match is on Sunday. The projection splits
that ambiguity on the one fact the payload does give: whether the player's own
fixtures are over. A finished blank is a blank forever; an unfinished one is
still anybody's guess and is left alone.
"""

from __future__ import annotations

from gaffer.live_gw import (entry_live_points, projected_multipliers,
                            projected_points, projected_subs)

POS = {1: "GKP", 2: "DEF", 3: "DEF", 4: "DEF", 5: "MID", 6: "MID",
       7: "MID", 8: "MID", 9: "FWD", 10: "FWD", 11: "FWD",
       12: "GKP", 13: "DEF", 14: "MID", 15: "FWD"}


def _picks(captain=9, vice=10, captain_mult=2):
    """A legal 3-5-2 with a four-man bench, in FPL's own pick order."""
    out = []
    for element in range(1, 16):
        mult = 0 if element > 11 else 1
        if element == captain:
            mult = captain_mult
        out.append({"element": element, "position": element,
                    "multiplier": mult,
                    "is_captain": element == captain,
                    "is_vice_captain": element == vice})
    return out


def _minutes(overrides=None):
    """Everyone in the XI on ninety, the bench on nothing, then the overrides.

    Takes a plain dict rather than keywords: the elements are ints and
    ``**{11: 0}`` is not legal Python.
    """
    mins = {e: 90 for e in range(1, 12)}
    mins.update({e: 0 for e in range(12, 16)})
    mins.update(overrides or {})
    return mins


def _finished(*elements):
    return {e: (e in elements) for e in range(1, 16)}


def test_a_finished_blank_is_replaced_by_the_first_legal_bench_player():
    # Forward 11 finished on nothing; bench 12 is a keeper (two in an eleven
    # is not a formation), 13 a defender (four at the back is), so 13 comes
    # on, and his own match has not kicked off yet.
    subs = projected_subs(_picks(), _minutes({11: 0}),
                          _finished(11), POS)
    assert subs == [{"out_element": 11, "in_element": 13,
                     "reason": "yet to play"}]


def test_the_bench_keeper_only_ever_replaces_a_keeper():
    subs = projected_subs(_picks(), _minutes({1: 0, 13: 90, 14: 90}),
                          _finished(1), POS)
    assert [s["in_element"] for s in subs] == [12]


def test_an_outfield_blank_never_takes_the_bench_keeper():
    """13, 14 and 15 all blanked and finished; only the keeper is left, and a
    second keeper in the XI is not a formation."""
    subs = projected_subs(_picks(), _minutes({11: 0}),
                          _finished(11, 13, 14, 15), POS)
    assert subs == []


def test_a_starter_whose_match_is_still_to_come_is_left_alone():
    """The whole point of the module's caveat: zero minutes before kick-off
    is not a blank."""
    assert projected_subs(_picks(), _minutes({11: 0}), _finished(), POS) == []


def test_a_bench_player_who_also_blanked_is_skipped():
    subs = projected_subs(_picks(), _minutes({11: 0}),
                          _finished(11, 13, 14), POS)
    assert [s["in_element"] for s in subs] == [15]


def test_a_bench_player_already_on_is_not_brought_on_twice():
    subs = projected_subs(_picks(), _minutes({10: 0, 11: 0, 13: 90}),
                          _finished(10, 11), POS)
    assert [s["in_element"] for s in subs] == [13, 14]
    assert [s["reason"] for s in subs] == ["played", "yet to play"]


def test_a_squad_that_is_not_eleven_and_four_projects_nothing():
    """A chip week (Bench Boost puts fifteen on the pitch) or a payload read
    mid-write: refuse rather than invent a formation."""
    picks = [dict(p, multiplier=1) for p in _picks()]
    assert projected_subs(picks, _minutes(), _finished(), POS) == []


# --- the armband ------------------------------------------------------


def test_the_vice_inherits_the_armband_from_a_finished_blank_captain():
    picks = _picks(captain=9, vice=10)
    subs = projected_subs(picks, _minutes({9: 0}), _finished(9), POS)
    mult = projected_multipliers(picks, subs, _minutes({9: 0}),
                                 _finished(9))
    assert mult[9] == 0          # subbed off the pitch entirely
    assert mult[10] == 2         # vice doubled


def test_the_triple_captain_armband_moves_at_its_own_multiplier():
    picks = _picks(captain=9, vice=10, captain_mult=3)
    subs = projected_subs(picks, _minutes({9: 0}), _finished(9), POS)
    mult = projected_multipliers(picks, subs, _minutes({9: 0}),
                                 _finished(9))
    assert mult[10] == 3


def test_the_armband_stays_put_while_the_captain_is_still_to_play():
    picks = _picks(captain=9, vice=10)
    mult = projected_multipliers(picks, [], _minutes({9: 0}), _finished())
    assert mult[9] == 2 and mult[10] == 1


def test_the_armband_does_not_pass_to_a_vice_left_on_the_bench():
    """FPL doubles the vice only if he is on the pitch at full time."""
    picks = _picks(captain=9, vice=13)
    subs = projected_subs(picks, _minutes({9: 0, 13: 0}),
                          _finished(9, 13), POS)
    mult = projected_multipliers(picks, subs, _minutes({9: 0, 13: 0}),
                                 _finished(9, 13))
    assert mult[13] == 0


def test_the_incoming_substitute_never_inherits_the_armband():
    """The armband goes to the vice, not to whoever replaced the captain."""
    picks = _picks(captain=11, vice=10)
    subs = projected_subs(picks, _minutes({11: 0}), _finished(11), POS)
    mult = projected_multipliers(picks, subs, _minutes({11: 0}),
                                 _finished(11))
    assert mult[13] == 1
    assert mult[10] == 2


def test_picks_without_captaincy_flags_fall_back_to_the_multiplier():
    """The web payload carries ``is_captain``; some fixtures and older caches
    carry only the multiplier. Read the armband off whichever is there."""
    picks = [{"element": e, "position": e,
              "multiplier": (2 if e == 9 else 0 if e > 11 else 1)}
             for e in range(1, 16)]
    mult = projected_multipliers(picks, [], _minutes({9: 0}), _finished(9))
    assert mult[9] == 1          # armband cannot move: no vice named
    assert 2 not in set(mult.values())


# --- projected points -------------------------------------------------


def test_projected_points_scores_the_substituted_eleven():
    picks = _picks(captain=9, vice=10)
    minutes = _minutes({11: 0})
    finished = _finished(11)
    points = {e: 2 for e in range(1, 16)}
    points[9] = 10          # the captain
    points[11] = 0          # the blank
    bonus = {e: 0 for e in range(1, 16)}
    subs = projected_subs(picks, minutes, finished, POS)
    mult = projected_multipliers(picks, subs, minutes, finished)
    # Nine ordinary starters on 2, the doubled captain, and 13 on for 11.
    assert projected_points(points, bonus, mult) == 9 * 2 + 2 * 10 + 2
    # The pinned figure applies no subs at all, so it is short by exactly the
    # substitute's two points.
    assert entry_live_points(picks, points, bonus) == 9 * 2 + 2 * 10


def test_projected_points_matches_live_points_when_nothing_is_projected():
    picks = _picks()
    points = {e: 3 for e in range(1, 16)}
    bonus = {e: 1 for e in range(1, 16)}
    mult = projected_multipliers(picks, [], _minutes(), _finished())
    assert (projected_points(points, bonus, mult)
            == entry_live_points(picks, points, bonus))
