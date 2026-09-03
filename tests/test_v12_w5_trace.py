"""v12 W5 §6.5 — why the plan makes each move.

Accounting, not a counterfactual. Every number here is a term of the MILP's own
objective (milp.py:805-889) evaluated at the plan the solver returned; none of
them is "the plan is this much better than not doing it", which needs a
re-solve, which §6.5 forbids.
"""
from __future__ import annotations

import copy
import dataclasses

import pytest

from gaffer.trace import MoveTrace, WeekTrace, trace_plan

GWS = [5, 6, 7]
POS = {100: "MID", 200: "MID", 300: "DEF", 400: "DEF"}
NAMES = {100: "In", 200: "Out", 300: "DefIn", 400: "DefOut"}
EP = {(100, 5): 6.0, (100, 6): 6.0, (100, 7): 6.0,
      (200, 5): 4.0, (200, 6): 4.0, (200, 7): 4.0,
      (300, 5): 3.0, (300, 6): 3.0, (300, 7): 3.0,
      (400, 5): 2.0, (400, 6): 2.0, (400, 7): 2.0}


def week(gw, buys=(), sells=(), hits=0, chip=None):
    return {"gw": gw, "buys": list(buys), "sells": list(sells), "hits": hits,
            "chip": chip}


def run(weeks, **kw):
    base = dict(gws=GWS, ep_by=EP, positions=POS, names=NAMES, decay=0.5,
                hit_cost=4, ft_value=1.5, itb_value=0.05, free_transfers=1)
    return trace_plan(weeks, **{**base, **kw})


def test_a_swap_is_the_decayed_ep_difference_over_the_rest_of_the_horizon():
    # weeks 5,6,7 at decay 0.5 -> 1 + 0.5 + 0.25 = 1.75 multipliers,
    # difference 2.0 a week: 2.0 * 1.75 = 3.5
    out = run([week(5, buys=[100], sells=[200])])
    assert out[0].moves[0].ep_gain == pytest.approx(3.5)


def test_a_later_week_only_counts_from_its_own_week_onward():
    out = run([week(5), week(6, buys=[100], sells=[200])])
    # weeks 6,7 -> 0.5 + 0.25 = 0.75 multipliers, 2.0 a week: 1.5
    assert out[1].moves[0].ep_gain == pytest.approx(1.5)


def test_the_decay_index_is_the_horizons_and_not_the_weeks():
    """`d = decay ** t_i` indexes T from 0 (milp.py:805). A trace that
    restarted the exponent at each move's own week would price a GW7 buy as if
    it were this week's."""
    out = run([week(7, buys=[100], sells=[200])])
    assert out[0].moves[0].ep_gain == pytest.approx(2.0 * 0.25)


def test_moves_are_paired_by_position():
    out = run([week(5, buys=[100, 300], sells=[400, 200])])
    pairs = {(m.buy_code, m.sell_code) for m in out[0].moves}
    assert pairs == {(100, 200), (300, 400)}


def test_an_unpaired_buy_gets_no_gain_and_says_why():
    out = run([week(5, buys=[100])])
    move = out[0].moves[0]
    assert move.buy_code == 100 and move.sell_code is None
    assert move.ep_gain is None
    assert "pair" in move.note


def test_an_unpaired_side_is_named_with_a_dash_and_not_the_word_None():
    """``names.get(None, str(None))`` prints the string "None" on the board,
    where it reads as a player. The missing half of a swap is an em dash, the
    same as every other unknown this UI prints."""
    out = run([week(5, buys=[100])])
    assert out[0].moves[0].sell_name == "—"
    assert out[0].moves[0].buy_name == "In"


def test_a_code_with_no_ep_in_the_pool_is_None_and_not_zero():
    out = run([week(5, buys=[999], sells=[200])], positions={**POS, 999: "MID"},
              names={**NAMES, 999: "Ghost"})
    assert out[0].moves[0].ep_gain is None
    assert "not in the pool" in out[0].moves[0].note


def test_the_weeks_gain_is_the_sum_of_its_paired_moves():
    out = run([week(5, buys=[100, 300], sells=[400, 200])])
    assert out[0].ep_gain == pytest.approx(
        sum(m.ep_gain for m in out[0].moves))


def test_one_unpriceable_move_makes_the_weeks_total_unknown():
    """Not "the rest of it". A total short by one move is a confident number
    that is wrong by exactly that move, with nothing on the page to say so."""
    out = run([week(5, buys=[100, 300], sells=[200])])
    assert out[0].ep_gain is None


def test_the_hit_cost_is_the_weeks_and_never_a_moves():
    out = run([week(5, buys=[100, 300], sells=[400, 200], hits=1)])
    # `hit_cost * decay**i * hits` at i = 0 — the objective's own charge
    # (milp.py:837), not a rounded-off 4.
    assert out[0].hit_cost == pytest.approx(4 * 0.5 ** 0 * 1)
    # And it is not attributed to a move: a week with two transfers and one
    # hit cannot say which of them bought it, so `MoveTrace` has no such
    # field at all rather than a split one.
    assert "hit_cost" not in {f.name for f in dataclasses.fields(MoveTrace)}


def test_the_hit_cost_is_decayed_like_the_objective_decays_it():
    """`-hit_cost * d * hits[t]` (milp.py:837). A GW7 hit does not cost four
    points of GW5 money."""
    out = run([week(7, buys=[100], sells=[200], hits=1)])
    assert out[0].hit_cost == pytest.approx(4 * 0.25)


def test_free_transfers_run_forward_across_the_plan():
    out = run([week(5, buys=[100], sells=[200]), week(6), week(7)],
              free_transfers=1)
    assert [w.ft_used for w in out] == [1, 0, 0]
    # 1 - 1 + 0 + 1 = 1 after GW5, then + 1 a week, capped at
    # MAX_FREE_TRANSFERS — milp.py:727-737's own recurrence.
    assert [w.ft_after for w in out] == [1, 2, 3]


def test_a_wildcard_week_charges_no_transfer_and_banks_one():
    out = run([week(5, buys=[100, 300], sells=[200, 400], chip="wildcard")],
              free_transfers=1)
    assert out[0].ft_used == 0
    assert out[0].ft_after == 2


def test_the_transfer_friction_is_charged_per_transfer_and_decayed():
    """`-ft_use_penalty * d * nt` (milp.py:867) — the term the plan's first
    draft left out. Omitting a *charge* flatters the move it is charged
    against, which is the one direction an accounting layer must not err in.
    """
    out = run([week(5), week(6, buys=[100, 300], sells=[200, 400])],
              ft_use_penalty=0.2)
    assert out[1].ft_use_penalty == pytest.approx(0.2 * 0.5 * 2)


def test_a_wildcard_week_is_charged_no_transfer_friction():
    """Waived on a wildcard (milp.py:866-868): fifteen transfers there are the
    chip working as designed."""
    out = run([week(5, buys=[100, 300], sells=[200, 400], chip="wildcard")],
              ft_use_penalty=0.2)
    assert out[0].ft_use_penalty == pytest.approx(0.0)


def test_the_terminal_bank_is_valued_only_on_the_last_horizon_week():
    """`(itb_value / 10) * bank[T[-1]]` (milp.py:889) — one term, on one week.
    The bank in an intermediate week is not priced by the objective at all,
    and reporting a value for it would invent a term the solver never had.

    `PlanGw.bank` is in millions and the objective's is in tenths, so the
    coefficient here is `itb_value` rather than `itb_value / 10`.
    """
    out = run([week(5), week(6), week(7)],
              banks={5: 1.0, 6: 1.0, 7: 2.0})
    assert out[0].bank_value is None and out[1].bank_value is None
    assert out[2].bank_value == pytest.approx(0.05 * 2.0)


def test_an_unknown_terminal_bank_is_not_a_zero_valuation():
    """`PlanGw.bank` is None when a move on the way had no price. Zero is
    "fully invested", which is a different fact."""
    out = run([week(5), week(6), week(7)], banks={5: 1.0, 7: None})
    assert out[2].bank_value is None


def test_the_ft_shadow_price_is_flat_without_a_lambda_table():
    out = run([week(5, buys=[100], sells=[200])])
    assert out[0].ft_shadow == pytest.approx(1.5)
    assert out[0].ft_basis == "flat"


def test_the_ft_shadow_price_is_the_lambda_tables_terminal_margin():
    class Lookup:
        empty = False

        def __call__(self, k, t):
            return 0.5 * k + 0.01 * t

    out = run([week(5, buys=[100], sells=[200]), week(6), week(7)],
              ft_lambda=Lookup())
    # terminal count 3 (see the recurrence above),
    # weeks_left = max(1, SEASON_LAST_GW - 7)
    from gaffer.optimize.milp import SEASON_LAST_GW
    assert out[-1].ft_basis == "lambda"
    assert out[-1].ft_shadow == pytest.approx(
        0.5 * 3 + 0.01 * max(1, SEASON_LAST_GW - 7))


def test_an_empty_lambda_lookup_falls_back_to_flat():
    class Lookup:
        empty = True

        def __call__(self, k, t):  # pragma: no cover — never called
            raise AssertionError

    out = run([week(5, buys=[100], sells=[200])], ft_lambda=Lookup())
    assert out[0].ft_basis == "flat"


def test_the_lambda_tilt_is_the_difference_the_tilt_made_to_the_pair():
    out = run([week(5, buys=[100], sells=[200])], lam=0.5,
              cover={100: 1.0, 200: 0.0})
    # tilt_ep scales by (1 + lam*(1-covered)) / (1 + lam): the covered buy is
    # marked down and the uncovered sell is not, so the tilt made this swap
    # *less* attractive and the number is negative.
    assert out[0].moves[0].lambda_tilt < 0


def test_a_neutral_lambda_tilts_nothing():
    out = run([week(5, buys=[100], sells=[200])], lam=0.0, cover={})
    assert out[0].moves[0].lambda_tilt == pytest.approx(0.0)


def test_theta_is_reported_only_for_a_week_that_plays_a_chip():
    out = run([week(5), week(6, chip="wildcard")],
              thresholds={6: 12.5})
    assert out[0].theta is None
    assert out[1].theta == pytest.approx(12.5)


def test_the_price_charge_is_off_when_the_setting_is_off():
    """Orchestrator ruling 1: the charge is computed only when [optimizer]
    price_timing is on. Off, the objective carries no such term, so reporting
    one would price a charge the solver never paid."""
    out = run([week(5), week(6, buys=[100], sells=[200])],
              price_timing=False, price_fall={200: 0.8})
    assert out[1].price_charge is None
    assert "price_timing is off" in out[1].note


def test_the_price_charge_is_absent_when_the_reader_has_no_row():
    """On, but the nightly price log has nothing for this code — an unknown,
    which is not the same fact as a zero chance of a fall."""
    out = run([week(5), week(6, sells=[200])], price_timing=True,
              price_fall={})
    assert out[1].price_charge is None
    assert "not recorded" in out[1].note


def test_the_price_charge_is_the_objectives_own_coefficient_when_it_is():
    out = run([week(5), week(6, buys=[100], sells=[200])],
              price_timing=True, price_fall={200: 0.8})
    assert out[1].price_charge == pytest.approx(0.8 * 0.1 * 0.05)


def test_the_first_week_is_never_charged_price_timing():
    """The term charges a sell *scheduled for a later week*; selling now is
    what it exists to encourage."""
    out = run([week(5, buys=[100], sells=[200])], price_timing=True,
              price_fall={200: 0.8})
    assert out[0].price_charge == pytest.approx(0.0)


def test_the_week_docstring_names_the_terms_it_does_not_attribute():
    """The objective has terms this trace does not carry — the XI, captain and
    vice weightings and the bench seats, all of which depend on the whole
    squad rather than on one swap. A reader who adds these lines up and finds
    they miss the week's xPts must be told why here, not left to guess; the
    board's caption says the same sentence (PlannerBoard.test.tsx).
    """
    doc = (WeekTrace.__doc__ or "").lower()
    assert "captain" in doc and "vice" in doc and "bench" in doc


def test_the_trace_does_not_mutate_a_single_input():
    """The real risk of an accounting layer: an in-place edit of the pool or
    the week dicts that the caller then serves."""
    weeks = [week(5, buys=[100], sells=[200]), week(6)]
    ep, pos, names = dict(EP), dict(POS), dict(NAMES)
    before = copy.deepcopy((weeks, ep, pos, names))
    trace_plan(weeks, gws=list(GWS), ep_by=ep, positions=pos, names=names,
               decay=0.5, hit_cost=4, ft_value=1.5, itb_value=0.05,
               free_transfers=1)
    assert copy.deepcopy((weeks, ep, pos, names)) == before


def test_the_trace_module_is_imported_by_no_solver():
    """The guarantee §6.5's byte-identity gate is really asking for. The trace
    cannot change a decision if nothing that makes one can see it."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "gaffer"
    # ``backtest.py`` joins the list because it re-solves history: a trace read
    # there would price a decision the same way the objective does, which is
    # the one place a "read-only" accounting layer could quietly become an
    # input to a measurement of the model.
    watched = [root / "advise.py", root / "backtest.py",
               *sorted((root / "optimize").glob("*.py"))]
    pattern = re.compile(r"\b(from\s+gaffer\.trace|import\s+gaffer\.trace"
                         r"|from\s+\.\.?trace|from\s+gaffer\s+import\s+trace)")
    guilty = [p.name for p in watched if pattern.search(p.read_text())]
    assert guilty == []


def test_the_types_are_frozen_so_a_caller_cannot_edit_a_trace():
    out = run([week(5, buys=[100], sells=[200])])
    assert isinstance(out[0], WeekTrace)
    assert isinstance(out[0].moves[0], MoveTrace)
    with pytest.raises(Exception):
        out[0].moves[0].ep_gain = 99.0
