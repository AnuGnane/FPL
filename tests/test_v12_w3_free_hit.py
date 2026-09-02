"""§4.5: the free hit is priced from the week it is played in.

Three claims, and the third is the one that moves a replay. The chip is scored
from the baseline's squad and bank *in that week* rather than today's; the
hits the baseline would have paid that week are credited, because a free hit
suspends them; and a baseline that cannot say what its bank was falls all the
way back to the pre-v12 number rather than to zero.

``GwPlan.bank`` is what makes the first possible, and it is a number the MILP
has solved for and discarded since v1.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.optimize.chips import chip_baseline, free_hit_gain
from gaffer.optimize.milp import GwPlan, Plan, SolveInput, solve_plan

CFG = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
           itb_value=0.05, hit_cost=4)
GWS = [1, 2]


def _pool() -> pd.DataFrame:
    rows, code = [], 1
    for pos, n in [("GKP", 4), ("DEF", 9), ("MID", 10), ("FWD", 7)]:
        for i in range(n):
            rows.append({"code": code, "position": pos,
                         "team_code": (code % 6) + 1,
                         "cost": 40 + i, "sell": 40 + i,
                         "ep": {g: 1.0 + (code % 7) * 0.3 for g in GWS}})
            code += 1
    return pd.DataFrame(rows)


def _state(**kw) -> SolveInput:
    base = dict(owned_codes=list(range(1, 16)), bank=150, free_transfers=1,
                gws=list(GWS))
    return SolveInput(**{**base, **kw})


def test_a_solved_week_now_carries_its_bank():
    plan = solve_plan(_pool(), _state(), **CFG)
    assert all(gp.bank is not None for gp in plan.gw_plans)
    assert plan.gw_plans[0].bank >= 0


def test_a_bank_of_zero_is_zero_and_not_unknown():
    """Fully invested is a real and common state; reading it as unknown would
    send free_hit_gain back to today's figures on the weeks that spend
    everything."""
    plan = solve_plan(_pool(), _state(bank=0), **CFG)
    banks = [gp.bank for gp in plan.gw_plans]
    assert None not in banks


def test_a_gw_plan_built_without_a_bank_still_builds():
    """Every positional and keyword construction in the tree, unchanged."""
    gp = GwPlan(gw=1, squad=[], xi=[], xi_rows=[], bench=[], captain=1,
                vice=2, buys=[], sells=[], hits=0, expected_pts=0.0)
    assert gp.bank is None


def test_the_gain_credits_the_hits_the_baseline_would_have_paid():
    """A free hit suspends the week's transfers, and expected_pts is gross of
    their cost — so leaving them in made the chip look worthless exactly when
    it had just saved a -8."""
    pool, state = _pool(), _state()
    base = chip_baseline(pool, state, **CFG)
    week = base.gw_plans[0]
    hit_free = Plan(objective=base.objective,
                    gw_plans=[__import__("dataclasses").replace(week, hits=0)]
                    + list(base.gw_plans[1:]))
    with_hits = Plan(objective=base.objective,
                     gw_plans=[__import__("dataclasses").replace(week, hits=2)]
                     + list(base.gw_plans[1:]))
    a = free_hit_gain(pool, state, 1, base=hit_free, **CFG)
    b = free_hit_gain(pool, state, 1, base=with_hits, **CFG)
    assert b - a == pytest.approx(2 * CFG["hit_cost"], abs=1e-6)


def test_the_budget_comes_from_the_baselines_week_and_not_from_today():
    """A baseline whose week holds a cheaper squad and more bank must price a
    different free hit from one that holds an expensive squad."""
    import dataclasses

    pool, state = _pool(), _state()
    base = chip_baseline(pool, state, **CFG)
    poor = dataclasses.replace(base.gw_plans[0],
                               squad=list(range(1, 16)), bank=0.0)
    rich = dataclasses.replace(base.gw_plans[0],
                               squad=list(range(1, 16)), bank=500.0)
    lean = free_hit_gain(pool, state, 1,
                         base=Plan(objective=0.0,
                                   gw_plans=[poor] + list(base.gw_plans[1:])),
                         **CFG)
    flush = free_hit_gain(pool, state, 1,
                          base=Plan(objective=0.0,
                                    gw_plans=[rich] + list(base.gw_plans[1:])),
                          **CFG)
    assert flush > lean


def test_a_baseline_with_no_bank_falls_back_to_todays_position_and_says_so(
        capsys):
    """The pre-v12 number, out loud. Silence here would price a chip off a
    position nobody chose."""
    import dataclasses

    pool, state = _pool(), _state()
    base = chip_baseline(pool, state, **CFG)
    stale = Plan(objective=base.objective,
                 gw_plans=[dataclasses.replace(base.gw_plans[0], bank=None)]
                 + list(base.gw_plans[1:]))
    free_hit_gain(pool, state, 1, base=stale, **CFG)
    assert "carries no bank for GW1" in capsys.readouterr().out


def test_the_lp_golden_still_matches(tmp_path):
    """Task 1's guard. Reading a solved variable adds no constraint."""
    from tests.test_v12_w3_force_out import GOLDEN, _capture_lp, _state as st

    assert _capture_lp(tmp_path, st())[0] == GOLDEN.read_text()
