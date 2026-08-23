import pandas as pd
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
