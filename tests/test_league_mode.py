import pandas as pd
import pytest
from gaffer.league_mode import (SIGMA, LAMBDA_CAP, Strategy,
                                compute_strategy, tilt_ep, win_probability)
from gaffer.optimize.milp import solve_plan
from tests.test_milp import _pool, _state

RIVALS = pd.DataFrame({"entry_name": ["Leader", "Mid", "Tail"],
                       "total": [500, 460, 400]})


def test_small_gap_is_neutral():
    s = compute_strategy(my_total=495, rivals=RIVALS, current_gw=10)
    assert s.stance == "neutral" and s.lam == 0.0


def test_big_gap_chases_with_positive_lambda():
    s = compute_strategy(my_total=380, rivals=RIVALS, current_gw=30)
    assert s.stance == "chase"
    assert s.lam == pytest.approx(
        0.5 * min(120 / (2 * 18 * 9 ** 0.5) - 0.5, 1.0))
    assert s.rival_name == "Leader"


def test_leading_big_defends_with_negative_lambda():
    s = compute_strategy(my_total=560, rivals=RIVALS, current_gw=36)
    assert s.stance == "defend" and s.lam < 0
    assert s.rival_name == "Leader"          # nearest chaser


def test_win_probability_symmetric_and_bounded():
    assert win_probability(500, 500, 10) == pytest.approx(0.5)
    assert 0.5 < win_probability(520, 500, 10) < 1.0


def test_empty_rivals_is_neutral():
    s = compute_strategy(500, pd.DataFrame(columns=["entry_name", "total"]),
                         10)
    assert s.stance == "neutral" and s.lam == 0.0


def test_tied_with_leader_is_neutral():
    """Dead level: gap 0 must land on neutral, not flip into a stance."""
    s = compute_strategy(my_total=500, rivals=RIVALS, current_gw=36)
    assert s.stance == "neutral"
    assert s.lam == 0.0
    assert s.gap == 0
    assert isinstance(s, Strategy)
    assert (SIGMA, LAMBDA_CAP) == (18.0, 0.5)


def test_tilt_zero_lambda_is_identity():
    ep_by = {(1, 5): 4.0, (2, 5): 4.0}
    assert tilt_ep(ep_by, {1: 90.0}, 0.0) == ep_by


def test_tilt_chasing_boosts_differentials():
    ep_by = {(1, 5): 4.0, (2, 5): 4.0}
    out = tilt_ep(ep_by, {1: 100.0, 2: 0.0}, 0.4)
    assert out[(1, 5)] == pytest.approx(4.0)          # fully owned: no boost
    assert out[(2, 5)] == pytest.approx(4.0 * 1.4)    # 0% owned: full boost


def test_tilt_defending_penalizes_differentials():
    out = tilt_ep({(1, 5): 4.0, (2, 5): 4.0}, {1: 100.0, 2: 0.0}, -0.3)
    assert out[(1, 5)] == pytest.approx(4.0)
    assert out[(2, 5)] == pytest.approx(4.0 * 0.7)


def test_tilt_eo_above_100_clamped():
    out = tilt_ep({(1, 5): 4.0}, {1: 180.0}, 0.4)     # captained by all
    assert out[(1, 5)] == pytest.approx(4.0)


def test_zero_lambda_reproduces_v1_solution():
    """lam=0 must leave the v1 points-max MILP solution bit-identical."""
    pool = _pool(star_ep=9.0)
    gws = [1, 2]
    ep_by = {(int(r["code"]), g): float(r["ep"][g])
             for _, r in pool.iterrows() for g in gws}
    # nonzero, non-uniform EO: an identity bug would perturb the pool.
    eo = {int(c): float((i * 37) % 150) for i, c in enumerate(pool["code"])}

    tilted = tilt_ep(ep_by, eo, 0.0)
    pool_tilted = pool.copy()
    pool_tilted["ep"] = [{g: tilted[(int(c), g)] for g in gws}
                         for c in pool_tilted["code"]]

    kw = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1,
              ft_value=1.5, itb_value=0.05, hit_cost=4)
    base = solve_plan(pool, _state(ft=1), **kw).gw_plans[0]
    same = solve_plan(pool_tilted, _state(ft=1), **kw).gw_plans[0]

    assert sorted(same.squad) == sorted(base.squad)
    assert sorted(same.xi) == sorted(base.xi)
    assert same.captain == base.captain
    assert sorted(same.buys) == sorted(base.buys)
    assert sorted(same.sells) == sorted(base.sells)


def test_explain_lam_puts_the_tilt_in_words():
    from gaffer.league_mode import Strategy, explain_lam

    chase = explain_lam(Strategy(0.4, 84, 30, "chase", "Ten Hag Hive"))
    assert "84 points behind Ten Hag Hive" in chase
    assert "differentials" in chase

    defend = explain_lam(Strategy(-0.3, 40, 12, "defend", "Ten Hag Hive"))
    assert "40 points ahead of Ten Hag Hive" in defend
    assert "mirror" in defend

    level = explain_lam(Strategy(0.0, 3, 30, "neutral", "Ten Hag Hive"))
    assert "points-max" in level
