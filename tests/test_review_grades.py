"""The four lanes, the five labels, and the gate that says the arithmetic is
FPL's arithmetic.

Every squad in here is small and hand-scored, so a failure names a rule rather
than a number. The actuals frame is the contract ``backtest.score_gw`` reads:
code, total points, minutes, position.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.review import (grade_gw_from, hindsight_gap, label_for,
                           lane_bench, lane_captaincy, lane_chip,
                           lane_transfers, pair_by_position, score_squad,
                           swap_slots)

# A legal fifteen: 2 GKP, 5 DEF, 5 MID, 3 FWD, codes 1..15. Two extras nobody
# starts with: 16 is the defender the model wanted and I never bought, 17 is
# the one I sold to fund my own move.
POS = {1: "GKP", 2: "GKP",
       3: "DEF", 4: "DEF", 5: "DEF", 6: "DEF", 7: "DEF",
       8: "MID", 9: "MID", 10: "MID", 11: "MID", 12: "MID",
       13: "FWD", 14: "FWD", 15: "FWD",
       16: "DEF", 17: "DEF"}

PTS = {1: 6, 2: 1, 3: 2, 4: 5, 5: 1, 6: 0, 7: 9, 8: 12, 9: 3, 10: 2,
       11: 4, 12: 1, 13: 8, 14: 0, 15: 2, 16: 15, 17: 0}

MINS = {code: 90 for code in POS}
MINS[6] = 0          # a blank starter, so autosubs have something to do
MINS[14] = 0         # and a blank bench player, so they cannot use him
MINS[17] = 0


def actuals(points=None, minutes=None) -> pd.DataFrame:
    points = PTS if points is None else points
    minutes = MINS if minutes is None else minutes
    return pd.DataFrame([{"code": code, "total_points": points.get(code, 0),
                          "minutes": minutes.get(code, 0),
                          "position": POS[code]}
                         for code in sorted(POS)])


MY_XI = [1, 3, 4, 5, 6, 8, 9, 10, 11, 13, 15]
MY_BENCH = [2, 7, 12, 14]


def squad(**over) -> dict:
    base = {"xi": list(MY_XI), "bench": list(MY_BENCH), "captain": 8,
            "vice": 13, "hits": 0, "chip": None}
    base.update(over)
    return base


MODEL = {"xi": [1, 3, 4, 5, 16, 8, 9, 10, 11, 13, 15],
         "bench": [2, 12, 7, 14], "captain": 13, "vice": 8,
         "buys": [16], "sells": [6], "hits": 1, "chip": None,
         "names": {6: "Blank", 7: "Sub", 8: "Salah", 13: "Haaland",
                   16: "Guehi", 17: "Sold"},
         "positions": {6: "DEF", 7: "DEF", 8: "MID", 13: "FWD", 16: "DEF",
                       17: "DEF"},
         "post_deadline": False}

MY_SCORE = 66
"""My squad's real score, by hand: 6 blanks, so the first *legal* bench player
comes on — 2 is a keeper and would leave two in the eleven, 7 is a defender
and fits. That gives 1+3+4+5+7+8+9+10+11+13+15 =
6+2+5+1+9+12+3+2+4+8+2 = 54, plus 12 again for the armband on 8."""


def test_a_squad_scores_the_way_the_replay_scores_it():
    """``score_squad`` is a chip-aware wrapper over ``backtest.score_gw`` and
    adds no arithmetic of its own."""
    assert score_squad(actuals(), **squad()) == MY_SCORE


def test_the_triple_captain_triples_and_the_bench_boost_scores_fifteen():
    plain = score_squad(actuals(), **squad())
    assert score_squad(actuals(), **squad(chip="3xc")) == plain + PTS[8]
    # Under a bench boost there are no autosubs: 6 stays on and 7 is a
    # scorer in his own right, so the swap is undone and the bench added.
    boosted = score_squad(actuals(), **squad(chip="bboost"))
    assert boosted == plain - PTS[7] + PTS[6] + PTS[2] + PTS[7] + PTS[12] \
        + PTS[14]


def test_a_hit_costs_four_points_off_the_top():
    assert score_squad(actuals(), **squad(hits=2)) \
        == score_squad(actuals(), **squad()) - 8


def test_a_squad_with_no_armband_at_all_still_scores():
    """A snapshot with no captain flag is rare and must not be a crash."""
    assert score_squad(actuals(), **squad(captain=None, vice=None)) \
        == score_squad(actuals(), **squad()) - PTS[8]


def test_swapping_a_slot_keeps_the_player_where_he_sat():
    xi, bench = swap_slots(MY_XI, MY_BENCH, [(6, 16), (14, 17)])
    assert xi[4] == 16          # 6 sat fifth in the eleven; 16 sits there now
    assert bench == [2, 7, 12, 17]


def test_swapping_a_player_who_is_not_in_the_squad_is_none():
    """The signal the transfers lane needs: the model sold somebody I never
    owned, so there is no counterfactual to build and the lane is null."""
    assert swap_slots(MY_XI, MY_BENCH, [(99, 16)]) is None


def test_buys_and_sells_pair_up_by_position():
    assert pair_by_position([6], [16], MODEL["positions"]) == [(6, 16)]


def test_a_move_that_changes_the_shape_of_the_squad_does_not_pair():
    """Two out, two in, but a defender for a forward: FPL cannot do it and
    neither can the counterfactual."""
    assert pair_by_position([6, 8], [16, 13],
                            {6: "DEF", 8: "MID", 16: "DEF", 13: "FWD"}) is None


def test_the_transfers_lane_prices_my_move_against_the_models():
    """I made no transfer; the model would have paid four points to bring 16
    in for 6. My 66 comes from the autosub that partly covered the blank; the
    model's fifteen is 6+2+5+1+15+12+3+2+4+8+2 = 60, +12 for the armband,
    less the four-point hit = 68. So the model's week was two better."""
    lane = lane_transfers(squad(), MODEL, actuals(), my_transfers=[],
                          positions=MODEL["positions"])
    assert lane["delta_pts"] == -2
    assert lane["note"] is None


def test_the_transfers_lane_undoes_my_move_before_applying_the_models():
    """I sold 17 and bought 7 this week, for a hit. The counterfactual starts
    from the fifteen I owned *at the deadline* — with 17 back on the bench —
    and then applies the model's move to that, not to the squad I ended up
    with. My 66 becomes 62 once my own hit is charged; the model's is still
    68, so the lane is six against me."""
    lane = lane_transfers(
        squad(hits=1), MODEL, actuals(),
        my_transfers=[{"element_in": 7, "element_out": 17, "event": 2}],
        positions=MODEL["positions"], code_of={7: 7, 17: 17})
    assert lane["note"] is None
    assert lane["delta_pts"] == -6


def test_a_model_sale_i_never_owned_is_a_null_lane_not_a_zero_one():
    """"The model had no opinion I could have acted on" and "the model
    agreed with me" are different facts (spec G2)."""
    model = {**MODEL, "sells": [99], "buys": [16],
             "positions": {**MODEL["positions"], 99: "DEF"}}
    lane = lane_transfers(squad(), model, actuals(), my_transfers=[],
                          positions=model["positions"])
    assert lane["delta_pts"] is None
    assert "was not in your squad" in lane["note"]


def test_the_captaincy_lane_is_my_armband_against_the_models():
    """I captained 8 (12 pts); the model said 13 (8 pts). I am four up."""
    lane = lane_captaincy(squad(), MODEL, actuals())
    assert lane["delta_pts"] == 4
    assert lane["mine"] == "Salah"
    assert lane["model"] == "Haaland"


def test_captaining_the_same_player_as_the_model_is_aligned():
    lane = lane_captaincy(squad(captain=13), MODEL, actuals())
    assert lane["delta_pts"] == 0
    assert lane["aligned"] is True


def test_a_model_captain_who_is_not_in_my_eleven_is_a_null_lane():
    """You cannot captain a player you do not own, so there is no squad to
    score — the honest answer is no grade."""
    lane = lane_captaincy(squad(), {**MODEL, "captain": 99}, actuals())
    assert lane["delta_pts"] is None
    assert "was not in your eleven" in lane["note"]


def test_the_bench_lane_prices_the_order_the_autosubs_walked():
    """My bench is [2, 7, 12, 14] and 6 blanks, so 7 comes on for nine. The
    model's order puts 12 ahead of 7, and 12 is a midfielder who also fits —
    so the model's ordering brings on a one-pointer instead."""
    lane = lane_bench(squad(), MODEL, actuals())
    assert lane["delta_pts"] == 8


def test_a_bench_order_that_changes_nothing_is_a_zero_lane_not_a_null_one():
    """Nobody blanked, so no autosub fired. Zero is a real grade here: the
    ordering was tested and cost nothing."""
    lane = lane_bench(squad(), MODEL, actuals(minutes={c: 90 for c in POS}))
    assert lane["delta_pts"] == 0
    assert lane["note"] is None


def test_the_chip_lane_prices_holding_against_playing():
    """The model said bench boost; I held. The boost is worth the bench,
    less the autosub it cancels."""
    lane = lane_chip(squad(), {**MODEL, "chip": "bboost"}, actuals())
    assert lane["delta_pts"] == score_squad(actuals(), **squad()) \
        - score_squad(actuals(), **squad(chip="bboost"))


def test_holding_when_the_model_held_is_aligned():
    lane = lane_chip(squad(), MODEL, actuals())
    assert lane["delta_pts"] == 0
    assert lane["aligned"] is True


def test_a_wildcard_on_either_side_is_a_null_chip_lane():
    """A wildcard changes the fifteen, not the way the fifteen scores, so
    there is no same-squad comparison to make."""
    lane = lane_chip(squad(chip="wildcard"), MODEL, actuals())
    assert lane["delta_pts"] is None
    assert "changes the squad" in lane["note"]


def test_the_labels_are_the_pre_registered_bands():
    assert label_for(6.0, 0.4, aligned=False) == "Brilliant"
    assert label_for(6.0, -0.4, aligned=False) == "Good"
    assert label_for(6.0, None, aligned=False) == "Good"
    assert label_for(2.0, None, aligned=False) == "Good"
    assert label_for(0.5, None, aligned=False) == "Aligned"
    assert label_for(-0.5, None, aligned=False) == "Aligned"
    assert label_for(-2.0, None, aligned=False) == "Inaccuracy"
    assert label_for(-9.0, None, aligned=False) == "Blunder"
    assert label_for(None, None, aligned=False) is None


def test_following_the_model_is_aligned_however_it_turned_out():
    """A lane where I made the model's own choice cannot be a blunder. The
    delta is zero by construction; the flag says *why* it is zero."""
    assert label_for(0.0, None, aligned=True) == "Aligned"


def test_the_hindsight_gap_is_the_selection_ev_left_on_the_table():
    assert hindsight_gap(74, 61) == 13


def test_the_grade_reconciles_against_the_official_score():
    """Spec D7: ``score_gw`` on my real squad must equal FPL's own
    ``points - event_transfers_cost``. ``points`` is gross of the hit."""
    mine = {**squad(hits=1),
            "official_gross": score_squad(actuals(), **squad(hits=0)),
            "official_cost": 4, "points_on_bench": 0, "transfers": [],
            "notices": []}
    row = grade_gw_from(2, mine, MODEL, actuals())
    assert row["my_points"] == mine["official_gross"] - 4
    assert row["official_points"] == mine["official_gross"] - 4
    assert row["reconciled"] is True


def test_a_mismatch_is_flagged_with_both_numbers_and_never_swallowed():
    """The known simplified-autosub caveats (backtest.py:36-38) are the
    expected source; the flag is how their real frequency gets measured."""
    mine = {**squad(), "official_gross": 999, "official_cost": 0,
            "points_on_bench": 0, "transfers": [], "notices": []}
    row = grade_gw_from(2, mine, MODEL, actuals())
    assert row["reconciled"] is False
    assert row["official_points"] == 999
    assert row["my_points"] != 999


def test_an_absent_official_score_is_unreconciled_rather_than_wrong():
    mine = {**squad(), "official_gross": None, "official_cost": 0,
            "points_on_bench": None, "transfers": [], "notices": []}
    row = grade_gw_from(2, mine, MODEL, actuals())
    assert row["reconciled"] is None
    assert "no official score" in " ".join(row["notices"])


def test_the_grade_carries_all_four_lanes_in_the_registered_order():
    mine = {**squad(), "official_gross": 0, "official_cost": 0,
            "points_on_bench": 0, "transfers": [], "notices": []}
    row = grade_gw_from(2, mine, MODEL, actuals())
    assert [lane["lane"] for lane in row["lanes"]] \
        == ["transfers", "captaincy", "bench", "chip"]


def test_accuracy_is_capped_at_a_hundred_when_i_beat_the_model():
    mine = {**squad(), "official_gross": 0, "official_cost": 0,
            "points_on_bench": 0, "transfers": [], "notices": []}
    row = grade_gw_from(2, mine, {**MODEL, "captain": 6, "buys": [],
                                  "sells": [], "hits": 0,
                                  "bench": list(MY_BENCH)}, actuals())
    assert row["accuracy"] == 100


def test_accuracy_is_null_when_there_was_no_advice_to_measure_against():
    mine = {**squad(), "official_gross": 0, "official_cost": 0,
            "points_on_bench": 0, "transfers": [], "notices": []}
    row = grade_gw_from(2, mine, None, actuals())
    assert row["no_advice"] is True
    assert row["accuracy"] is None
    assert row["model_points"] is None
    assert all(lane["delta_pts"] is None for lane in row["lanes"])


def test_a_model_move_i_skipped_that_hauled_is_a_miss_row():
    """Spec D5's Miss: the model flagged 16, I kept 6, and 16 beat him by
    fifteen — over the six-point bar."""
    mine = {**squad(), "official_gross": 0, "official_cost": 0,
            "points_on_bench": 0, "transfers": [], "notices": []}
    row = grade_gw_from(2, mine, MODEL, actuals())
    assert row["misses"] == [{"code": 16, "name": "Guehi", "over": "Blank",
                              "gain": 15}]


def test_a_model_move_i_actually_made_is_never_a_miss():
    mine = {**squad(xi=[1, 3, 4, 5, 16, 8, 9, 10, 11, 13, 15]),
            "official_gross": 0, "official_cost": 0, "points_on_bench": 0,
            "transfers": [], "notices": []}
    assert grade_gw_from(2, mine, MODEL, actuals())["misses"] == []


def test_a_model_move_that_returned_little_is_not_a_miss():
    small = {**PTS, 16: 4}
    mine = {**squad(), "official_gross": 0, "official_cost": 0,
            "points_on_bench": 0, "transfers": [], "notices": []}
    assert grade_gw_from(2, mine, MODEL, actuals(points=small))["misses"] == []


def test_the_late_advice_caveat_rides_on_the_row():
    mine = {**squad(), "official_gross": 0, "official_cost": 0,
            "points_on_bench": 0, "transfers": [], "notices": []}
    row = grade_gw_from(2, mine, {**MODEL, "post_deadline": True}, actuals())
    assert row["post_deadline"] is True


def test_the_bench_points_we_compute_sit_beside_the_official_ones():
    """Spec D5's EV ledger reconciles our bench arithmetic against FPL's own
    rather than trusting either alone."""
    mine = {**squad(), "official_gross": 0, "official_cost": 0,
            "points_on_bench": 11, "transfers": [], "notices": []}
    row = grade_gw_from(2, mine, MODEL, actuals())
    assert row["points_on_bench"] == 11
    assert row["our_bench_points"] == PTS[2] + PTS[7] + PTS[12] + PTS[14]


def test_the_hindsight_row_names_the_best_eleven_i_owned():
    mine = {**squad(), "official_gross": 0, "official_cost": 0,
            "points_on_bench": 0, "transfers": [], "notices": []}
    row = grade_gw_from(2, mine, MODEL, actuals())
    assert row["hindsight"]["points"] >= row["my_points"]
    assert row["hindsight"]["gap"] == row["hindsight"]["points"] \
        - row["my_points"]


def test_an_ungraded_lane_carries_no_win_percentage_either():
    """I2: the bench and chip lanes carry ``0.0`` because the simulation
    genuinely cannot see them — that is a measurement. A lane that could not
    be *built* has no measurement in either currency, and a row that shipped
    ``delta_pts: null`` beside ``delta_pwin: 0.0`` would render as "not
    graded · — pts · +0.0 pp"."""
    mine = {**squad(chip="wildcard"), "official_gross": 0, "official_cost": 0,
            "points_on_bench": 0, "transfers": [], "notices": []}
    row = grade_gw_from(2, mine, MODEL, actuals())
    chip = next(lane for lane in row["lanes"] if lane["lane"] == "chip")
    assert chip["delta_pts"] is None
    assert chip["delta_pwin"] is None
    assert chip["label"] is None
    # The graded ones still carry their zero, which is a real answer.
    bench = next(lane for lane in row["lanes"] if lane["lane"] == "bench")
    assert bench["delta_pwin"] == 0.0
