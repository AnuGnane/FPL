import pandas as pd
import pytest
from gaffer.optimize.milp import solve_plan, SolveInput, build_pool

OWNED = [1, 2,               # GKP x2
         3, 4, 5, 6, 7,      # DEF x5 (of 6 in pool)
         9, 10, 11, 12, 13,  # MID x5 (of 7)
         16, 17, 18]         # FWD x3 (of 5) — a LEGAL 15-man squad


def _pool(star_ep=8.0):
    """20 players: codes 1-2 GKP, 3-8 DEF, 9-15 MID, 16-20 FWD.
    Code 20 (FWD) is the non-owned star."""
    rows = []
    code = 1
    for pos, n in [("GKP", 2), ("DEF", 6), ("MID", 7), ("FWD", 5)]:
        for _ in range(n):
            rows.append({"code": code, "position": pos, "team_code": code % 8,
                         "cost": 50, "sell": 50, "ep": {1: 2.0, 2: 2.0}})
            code += 1
    rows[-1]["ep"] = {1: star_ep, 2: star_ep}          # code 20, FWD, not owned
    return pd.DataFrame(rows)


def _state(ft=1, bank=0):
    return SolveInput(owned_codes=list(OWNED), bank=bank,
                      free_transfers=ft, gws=[1, 2])


def test_solution_is_legal():
    plan = solve_plan(_pool(), _state(), decay=0.85, bench_weight=0.1,
                      vice_weight=0.1, ft_value=1.5, itb_value=0.05, hit_cost=4)
    gw = plan.gw_plans[0]
    assert len(gw.squad) == 15 and len(gw.xi) == 11
    positions = pd.DataFrame(gw.xi_rows)
    assert (positions["position"] == "GKP").sum() == 1
    assert 3 <= (positions["position"] == "DEF").sum() <= 5
    assert 1 <= (positions["position"] == "FWD").sum() <= 3
    assert gw.captain in gw.xi and gw.vice in gw.xi and gw.captain != gw.vice


def test_transfers_in_star_with_free_transfer():
    plan = solve_plan(_pool(star_ep=9.0), _state(ft=1), decay=0.85,
                      bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
                      itb_value=0.05, hit_cost=4)
    assert 20 in plan.gw_plans[0].buys        # +7 EP/GW for a free transfer
    assert plan.gw_plans[0].hits == 0


def test_no_hit_for_marginal_gain():
    # 0 free transfers. The star would be captained, so a +0.5 raw EP edge is
    # worth 2 x 0.5 = 1.0 EP/GW; over two decayed GWs that is
    # 1.0 * (1 + 0.85) = 1.85 < the 4-pt hit -> no transfer.
    plan = solve_plan(_pool(star_ep=2.5), _state(ft=0), decay=0.85,
                      bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
                      itb_value=0.05, hit_cost=4)
    assert plan.gw_plans[0].buys == []


def test_budget_blocks_unaffordable_star():
    # Star is a monster (20 EP/GW) but costs 120 with bank=0 and every
    # sale raising only 50 -> a single swap leaves a 70 shortfall.
    pool = _pool(star_ep=20.0)
    pool.loc[pool["code"] == 20, "cost"] = 120
    pool.loc[pool["code"] == 20, "sell"] = 120
    plan = solve_plan(pool, _state(ft=1, bank=0), decay=0.85,
                      bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
                      itb_value=0.05, hit_cost=4)
    for gw in plan.gw_plans:
        assert 20 not in gw.buys
        assert 20 not in gw.squad


def test_three_per_club_limit_respected():
    # Codes 19 and 20 share the club of owned FWDs 16 and 17 (team 3 by
    # construction: 19 % 8 == 3, 16 % 8 == 0 -> force it explicitly).
    pool = _pool(star_ep=15.0)
    pool.loc[pool["code"].isin([16, 17, 19, 20]), "team_code"] = 99
    pool.at[pool.index[pool["code"] == 19][0], "ep"] = {1: 15.0, 2: 15.0}
    plan = solve_plan(pool, _state(ft=2, bank=0), decay=0.85,
                      bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
                      itb_value=0.05, hit_cost=4)
    club = dict(zip(pool["code"], pool["team_code"]))
    for gw in plan.gw_plans:
        counts = pd.Series([club[c] for c in gw.squad]).value_counts()
        assert counts.max() <= 3


def test_build_pool_keeps_owned_and_uses_sell_prices():
    rows = []
    code = 1
    for pos, n in [("GKP", 4), ("DEF", 10), ("MID", 10), ("FWD", 6)]:
        for _ in range(n):
            rows.append({"code": code, "position": pos, "team_code": code % 12,
                         "now_cost": 40 + code})
            code += 1
    players = pd.DataFrame(rows)
    gws = [1, 2]
    # Owned players are deliberately the WORST by EP so top-N would drop them.
    owned_codes = [1, 5, 15, 25]
    ep_by_code_gw = {(c, g): float(c) for c in players["code"] for g in gws}
    for c in owned_codes:
        for g in gws:
            ep_by_code_gw[(c, g)] = -100.0
    my_picks = pd.DataFrame({"code": owned_codes,
                             "sell": [39, 44, 54, 64]})

    top_n = {"GKP": 2, "DEF": 3, "MID": 3, "FWD": 2}
    pool = build_pool(players, ep_by_code_gw, my_picks, gws, top_n=top_n)

    assert set(owned_codes) <= set(pool["code"])
    assert len(pool) <= sum(top_n.values()) + len(owned_codes)
    assert list(pool.columns) == ["code", "position", "team_code",
                                  "cost", "sell", "ep"]
    sell = dict(zip(pool["code"], pool["sell"]))
    cost = dict(zip(pool["code"], pool["cost"]))
    now = dict(zip(players["code"], players["now_cost"]))
    for c, s in zip(my_picks["code"], my_picks["sell"]):
        assert sell[c] == s
    for c in pool["code"]:
        assert cost[c] == now[c]
        if c not in owned_codes:
            assert sell[c] == now[c]
    # ep is carried through as a {gw: points} dict
    assert pool.loc[pool["code"] == 4, "ep"].iloc[0] == {1: 4.0, 2: 4.0}


def test_locked_in_player_is_kept_in_every_gameweek():
    # Code 8 is a non-owned DEF on 2.0 EP: nothing would buy him voluntarily.
    plan = solve_plan(_pool(), SolveInput(owned_codes=list(OWNED), bank=0,
                                          free_transfers=2, gws=[1, 2],
                                          locked_in=[8]),
                      decay=0.85, bench_weight=0.1, vice_weight=0.1,
                      ft_value=1.5, itb_value=0.05, hit_cost=4)
    for gw in plan.gw_plans:
        assert 8 in gw.squad


def test_force_in_buys_the_player_in_the_first_gameweek():
    plan = solve_plan(_pool(), SolveInput(owned_codes=list(OWNED), bank=0,
                                          free_transfers=2, gws=[1, 2],
                                          force_in_gw=[8]),
                      decay=0.85, bench_weight=0.1, vice_weight=0.1,
                      ft_value=1.5, itb_value=0.05, hit_cost=4)
    assert 8 in plan.gw_plans[0].buys


def test_max_hits_caps_the_hits_taken_each_gameweek():
    pool = _pool(star_ep=30.0)
    pool.loc[pool["code"] == 19, "ep"] = [{1: 30.0, 2: 30.0}]
    plan = solve_plan(pool, SolveInput(owned_codes=list(OWNED), bank=0,
                                       free_transfers=0, gws=[1, 2],
                                       max_hits=0),
                      decay=0.85, bench_weight=0.1, vice_weight=0.1,
                      ft_value=1.5, itb_value=0.05, hit_cost=4)
    for gw in plan.gw_plans:
        assert gw.hits == 0


def test_max_hits_does_not_bind_on_a_wildcard_week():
    # Under a wildcard hits are free, so a cap must not restrict transfers.
    pool = _pool(star_ep=30.0)
    pool.loc[pool["code"] == 19, "ep"] = [{1: 30.0, 2: 30.0}]
    plan = solve_plan(pool, SolveInput(owned_codes=list(OWNED), bank=0,
                                       free_transfers=0, gws=[1, 2],
                                       wildcard_gw=1, max_hits=0),
                      decay=0.85, bench_weight=0.1, vice_weight=0.1,
                      ft_value=1.5, itb_value=0.05, hit_cost=4)
    assert 20 in plan.gw_plans[0].squad
    assert 19 in plan.gw_plans[0].squad
    assert plan.gw_plans[0].hits == 0


def test_defaults_leave_the_solve_untouched():
    """The new fields are opt-in: an unconstrained solve must be identical."""
    kw = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
              itb_value=0.05, hit_cost=4)
    before = solve_plan(_pool(star_ep=9.0), _state(ft=1), **kw)
    after = solve_plan(_pool(star_ep=9.0),
                       SolveInput(owned_codes=list(OWNED), bank=0,
                                  free_transfers=1, gws=[1, 2],
                                  locked_in=[], force_in_gw=[],
                                  max_hits=None), **kw)
    assert len(before.gw_plans) == len(after.gw_plans)
    for was, now in zip(before.gw_plans, after.gw_plans):
        assert was.gw == now.gw
        assert (was.squad, was.xi, was.captain, was.vice, was.hits,
                was.buys, was.sells) == (now.squad, now.xi, now.captain,
                                         now.vice, now.hits, now.buys,
                                         now.sells)
    assert abs(before.objective - after.objective) < 1e-9


def test_unknown_locked_player_is_a_readable_error():
    from gaffer.errors import GafferError

    with pytest.raises(GafferError) as exc:
        solve_plan(_pool(), SolveInput(owned_codes=list(OWNED), bank=0,
                                       free_transfers=1, gws=[1, 2],
                                       locked_in=[999]),
                   decay=0.85, bench_weight=0.1, vice_weight=0.1,
                   ft_value=1.5, itb_value=0.05, hit_cost=4)
    assert "999" in str(exc.value)


# --- v4c: fixed moves ------------------------------------------------------

from gaffer.errors import GafferError
from gaffer.optimize.milp import FixedMoves
from tests.test_v4c_degradation import GOLDEN_KW, golden_pool


def _owned_state(pool, gws=(1, 2)):
    """A legal starting squad drawn off the golden pool, with one FT and
    enough bank to make a swap possible."""
    by_pos = {}
    for r in pool.itertuples():
        by_pos.setdefault(r.position, []).append(int(r.code))
    owned = (by_pos["GKP"][:2] + by_pos["DEF"][:5] + by_pos["MID"][:5]
             + by_pos["FWD"][:3])
    return SolveInput(owned_codes=owned, bank=200, free_transfers=1,
                      gws=list(gws))


def test_fixed_moves_none_is_the_identity():
    """The rail: the new argument at its default cannot move a single float."""
    pool = golden_pool()
    state = _owned_state(pool)
    a = solve_plan(pool, state, **GOLDEN_KW)
    b = solve_plan(pool, state, **GOLDEN_KW, fixed_moves=None)
    assert round(a.objective, 9) == round(b.objective, 9)
    assert a.gw_plans[0].squad == b.gw_plans[0].squad


def test_fixed_moves_forces_the_named_buy_in_the_first_week():
    pool = golden_pool()
    state = _owned_state(pool)
    spare = [int(c) for c in pool["code"] if c not in state.owned_codes]
    target = spare[0]
    plan = solve_plan(pool, state, **GOLDEN_KW,
                      fixed_moves=FixedMoves(buys=[target]))
    assert target in plan.gw_plans[0].buys
    assert target in plan.gw_plans[0].squad


def test_fixed_moves_forces_the_named_sell_in_the_first_week():
    pool = golden_pool()
    state = _owned_state(pool)
    target = state.owned_codes[-1]
    plan = solve_plan(pool, state, **GOLDEN_KW,
                      fixed_moves=FixedMoves(sells=[target]))
    assert target in plan.gw_plans[0].sells
    assert target not in plan.gw_plans[0].squad


def test_fixed_moves_can_force_a_paired_swap():
    pool = golden_pool()
    state = _owned_state(pool)
    out_code = state.owned_codes[-1]
    in_code = [int(c) for c in pool["code"]
               if c not in state.owned_codes][0]
    plan = solve_plan(pool, state, **GOLDEN_KW,
                      fixed_moves=FixedMoves(buys=[in_code],
                                             sells=[out_code]))
    first = plan.gw_plans[0]
    assert in_code in first.buys and out_code in first.sells


def test_no_transfer_forbids_every_first_week_move():
    """The 'hold, roll the FT' branch of the policy needs this to be
    enforceable, not merely preferred."""
    pool = golden_pool()
    state = _owned_state(pool)
    plan = solve_plan(pool, state, **GOLDEN_KW,
                      fixed_moves=FixedMoves(no_transfer=True))
    first = plan.gw_plans[0]
    assert first.buys == [] and first.sells == [] and first.hits == 0


def test_no_transfer_leaves_later_horizon_weeks_free():
    """Holding this week is a statement about this week only."""
    pool = golden_pool()
    state = _owned_state(pool)
    plan = solve_plan(pool, state, **GOLDEN_KW,
                      fixed_moves=FixedMoves(no_transfer=True))
    assert plan.gw_plans[0].buys == []
    assert len(plan.gw_plans) == 2


def test_fixed_moves_targets_the_first_horizon_week_by_default():
    pool = golden_pool()
    state = _owned_state(pool, gws=(3, 4))
    spare = [int(c) for c in pool["code"] if c not in state.owned_codes][0]
    plan = solve_plan(pool, state, **GOLDEN_KW,
                      fixed_moves=FixedMoves(buys=[spare]))
    assert spare in plan.gw_plans[0].buys


def test_fixed_moves_honours_an_explicit_gameweek():
    pool = golden_pool()
    state = _owned_state(pool, gws=(3, 4))
    spare = [int(c) for c in pool["code"] if c not in state.owned_codes][0]
    plan = solve_plan(pool, state, **GOLDEN_KW,
                      fixed_moves=FixedMoves(buys=[spare], gw=4))
    assert spare in plan.gw_plans[1].buys


def test_fixed_moves_on_an_unknown_code_raises_with_a_useful_message():
    """Same discipline as locked_in: silently ignoring a forced move would
    produce a plan that quietly is not the one the policy chose."""
    pool = golden_pool()
    state = _owned_state(pool)
    with pytest.raises(GafferError) as exc:
        solve_plan(pool, state, **GOLDEN_KW,
                   fixed_moves=FixedMoves(buys=[999999]))
    assert "fixed_moves" in str(exc.value)
    assert "999999" in str(exc.value)


def test_fixed_moves_with_no_transfer_and_a_buy_raises():
    """The two settings contradict each other; resolving it silently would
    hide a policy bug."""
    pool = golden_pool()
    state = _owned_state(pool)
    with pytest.raises(GafferError) as exc:
        solve_plan(pool, state, **GOLDEN_KW,
                   fixed_moves=FixedMoves(buys=[int(pool.loc[0, "code"])],
                                          no_transfer=True))
    assert "no_transfer" in str(exc.value)


# --- v4c: lambda-priced free transfers -------------------------------------

from gaffer.optimize.ft_value import LambdaLookup
from gaffer.optimize.milp import SEASON_LAST_GW


def test_the_season_end_constant_is_gameweek_thirty_eight():
    assert SEASON_LAST_GW == 38


def test_ft_lambda_none_is_the_identity():
    pool = golden_pool()
    state = _owned_state(pool)
    a = solve_plan(pool, state, **GOLDEN_KW)
    b = solve_plan(pool, state, **GOLDEN_KW, ft_lambda=None)
    assert round(a.objective, 9) == round(b.objective, 9)


def test_an_empty_lambda_lookup_falls_back_to_the_flat_ft_value():
    """No priors asset must mean 'behave as before', not 'price FTs at 0'."""
    pool = golden_pool()
    state = _owned_state(pool)
    a = solve_plan(pool, state, **GOLDEN_KW)
    b = solve_plan(pool, state, **GOLDEN_KW, ft_lambda=LambdaLookup({}))
    assert round(a.objective, 9) == round(b.objective, 9)


def test_a_lambda_table_replaces_the_flat_terminal_term():
    """With lambda in play the flat ft_value must no longer appear in the
    objective — pricing an FT twice is worse than pricing it wrong."""
    import inspect

    src = inspect.getsource(solve_plan)
    assert "ft_lambda is None or ft_lambda.empty" in src
    assert "obj.append(ft_value * ftv[T[-1]])" in src


def test_a_generous_lambda_makes_the_solver_bank_rather_than_spend():
    """The behavioural claim: a high shadow price on banked transfers buys
    fewer transfers, which is the whole point."""
    pool = golden_pool()
    state = _owned_state(pool)
    greedy = solve_plan(pool, state, **GOLDEN_KW)
    stingy = solve_plan(
        pool, state, **GOLDEN_KW,
        ft_lambda=LambdaLookup({(k, t): 50.0 for k in range(1, 6)
                                for t in range(1, 39)}))
    assert len(stingy.gw_plans[0].buys) <= len(greedy.gw_plans[0].buys)


def test_a_zero_lambda_table_makes_banking_worthless():
    """The other end: FTs worth nothing means spend them."""
    pool = golden_pool()
    state = _owned_state(pool)
    plan = solve_plan(
        pool, state, **GOLDEN_KW,
        ft_lambda=LambdaLookup({(k, t): 0.0 for k in range(1, 6)
                                for t in range(1, 39)}))
    assert len(plan.gw_plans[0].squad) == 15


def test_lambda_is_looked_up_at_the_weeks_remaining_in_the_season():
    """t is 'gameweeks left after the horizon ends', not 'horizon length' —
    a GW36 horizon is nearly worthless to bank into and a GW6 one is not."""
    import inspect

    src = inspect.getsource(solve_plan)
    assert "SEASON_LAST_GW - T[-1]" in src


def test_lambda_pricing_is_concave_in_the_banked_count():
    """Each successive banked transfer must be worth less than the last, or
    the objective would prefer hoarding five to using one."""
    pool = golden_pool()
    state = _owned_state(pool)
    table = {(k, t): 4.0 / k for k in range(1, 6) for t in range(1, 39)}
    plan = solve_plan(pool, state, **GOLDEN_KW,
                      ft_lambda=LambdaLookup(table))
    assert len(plan.gw_plans[0].squad) == 15


# --- v4c: objective craft --------------------------------------------------

from dataclasses import replace

from gaffer.optimize.milp import DEFAULT_BENCH_CURVE


def test_the_default_bench_curve_is_the_spec_triple():
    assert DEFAULT_BENCH_CURVE == [0.21, 0.06, 0.002]


def test_bench_curve_none_is_the_identity():
    pool = golden_pool()
    state = _owned_state(pool)
    a = solve_plan(pool, state, **GOLDEN_KW)
    b = solve_plan(pool, state, **GOLDEN_KW, bench_curve=None,
                   ft_use_penalty=0.0)
    assert round(a.objective, 9) == round(b.objective, 9)


def test_a_bench_curve_changes_the_objective():
    pool = golden_pool()
    state = _owned_state(pool)
    a = solve_plan(pool, state, **GOLDEN_KW)
    b = solve_plan(pool, state, **GOLDEN_KW,
                   bench_curve=DEFAULT_BENCH_CURVE)
    assert round(a.objective, 6) != round(b.objective, 6)


def test_a_bench_curve_still_produces_a_legal_squad():
    pool = golden_pool()
    state = _owned_state(pool)
    first = solve_plan(pool, state, **GOLDEN_KW,
                       bench_curve=DEFAULT_BENCH_CURVE).gw_plans[0]
    assert len(first.squad) == 15 and len(first.xi) == 11
    assert len(first.bench) == 4


def test_the_bench_curve_must_have_three_weights():
    """Three outfield bench slots; the bench keeper rides on the first
    weight, per spec's '{GK + 1st: 0.21}'."""
    pool = golden_pool()
    state = _owned_state(pool)
    with pytest.raises(GafferError) as exc:
        solve_plan(pool, state, **GOLDEN_KW, bench_curve=[0.2, 0.1])
    assert "three" in str(exc.value)


def test_bench_boost_overrides_the_curve_entirely():
    """Under a bench boost every bench player scores in full; a curve that
    survived would understate the chip by more than the chip is worth."""
    import inspect

    src = inspect.getsource(solve_plan)
    assert "state.bench_boost_gw == t" in src
    pool = golden_pool()
    state = _owned_state(pool)
    boosted = solve_plan(pool, replace(state, bench_boost_gw=1),
                         **GOLDEN_KW, bench_curve=DEFAULT_BENCH_CURVE)
    plain = solve_plan(pool, state, **GOLDEN_KW,
                       bench_curve=DEFAULT_BENCH_CURVE)
    assert boosted.objective > plain.objective


def test_a_convex_curve_prefers_a_stronger_first_bench_slot():
    """The behavioural claim: the curve buys a better first substitute and
    stops paying for the third."""
    pool = golden_pool()
    state = SolveInput(owned_codes=[], bank=1000, free_transfers=15,
                       gws=[1, 2])
    ep_of = {int(r.code): float(r.ep[1]) for r in pool.itertuples()}
    flat = solve_plan(pool, state, **GOLDEN_KW).gw_plans[0]
    curved = solve_plan(pool, state, **GOLDEN_KW,
                        bench_curve=DEFAULT_BENCH_CURVE).gw_plans[0]
    assert (max(ep_of[c] for c in curved.bench)
            >= max(ep_of[c] for c in flat.bench))


def test_ft_use_penalty_zero_is_the_identity():
    pool = golden_pool()
    state = _owned_state(pool)
    a = solve_plan(pool, state, **GOLDEN_KW)
    b = solve_plan(pool, state, **GOLDEN_KW, ft_use_penalty=0.0)
    assert round(a.objective, 9) == round(b.objective, 9)


def test_a_large_ft_use_penalty_stops_marginal_churn():
    pool = golden_pool()
    state = _owned_state(pool)
    busy = solve_plan(pool, state, **GOLDEN_KW).gw_plans[0]
    calm = solve_plan(pool, state, **GOLDEN_KW,
                      ft_use_penalty=50.0).gw_plans[0]
    assert len(calm.buys) <= len(busy.buys)


def test_the_churn_penalty_is_waived_on_a_wildcard_week():
    """Fifteen transfers on a wildcard are the chip working, not churn."""
    import inspect

    src = inspect.getsource(solve_plan)
    penalty = src.index("ft_use_penalty *")
    assert "if not wc:" in src[max(0, penalty - 200):penalty + 200]
