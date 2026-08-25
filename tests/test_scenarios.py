import numpy as np
import pandas as pd

from gaffer.optimize.scenarios import (NOISE_DENOM, NOISE_FLOOR_XMINS,
                                       noise_ep, noised_pool,
                                       xmins_by_player_gw)


def _comp() -> pd.DataFrame:
    """Component frame in predict_components' shape: one row per fixture."""
    return pd.DataFrame([
        {"code": 1, "gw": 5, "opp_code": 9, "p_play": 1.0, "p60": 1.0},
        {"code": 2, "gw": 5, "opp_code": 9, "p_play": 0.0, "p60": 0.0},
        {"code": 3, "gw": 5, "opp_code": 9, "p_play": 0.8, "p60": 0.5},
    ])


def test_xmins_of_a_nailed_on_starter_is_ninety():
    out = xmins_by_player_gw(_comp())
    assert out[(1, 5)] == 90.0


def test_xmins_of_a_player_who_never_plays_is_zero():
    out = xmins_by_player_gw(_comp())
    assert out[(2, 5)] == 0.0


def test_xmins_matches_the_hand_computed_formula():
    out = xmins_by_player_gw(_comp())
    want = 90 * 0.8 * 0.5 + 45 * 0.8 * (1 - 0.5)
    assert abs(out[(3, 5)] - want) < 1e-12


def test_xmins_is_clipped_to_the_ninety_two_ceiling():
    """The formula cannot exceed 90, but a DGW average of two 90s is still 90
    and a corrupt p_play > 1 must not produce negative noise scale."""
    comp = _comp()
    comp.loc[0, "p_play"] = 1.4
    out = xmins_by_player_gw(comp)
    assert out[(1, 5)] == NOISE_FLOOR_XMINS


def test_xmins_averages_a_double_gameweek_rather_than_summing_it():
    """Two fixtures do not make a player twice as nailed on; their EP is
    already doubled, so the absolute noise doubles on its own."""
    comp = pd.concat([_comp(), pd.DataFrame([
        {"code": 1, "gw": 5, "opp_code": 11, "p_play": 1.0, "p60": 1.0}])],
        ignore_index=True)
    assert xmins_by_player_gw(comp)[(1, 5)] == 90.0


def test_xmins_of_a_frame_without_the_minutes_columns_is_empty():
    """Degradation: no minutes model output means no scenario noise, which
    noise_ep turns into a no-op rather than a crash."""
    assert xmins_by_player_gw(pd.DataFrame({"code": [1], "gw": [5]})) == {}


# --- noise -----------------------------------------------------------------

def test_noise_on_a_ninety_two_minute_player_is_exactly_zero():
    """The point of the scaling: a certainty has no estimation error left to
    simulate."""
    ep = {(1, 5): 6.0}
    out = noise_ep(ep, {(1, 5): 92.0}, np.random.default_rng(0))
    assert out[(1, 5)] == 6.0


def test_noise_on_a_zero_minute_player_is_the_full_scale():
    ep = {(1, 5): 6.0}
    rng = np.random.default_rng(3)
    draw = np.random.default_rng(3).standard_normal()
    out = noise_ep(ep, {(1, 5): 0.0}, rng)
    want = max(0.0, 6.0 + 6.0 * (92.0 - 0.0) / NOISE_DENOM * draw)
    assert abs(out[(1, 5)] - want) < 1e-12


def test_noise_is_deterministic_under_a_fixed_seed():
    ep = {(1, 5): 6.0, (2, 5): 3.0, (1, 6): 5.0}
    xm = {(1, 5): 40.0, (2, 5): 10.0, (1, 6): 70.0}
    a = noise_ep(ep, xm, np.random.default_rng(11))
    b = noise_ep(ep, xm, np.random.default_rng(11))
    assert a == b


def test_noise_differs_between_two_draws_from_the_same_generator():
    """One draw per player-GW per scenario, so consecutive scenarios off the
    same generator must not repeat."""
    ep = {(1, 5): 6.0}
    rng = np.random.default_rng(11)
    assert noise_ep(ep, {(1, 5): 10.0}, rng) != noise_ep(
        ep, {(1, 5): 10.0}, rng)


def test_noise_never_produces_a_negative_expected_score():
    """A large downward draw on a low-xmins player can cross zero; a negative
    EP would make the MILP want to bench a player it cannot bench."""
    ep = {(c, 5): 0.2 for c in range(200)}
    xm = {(c, 5): 0.0 for c in range(200)}
    out = noise_ep(ep, xm, np.random.default_rng(2))
    assert min(out.values()) >= 0.0


def test_noise_leaves_cells_with_no_xmins_untouched():
    """A player with no minutes prediction is not a player with certain
    minutes; leaving the cell alone is the honest degradation."""
    out = noise_ep({(1, 5): 6.0}, {}, np.random.default_rng(0))
    assert out == {(1, 5): 6.0}


def test_noise_does_not_mutate_its_input():
    ep = {(1, 5): 6.0}
    noise_ep(ep, {(1, 5): 0.0}, np.random.default_rng(0))
    assert ep == {(1, 5): 6.0}


# --- pool ------------------------------------------------------------------

def _pool() -> pd.DataFrame:
    return pd.DataFrame([
        {"code": 1, "position": "MID", "team_code": 3, "cost": 70, "sell": 70,
         "ep": {5: 6.0, 6: 5.0}},
        {"code": 2, "position": "DEF", "team_code": 4, "cost": 50, "sell": 50,
         "ep": {5: 3.0, 6: 3.5}},
    ])


def test_noised_pool_keeps_every_column_and_row():
    """The candidate set must not change between scenarios, or the move
    frequencies are counting different boards."""
    out = noised_pool(_pool(), {(1, 5): 40.0}, np.random.default_rng(0))
    assert list(out.columns) == list(_pool().columns)
    assert list(out["code"]) == [1, 2]


def test_noised_pool_replaces_the_ep_dicts_without_mutating_the_original():
    pool = _pool()
    out = noised_pool(pool, {(1, 5): 0.0, (1, 6): 0.0, (2, 5): 0.0,
                             (2, 6): 0.0}, np.random.default_rng(4))
    assert pool.loc[0, "ep"] == {5: 6.0, 6: 5.0}
    assert out.loc[0, "ep"] != pool.loc[0, "ep"]
    assert set(out.loc[0, "ep"]) == {5, 6}


# --- run_scenarios ---------------------------------------------------------

from gaffer.optimize.milp import SolveInput
from gaffer.optimize.scenarios import ScenarioRun, run_scenarios

SOLVE_KW = dict(decay=0.85, bench_weight=0.10, vice_weight=0.1,
                ft_value=1.5, itb_value=0.05, hit_cost=4)


def _board() -> tuple[pd.DataFrame, SolveInput]:
    """A legal 15-player board with spares, over one gameweek."""
    rows, code = [], 200
    for pos, count, base in [("GKP", 3, 45), ("DEF", 7, 45),
                             ("MID", 7, 55), ("FWD", 4, 60)]:
        for i in range(count):
            rows.append({"code": code, "position": pos,
                         "team_code": code % 8, "cost": base + i,
                         "sell": base + i, "ep": {5: 2.0 + 0.3 * i}})
            code += 1
    pool = pd.DataFrame(rows)
    state = SolveInput(owned_codes=[], bank=1000, free_transfers=15, gws=[5])
    return pool, state


def test_run_scenarios_returns_one_plan_per_scenario():
    pool, state = _board()
    run = run_scenarios(pool, state, {}, n=3, seed=1, **SOLVE_KW)
    assert isinstance(run, ScenarioRun)
    assert len(run.plans) == 3
    assert run.attempted == 3 and run.completed == 3


def test_run_scenarios_with_n_zero_solves_nothing():
    """The degradation rail's load-bearing case."""
    pool, state = _board()
    run = run_scenarios(pool, state, {}, n=0, seed=1, **SOLVE_KW)
    assert run.plans == [] and run.attempted == 0 and run.completed == 0


def test_run_scenarios_is_reproducible_under_a_seed():
    pool, state = _board()
    xm = {(int(c), 5): 20.0 for c in pool["code"]}
    a = run_scenarios(pool, state, xm, n=3, seed=99, **SOLVE_KW)
    b = run_scenarios(pool, state, xm, n=3, seed=99, **SOLVE_KW)
    assert [p.gw_plans[0].squad for p in a.plans] == \
           [p.gw_plans[0].squad for p in b.plans]


def test_run_scenarios_with_a_different_seed_explores_differently():
    pool, state = _board()
    xm = {(int(c), 5): 0.0 for c in pool["code"]}
    a = run_scenarios(pool, state, xm, n=4, seed=1, **SOLVE_KW)
    b = run_scenarios(pool, state, xm, n=4, seed=2, **SOLVE_KW)
    assert [p.gw_plans[0].captain for p in a.plans] != \
           [p.gw_plans[0].captain for p in b.plans]


def test_run_scenarios_records_the_seed_it_used():
    """The report prints it, and reproducing an old piece of advice is the
    only way to argue with it."""
    pool, state = _board()
    assert run_scenarios(pool, state, {}, n=2, seed=77, **SOLVE_KW).seed == 77


def test_run_scenarios_drops_a_failing_solve_and_counts_it(monkeypatch):
    """39/40 is a report line, not an error."""
    import gaffer.optimize.scenarios as scen

    pool, state = _board()
    calls = {"n": 0}
    real = scen.solve_plan

    def flaky(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("MILP not optimal: Infeasible")
        return real(*a, **kw)

    monkeypatch.setattr(scen, "solve_plan", flaky)
    run = run_scenarios(pool, state, {}, n=3, seed=1, **SOLVE_KW)
    assert run.attempted == 3 and run.completed == 2
    assert len(run.plans) == 2
    assert run.failures == 1


def test_run_scenarios_zero_noise_reproduces_the_deterministic_optimum():
    """With every player pinned at 92 xMins the noise is identically zero, so
    every scenario has to agree with the plain solve. This is the sanity
    check that the noise is the only thing varying."""
    from gaffer.optimize.milp import solve_plan

    pool, state = _board()
    xm = {(int(c), 5): 92.0 for c in pool["code"]}
    run = run_scenarios(pool, state, xm, n=2, seed=5, **SOLVE_KW)
    raw = solve_plan(pool, state, **SOLVE_KW)
    for plan in run.plans:
        assert plan.gw_plans[0].squad == raw.gw_plans[0].squad


# --- move_frequencies ------------------------------------------------------

from gaffer.optimize.milp import GwPlan, Plan
from gaffer.optimize.scenarios import FREQ_COLUMNS, move_frequencies


def _plan(buys, sells, captain, hits=0, gw=5, chip=None) -> Plan:
    gp = GwPlan(gw=gw, squad=[], xi=[], xi_rows=[], bench=[], captain=captain,
                vice=0, buys=list(buys), sells=list(sells), hits=hits,
                expected_pts=0.0)
    plan = Plan(objective=0.0, gw_plans=[gp])
    if chip is not None:
        plan.chip, plan.chip_gw = chip, gw     # set by the chip sweep
    return plan


def test_move_frequencies_has_the_documented_columns():
    out = move_frequencies([_plan([1], [2], 9)])
    assert list(out.columns) == list(FREQ_COLUMNS)


def test_a_buy_in_every_scenario_has_frequency_one():
    out = move_frequencies([_plan([1], [2], 9), _plan([1], [3], 9)])
    row = out[(out["kind"] == "buy") & (out["code"] == 1)].iloc[0]
    assert row["frequency"] == 1.0 and row["count"] == 2


def test_a_buy_in_half_the_scenarios_has_frequency_one_half():
    out = move_frequencies([_plan([1], [2], 9), _plan([4], [2], 9)])
    row = out[(out["kind"] == "buy") & (out["code"] == 1)].iloc[0]
    assert row["frequency"] == 0.5


def test_a_buy_inside_a_double_move_counts_the_same_as_one_alone():
    """The key is the player, not the plan shape: 'how often does the model
    want this player' is the question the threshold is answering."""
    out = move_frequencies([_plan([1], [2], 9), _plan([1, 7], [2, 8], 9)])
    row = out[(out["kind"] == "buy") & (out["code"] == 1)].iloc[0]
    assert row["frequency"] == 1.0


def test_a_repeated_buy_within_one_scenario_counts_once():
    out = move_frequencies([_plan([1, 1], [2], 9)])
    assert int(out[(out["kind"] == "buy") & (out["code"] == 1)]
               .iloc[0]["count"]) == 1


def test_no_transfer_is_its_own_counted_move():
    """'Roll the FT' has to compete on the same scale as the transfers, or
    holding could never win."""
    out = move_frequencies([_plan([], [], 9), _plan([1], [2], 9)])
    row = out[out["kind"] == "no_transfer"].iloc[0]
    assert row["frequency"] == 0.5


def test_captain_frequencies_are_a_distribution_over_scenarios():
    out = move_frequencies([_plan([], [], 9), _plan([], [], 9),
                            _plan([], [], 4)])
    caps = out[out["kind"] == "captain"].set_index("code")["frequency"]
    assert abs(caps[9] - 2 / 3) < 1e-12
    assert abs(caps[4] - 1 / 3) < 1e-12


def test_hits_are_counted_per_horizon_week():
    out = move_frequencies([_plan([1], [2], 9, hits=1),
                            _plan([1], [2], 9, hits=0)])
    row = out[out["kind"] == "hit"].iloc[0]
    assert row["frequency"] == 0.5 and row["gw"] == 5


def test_a_week_with_no_hit_in_any_scenario_produces_no_hit_row():
    out = move_frequencies([_plan([1], [2], 9), _plan([1], [2], 9)])
    assert out[out["kind"] == "hit"].empty


def test_only_the_first_horizon_week_produces_buy_and_sell_rows():
    """Weeks two and three are re-planned from scratch next week; counting
    their moves would gate a decision nobody is taking."""
    gp1 = GwPlan(gw=5, squad=[], xi=[], xi_rows=[], bench=[], captain=9,
                 vice=0, buys=[1], sells=[2], hits=0, expected_pts=0.0)
    gp2 = GwPlan(gw=6, squad=[], xi=[], xi_rows=[], bench=[], captain=9,
                 vice=0, buys=[5], sells=[6], hits=0, expected_pts=0.0)
    out = move_frequencies([Plan(objective=0.0, gw_plans=[gp1, gp2])])
    assert set(out[out["kind"] == "buy"]["code"]) == {1}
    assert set(out[out["kind"] == "sell"]["code"]) == {2}


def test_hits_in_later_horizon_weeks_are_still_counted():
    """A hit planned for week three is information about this week's decision
    — it says the current squad is about to need surgery."""
    gp1 = GwPlan(gw=5, squad=[], xi=[], xi_rows=[], bench=[], captain=9,
                 vice=0, buys=[], sells=[], hits=0, expected_pts=0.0)
    gp2 = GwPlan(gw=6, squad=[], xi=[], xi_rows=[], bench=[], captain=9,
                 vice=0, buys=[5], sells=[6], hits=1, expected_pts=0.0)
    out = move_frequencies([Plan(objective=0.0, gw_plans=[gp1, gp2])])
    assert list(out[out["kind"] == "hit"]["gw"]) == [6]


def test_chip_frequencies_are_keyed_by_chip_and_week():
    out = move_frequencies([_plan([], [], 9, chip="bboost"),
                            _plan([], [], 9, chip="bboost"),
                            _plan([], [], 9)])
    row = out[out["kind"] == "chip"].iloc[0]
    assert row["label"] == "bboost" and abs(row["frequency"] - 2 / 3) < 1e-12


def test_move_frequencies_of_no_scenarios_is_an_empty_typed_frame():
    out = move_frequencies([])
    assert out.empty and list(out.columns) == list(FREQ_COLUMNS)


def test_move_frequencies_is_sorted_by_descending_frequency():
    out = move_frequencies([_plan([1, 2], [3], 9), _plan([1], [3], 9)])
    buys = out[out["kind"] == "buy"]["frequency"].tolist()
    assert buys == sorted(buys, reverse=True)
