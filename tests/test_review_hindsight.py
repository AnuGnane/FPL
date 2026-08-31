"""The best eleven I could have fielded, chosen with hindsight.

The gap between this and what I actually scored is "selection EV left on the
table" (spec D5) — the one number in the ledger that owes nothing to the
model and is therefore true whatever happened to the advice history.

Fifteen choose eleven is 1365, so the search is exhaustive and the tests can
ask for the *exact* best rather than for a plausible one.
"""

from __future__ import annotations

import pandas as pd

from gaffer.review import hindsight_xi

POS = {1: "GKP", 2: "GKP",
       3: "DEF", 4: "DEF", 5: "DEF", 6: "DEF", 7: "DEF",
       8: "MID", 9: "MID", 10: "MID", 11: "MID", 12: "MID",
       13: "FWD", 14: "FWD", 15: "FWD"}

SQUAD = list(POS)


def frame(points: dict, minutes: dict | None = None) -> pd.DataFrame:
    minutes = minutes or {code: 90 for code in POS}
    return pd.DataFrame([{"code": code, "total_points": points.get(code, 0),
                          "minutes": minutes.get(code, 0),
                          "position": POS[code]}
                         for code in SQUAD])


def test_the_best_eleven_is_legal_by_formation():
    """Not simply the eleven highest scorers: FPL needs one keeper, three
    defenders and a forward, and an unconstrained pick would field five
    midfielders and no goalkeeper the moment midfielders had a good week."""
    points = {code: 10 for code in (8, 9, 10, 11, 12)}
    xi, _, _ = hindsight_xi(SQUAD, frame(points))
    kinds = [POS[c] for c in xi]
    assert kinds.count("GKP") == 1
    assert 3 <= kinds.count("DEF") <= 5
    assert 2 <= kinds.count("MID") <= 5
    assert 1 <= kinds.count("FWD") <= 3
    assert len(xi) == 11


def test_the_armband_goes_to_the_best_scorer_in_the_chosen_eleven():
    points = {1: 2, 3: 3, 4: 3, 5: 3, 8: 4, 9: 4, 13: 20}
    xi, captain, _ = hindsight_xi(SQUAD, frame(points))
    assert captain == 13
    assert 13 in xi


def test_the_total_counts_the_captain_twice():
    """One goalkeeper at 5 and everyone else at 1: the best legal eleven is
    5 + ten ones, and the armband on the keeper adds his five again."""
    points = {code: 1 for code in SQUAD}
    points[1] = 5
    _, captain, total = hindsight_xi(SQUAD, frame(points))
    assert captain == 1
    assert total == 5 + 10 + 5


def test_a_player_the_actuals_frame_has_never_heard_of_scores_nothing():
    """A player who did not feature at all is worth zero, which is exactly
    what he scored — the same rule ``score_gw`` applies."""
    xi, _, total = hindsight_xi(SQUAD + [999], frame({13: 9}))
    assert total == 9 + 9
    assert 999 not in xi


def test_minutes_do_not_constrain_the_hindsight_pick():
    """No autosubs here, deliberately. Autosubs are a *consequence* of a
    bench order; this measures the selection I could have made at the
    deadline, when a blank was still avoidable by picking somebody else."""
    points = {code: 1 for code in SQUAD}
    points[13] = 20
    _, captain, _ = hindsight_xi(SQUAD, frame(points, minutes={13: 0}))
    assert captain == 13


def test_a_squad_too_small_to_field_a_legal_eleven_is_an_empty_answer():
    """A partially-resolved bank — half its picks were players who have since
    left the game — must give back "no answer", not a nine-man eleven."""
    assert hindsight_xi([1, 3, 4, 8], frame({})) == ([], None, 0)


def test_the_hindsight_pick_never_scores_below_the_eleven_i_played():
    """The definitional property, and the one that makes the gap readable as
    a loss rather than as noise."""
    from gaffer.review import score_squad

    points = {1: 2, 2: 1, 3: 6, 4: 1, 5: 0, 6: 9, 7: 2, 8: 11, 9: 1, 10: 3,
              11: 0, 12: 7, 13: 4, 14: 8, 15: 1}
    actuals = frame(points)
    played = score_squad(actuals, xi=[1, 3, 4, 5, 8, 9, 10, 11, 13, 14, 15],
                         bench=[2, 6, 7, 12], captain=8, vice=13, hits=0)
    _, _, best = hindsight_xi(SQUAD, actuals)
    assert best >= played
