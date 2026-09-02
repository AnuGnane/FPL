"""§4.3: the second- and third-best plans, and what "distinct" means.

A no-good cut over a plan's move set forbids making all of those moves at
once. Three properties follow and all three are asserted here: an alternative
differs from the incumbent in at least one move; a plan that makes the
incumbent's moves *and another* is also excluded (it is the same decision with
a passenger); and the hold plan — whose move set is empty — is excluded by
"make at least one transfer", because a cut over nothing is infeasible rather
than trivially satisfied.

The gap is an objective gap and is signed. Both are pinned: an EP re-score
would compare plans on a quantity neither was chosen by, and clamping the sign
would hide the case where the incumbent's own coherence constraint cost it the
optimum.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.errors import GafferError
from gaffer.optimize.milp import (ALT_PLAN_MAX, FixedMoves, SolveInput,
                                  alternative_plans, move_set, solve_plan)

GWS = [1, 2]
KW = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
          itb_value=0.05, hit_cost=4)


def _pool() -> pd.DataFrame:
    rows, code = [], 1
    for pos, n in [("GKP", 4), ("DEF", 9), ("MID", 10), ("FWD", 7)]:
        for i in range(n):
            rows.append({"code": code, "position": pos,
                         "team_code": (code % 6) + 1,
                         "cost": 40 + i, "sell": 40 + i,
                         "ep": {1: 1.0 + (code % 7) * 0.3,
                                2: 2.0 + (code % 5) * 0.2}})
            code += 1
    return pd.DataFrame(rows)


OWNED = [1, 2, 5, 6, 7, 8, 9, 14, 15, 16, 17, 18, 22, 23, 24]

HOLDABLE = [1, 2, 5, 6, 7, 8, 9, 14, 15, 16, 17, 18, 24, 25, 27]
"""A squad that is legal to *keep*: 2/5/5/3 and no more than three from any
club. ``OWNED`` above is seven midfielders and one forward, which the solver
must transfer its way out of — fine for every other test here and useless for
the one that needs a hold plan to exist."""


def _state(**kw) -> SolveInput:
    base = dict(owned_codes=list(OWNED), bank=100, free_transfers=2, gws=GWS)
    return SolveInput(**{**base, **kw})


def test_a_plan_carries_no_gap_and_no_alternatives_by_default():
    """The degradation direction: every Plan in the tree is the object it
    was, including the tens of thousands a scenario sweep builds."""
    plan = solve_plan(_pool(), _state(), **KW)
    assert plan.gap is None
    assert plan.alternatives == []


def test_move_set_is_sorted_and_names_both_directions():
    plan = solve_plan(_pool(), _state(), **KW)
    moves = move_set(plan)
    assert moves == sorted(moves)
    assert all(kind in ("in", "out") for kind, _, _ in moves)


def test_the_cut_excludes_the_incumbents_exact_move_set():
    pool, state = _pool(), _state()
    first = solve_plan(pool, state, **KW)
    second = solve_plan(pool, state, **KW, no_good=[move_set(first)])
    assert move_set(second) != move_set(first)


def test_the_cut_also_excludes_a_superset_of_the_incumbents_moves():
    """"The same decision with a passenger" is not a distinct plan. A
    solution containing every cut move is excluded whatever else it does."""
    pool, state = _pool(), _state()
    first = solve_plan(pool, state, **KW)
    cut = move_set(first)
    second = solve_plan(pool, state, **KW, no_good=[cut])
    assert not set(cut).issubset(set(move_set(second)))


def test_a_cut_over_a_hold_plan_forces_at_least_one_transfer():
    """The empty move set. ``sum(nothing) <= -1`` is infeasible, so the cut
    is spelled the other way round."""
    pool = _pool()
    state = _state(owned_codes=list(HOLDABLE), free_transfers=0)
    held = solve_plan(pool, state, **KW, fixed_moves=FixedMoves(
        no_transfer=True))
    assert move_set(held) == []
    moved = solve_plan(pool, state, **KW, no_good=[move_set(held)])
    assert move_set(moved) != []


def test_a_cut_naming_a_player_outside_the_pool_is_refused_by_name():
    with pytest.raises(GafferError, match="not expressible on this board"):
        solve_plan(_pool(), _state(), **KW, no_good=[[("in", 9999, 1)]])


def test_a_cut_naming_a_gameweek_outside_the_horizon_is_refused():
    with pytest.raises(GafferError, match="not expressible on this board"):
        solve_plan(_pool(), _state(), **KW, no_good=[[("in", 3, 9)]])


# --- alternative_plans ----------------------------------------------------

def test_it_returns_two_alternatives_at_a_generous_gap():
    pool, state = _pool(), _state()
    plan = solve_plan(pool, state, **KW)
    alts = alternative_plans(pool, state, plan, max_gap=1e6, **KW)
    assert len(alts) == ALT_PLAN_MAX - 1


def test_every_alternative_is_distinct_from_the_incumbent_and_each_other():
    pool, state = _pool(), _state()
    plan = solve_plan(pool, state, **KW)
    alts = alternative_plans(pool, state, plan, max_gap=1e6, **KW)
    sets = [tuple(move_set(p)) for p in [plan] + alts]
    assert len(set(sets)) == len(sets)


def test_the_gap_is_the_objective_difference_and_is_ordered():
    pool, state = _pool(), _state()
    plan = solve_plan(pool, state, **KW)
    alts = alternative_plans(pool, state, plan, max_gap=1e6, **KW)
    for alt in alts:
        assert alt.gap == pytest.approx(plan.objective - alt.objective,
                                        abs=1e-3)
    assert alts[0].gap <= alts[1].gap


def test_a_tight_gap_stops_the_search_early():
    pool, state = _pool(), _state()
    plan = solve_plan(pool, state, **KW)
    assert alternative_plans(pool, state, plan, max_gap=1e-6, **KW) == []


def test_a_gap_of_zero_solves_nothing_at_all(monkeypatch):
    """The off switch has to be free. A knob that spent two MILPs and threw
    the answers away would be a preference, not a switch."""
    import gaffer.optimize.milp as milp_mod

    pool, state = _pool(), _state()
    plan = solve_plan(pool, state, **KW)
    monkeypatch.setattr(milp_mod, "_solve_once",
                        lambda *a, **k: pytest.fail("must not solve"))
    assert alternative_plans(pool, state, plan, max_gap=0.0, **KW) == []


def test_the_gap_can_be_negative_when_the_incumbent_was_constrained():
    """Plan A is ``coherent_plan``'s — the best plan *containing the sweep's
    moves*. An alternative solved without that constraint can beat it, and the
    sign is the only thing that says so."""
    pool, state = _pool(), _state()
    # A deliberately poor forced move, standing in for a sweep that voted for
    # something the raw optimum did not want. Asserted poor rather than
    # assumed: the unconstrained optimum must actually be worth more, or the
    # negative gap below would be proving nothing about the sign.
    constrained = solve_plan(pool, state, **KW,
                             fixed_moves=FixedMoves(buys=[4], sells=[1]))
    assert solve_plan(pool, state, **KW).objective > constrained.objective
    alts = alternative_plans(pool, state, constrained, max_gap=1e6, **KW)
    assert any(alt.gap < 0 for alt in alts)


def test_the_lp_golden_still_matches_with_no_cuts(tmp_path):
    """Task 1's guard, re-run: ``no_good=None`` must add nothing to the
    model."""
    from tests.test_v12_w3_force_out import GOLDEN, _capture_lp, _state as st

    assert _capture_lp(tmp_path, st())[0] == GOLDEN.read_text()
