import pandas as pd
from gaffer.optimize.milp import SolveInput
from gaffer.optimize.chips import evaluate_chips, wildcard_now_assessment


def _pool():
    rows = []
    code = 1
    for pos, n in [("GKP", 2), ("DEF", 6), ("MID", 7), ("FWD", 5)]:
        for _ in range(n):
            rows.append({"code": code, "position": pos, "team_code": code % 8,
                         "cost": 50, "sell": 50,
                         "ep": {1: 3.0, 2: 3.0}})
            code += 1
    return pd.DataFrame(rows)


OWNED = [1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 16, 17, 18]  # legal 15

CFG = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
           itb_value=0.05, hit_cost=4)


def test_evaluate_chips_returns_delta_per_chip_gw():
    state = SolveInput(owned_codes=list(OWNED), bank=0,
                       free_transfers=1, gws=[1, 2])
    cfg = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
               itb_value=0.05, hit_cost=4)
    table = evaluate_chips(_pool(), state, chips_available=["bboost", "3xc"],
                           **cfg)
    assert {"chip", "gw", "gain"} <= set(table.columns)
    # bench boost on identical 3.0-EP players: gain ≈ 4 players * 3 EP * (1-0.1)
    bb = table[(table.chip == "bboost") & (table.gw == 1)]["gain"].iloc[0]
    assert bb > 8.0
    assert (table["gain"] > -1e-6).all()   # chips never forced to hurt


def _bad_squad_pool():
    """Same shape as _pool() but the five non-owned players are elite."""
    pool = _pool()
    elite = {8, 14, 15, 19, 20}          # DEF, MID, MID, FWD, FWD
    pool["ep"] = [
        {1: 8.0, 2: 8.0} if c in elite else {1: 2.0, 2: 2.0}
        for c in pool["code"]
    ]
    return pool


def test_wildcard_gain_is_large_when_squad_is_bad():
    state = SolveInput(owned_codes=list(OWNED), bank=0,
                       free_transfers=1, gws=[1, 2])
    table = evaluate_chips(_bad_squad_pool(), state,
                           chips_available=["wildcard", "bboost", "3xc"],
                           **CFG)
    wc = table[(table.chip == "wildcard") & (table.gw == 1)]["gain"].iloc[0]
    assert wc > 5.0
    assert (table["gain"] > -1e-6).all()


def test_wildcard_now_assessment_recommends_only_when_it_pays():
    state = SolveInput(owned_codes=list(OWNED), bank=0,
                       free_transfers=1, gws=[1, 2])
    bad = wildcard_now_assessment(_bad_squad_pool(), state, **CFG)
    assert bad["recommend"] is True
    assert bad["gain_over_horizon"] > 8.0
    assert len(bad["wc_squad"]) == 15

    ok = wildcard_now_assessment(_pool(), state, **CFG)
    assert ok["recommend"] is False
