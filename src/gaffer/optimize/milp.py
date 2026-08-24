"""Multi-period MILP for FPL squad planning.

Decides, jointly over a horizon of gameweeks: the 15-man squad, the starting
XI, captain/vice, and the transfers (with free-transfer banking and points
hits) that link one gameweek's squad to the next.

Two modelling caveats callers should know about:

* ``hits`` and ``ftv`` are bounded rather than pinned to an exact min/max,
  which is only equivalent to the FPL rules while a hit costs more than a
  banked free transfer is worth, i.e. while
  ``ft_value < hit_cost * decay ** (len(gws) - 1)``. The defaults
  (1.5 < 4 * 0.85**5 = 1.775) satisfy this with room to spare.
* ``locked_out`` removes players from the pool outright, so it is meant for
  players you do *not* own. Locking out an owned player makes them vanish
  from the squad without generating sale proceeds.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import pulp

from gaffer.errors import GafferError

SQUAD_COMPOSITION = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
XI_BOUNDS = {"GKP": (1, 1), "DEF": (3, 5), "MID": (2, 5), "FWD": (1, 3)}
MAX_PER_CLUB = 3
MAX_FREE_TRANSFERS = 5

DEFAULT_TOP_N = {"GKP": 8, "DEF": 22, "MID": 26, "FWD": 14}


@dataclass
class SolveInput:
    owned_codes: list[int]
    bank: int                    # 0.1m units
    free_transfers: int
    gws: list[int]               # planning horizon, e.g. [3,4,5,6,7,8]
    wildcard_gw: int | None = None
    bench_boost_gw: int | None = None
    triple_captain_gw: int | None = None
    locked_out: list[int] = field(default_factory=list)   # codes banned
    # What-if constraints (spec §3.2). All three default to "no constraint",
    # so an unconstrained solve is bit-identical to the pre-v3 one.
    locked_in: list[int] = field(default_factory=list)
    """Codes that must be in the squad in every gameweek of the horizon."""
    force_in_gw: list[int] = field(default_factory=list)
    """Codes that must be transferred in during the *first* gameweek."""
    max_hits: int | None = None
    """Upper bound on hits per gameweek. ``None`` leaves it to the objective.

    Never applied to a wildcard week, where hits are free by the rules.
    """


@dataclass
class GwPlan:
    gw: int
    squad: list[int]
    xi: list[int]
    xi_rows: list[dict]
    bench: list[int]
    captain: int
    vice: int
    buys: list[int]
    sells: list[int]
    hits: int
    expected_pts: float


@dataclass
class Plan:
    objective: float
    gw_plans: list[GwPlan]


def solve_plan(pool: pd.DataFrame, state: SolveInput, *, decay: float,
               bench_weight: float, vice_weight: float, ft_value: float,
               itb_value: float, hit_cost: int) -> Plan:
    """Solve the multi-period plan.

    pool: [code, position, team_code, cost, sell, ep] where ep is a dict
    {gw: expected_points} (missing gw -> 0, e.g. blank GWs).
    Prices are static over the horizon (documented approximation).
    """
    pool = pool[~pool["code"].isin(state.locked_out)].reset_index(drop=True)
    codes = pool["code"].tolist()
    known = set(codes)
    for label, wanted in (("lock", state.locked_in),
                          ("force_in", state.force_in_gw)):
        missing = [c for c in wanted if c not in known]
        if missing:
            raise GafferError(
                f"{label}: player code {missing[0]} is not in the candidate "
                f"pool (it may also be banned)")
    pos = dict(zip(pool["code"], pool["position"]))
    club = dict(zip(pool["code"], pool["team_code"]))
    cost = dict(zip(pool["code"], pool["cost"]))
    sell = dict(zip(pool["code"], pool["sell"]))
    ep_col = dict(zip(pool["code"], pool["ep"]))
    ep = {c: {g: float(ep_col[c].get(g, 0.0)) for g in state.gws}
          for c in codes}
    owned0 = {c: int(c in set(state.owned_codes)) for c in codes}
    T = state.gws

    prob = pulp.LpProblem("gaffer", pulp.LpMaximize)
    V = pulp.LpVariable.dicts
    sq = V("sq", (codes, T), cat="Binary")
    xi = V("xi", (codes, T), cat="Binary")
    cap = V("cap", (codes, T), cat="Binary")
    vice = V("vc", (codes, T), cat="Binary")
    tin = V("in", (codes, T), cat="Binary")
    tout = V("out", (codes, T), cat="Binary")
    hits = V("hit", T, lowBound=0, cat="Integer")
    ftv = V("ft", T, lowBound=0, upBound=MAX_FREE_TRANSFERS, cat="Integer")
    bank = V("bank", T, lowBound=0)

    for t_i, t in enumerate(T):
        wc = (state.wildcard_gw == t)
        nt = pulp.lpSum(tin[c][t] for c in codes)
        # squad continuity
        for c in codes:
            prev = owned0[c] if t_i == 0 else sq[c][T[t_i - 1]]
            prob += sq[c][t] == prev + tin[c][t] - tout[c][t]
            prob += tin[c][t] + tout[c][t] <= 1
            prob += xi[c][t] <= sq[c][t]
            prob += cap[c][t] <= xi[c][t]
            prob += vice[c][t] <= xi[c][t]
            prob += cap[c][t] + vice[c][t] <= 1
        # composition
        for p, n in SQUAD_COMPOSITION.items():
            prob += pulp.lpSum(sq[c][t] for c in codes if pos[c] == p) == n
        prob += pulp.lpSum(xi[c][t] for c in codes) == 11
        for p, (lo, hi) in XI_BOUNDS.items():
            n_p = pulp.lpSum(xi[c][t] for c in codes if pos[c] == p)
            prob += n_p >= lo
            prob += n_p <= hi
        prob += pulp.lpSum(cap[c][t] for c in codes) == 1
        prob += pulp.lpSum(vice[c][t] for c in codes) == 1
        for tc in set(club.values()):
            prob += pulp.lpSum(
                sq[c][t] for c in codes if club[c] == tc) <= MAX_PER_CLUB
        # budget: bank rolls forward, sales fund purchases, never negative
        inflow = pulp.lpSum(sell[c] * tout[c][t] for c in codes)
        outflow = pulp.lpSum(cost[c] * tin[c][t] for c in codes)
        prev_bank = state.bank if t_i == 0 else bank[T[t_i - 1]]
        prob += bank[t] == prev_bank + inflow - outflow
        # free transfers & hits
        prev_ft = state.free_transfers if t_i == 0 else ftv[T[t_i - 1]]
        if wc:
            prob += hits[t] == 0                 # unlimited free transfers
            prob += ftv[t] <= prev_ft + 1        # banked FTs survive the WC
        else:
            # hits is penalised in the objective so the >= bound is tight;
            # ftv is rewarded so its <= bound is tight. The <= nt cut stops
            # the solver from buying FTs with phantom hits (see module note).
            prob += hits[t] >= nt - prev_ft
            prob += hits[t] <= nt
            prob += ftv[t] <= prev_ft - nt + hits[t] + 1
        prob += ftv[t] <= MAX_FREE_TRANSFERS
        for c in state.locked_in:
            prob += sq[c][t] == 1
        if state.max_hits is not None and not wc:
            prob += hits[t] <= state.max_hits
    for c in state.force_in_gw:
        prob += tin[c][T[0]] == 1

    obj = []
    for t_i, t in enumerate(T):
        d = decay ** t_i
        cap_mult = 2.0 if state.triple_captain_gw == t else 1.0
        bw = 1.0 if state.bench_boost_gw == t else bench_weight
        for c in codes:
            e = ep[c][t]
            obj.append(d * e * (xi[c][t] + cap_mult * cap[c][t]
                                + vice_weight * vice[c][t]))
            obj.append(d * e * bw * (sq[c][t] - xi[c][t]))
        obj.append(-hit_cost * d * hits[t])
    obj.append(ft_value * ftv[T[-1]])
    obj.append((itb_value / 10.0) * bank[T[-1]])
    prob += pulp.lpSum(obj)

    _solve(prob)
    if pulp.LpStatus[prob.status] != "Optimal":
        raise RuntimeError(f"MILP not optimal: {pulp.LpStatus[prob.status]}")

    def val(v):
        return v.varValue is not None and v.varValue > 0.5

    gw_plans = []
    for t in T:
        squad = [c for c in codes if val(sq[c][t])]
        xi_l = [c for c in codes if val(xi[c][t])]
        # bench order: outfielders by EP desc, GK last (bench-GK convention)
        bench = sorted((c for c in squad if c not in xi_l),
                       key=lambda c: (pos[c] == "GKP", -ep[c][t]))
        gw_plans.append(GwPlan(
            gw=t, squad=squad, xi=xi_l,
            xi_rows=[{"code": c, "position": pos[c], "ep": ep[c][t]}
                     for c in xi_l],
            bench=bench,
            captain=next(c for c in codes if val(cap[c][t])),
            vice=next(c for c in codes if val(vice[c][t])),
            buys=[c for c in codes if val(tin[c][t])],
            sells=[c for c in codes if val(tout[c][t])],
            hits=int(round(hits[t].varValue or 0)),
            expected_pts=sum(ep[c][t] for c in xi_l)
                         + max((ep[c][t] for c in xi_l), default=0.0),
        ))
    return Plan(objective=pulp.value(prob.objective), gw_plans=gw_plans)


def _solve(prob: pulp.LpProblem) -> None:
    """Solve with HiGHS, falling back to bundled CBC on any failure.

    HiGHS can construct fine and still blow up at solve time (missing shared
    library, unsupported build), so the fallback wraps the solve itself.
    """
    try:
        prob.solve(pulp.HiGHS(msg=False))
        return
    except Exception:
        pass
    prob.solve(pulp.PULP_CBC_CMD(msg=False))


def build_pool(players: pd.DataFrame, ep_by_code_gw: dict,
               my_picks: pd.DataFrame, gws: list[int],
               top_n: dict | None = None) -> pd.DataFrame:
    """Candidate pool: owned players + top-N per position by horizon EP.

    Keeps the MILP small (fast) without losing realistic candidates.
    """
    if top_n is None:
        top_n = DEFAULT_TOP_N
    players = players.copy()
    players["ep"] = players["code"].map(
        lambda c: {g: ep_by_code_gw.get((c, g), 0.0) for g in gws})
    players["h_ep"] = players["ep"].map(lambda d: sum(d.values()))
    owned = set(my_picks["code"])
    keep = [players[players["position"] == p].nlargest(n, "h_ep")
            for p, n in top_n.items()]
    pool = pd.concat(keep).drop_duplicates("code")
    pool = pd.concat([pool, players[players["code"].isin(owned)]]) \
             .drop_duplicates("code")
    sell_map = dict(zip(my_picks["code"], my_picks["sell"]))
    pool["cost"] = pool["now_cost"]
    pool["sell"] = pool.apply(
        lambda r: sell_map.get(r["code"], r["now_cost"]), axis=1)
    return pool[["code", "position", "team_code", "cost", "sell", "ep"]]
