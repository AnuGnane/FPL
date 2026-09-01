"""§F1's rails: the two-pass autosub weighting, and the identity it degrades to.

The most valuable assertion in this file is the byte-identity one, and it has
to be at the level of the **LP text** rather than the returned :class:`Plan`:
two different problems can have the same optimum, and a rail that only compared
answers would pass while the objective quietly moved. So every identity test
here spies on ``milp._solve``, captures ``str(prob.objective)`` and the sorted
constraint strings, and compares them character for character against a call
that passes no ``p_play`` at all.

The call *count* carries as much weight as the text: one call means no second
pass ran, which is the whole of plan A2's short-circuit.
"""

from __future__ import annotations

import pandas as pd
import pytest

import gaffer.optimize.milp as milp
from gaffer.optimize.milp import (DEFAULT_BENCH_CURVE, FRAILTY_CLAMP,
                                  POPULATION_DNP, SolveInput, _frailty,
                                  solve_plan)

GWS = [1, 2]
KW = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
          itb_value=0.05, hit_cost=4, bench_curve=list(DEFAULT_BENCH_CURVE))


def _pool(star_ep: float = 8.0) -> pd.DataFrame:
    """30 players: 4 GKP, 9 DEF, 10 MID, 7 FWD, a legal 15 inside it."""
    rows, code = [], 1
    for pos, n in [("GKP", 4), ("DEF", 9), ("MID", 10), ("FWD", 7)]:
        for i in range(n):
            rows.append({"code": code, "position": pos,
                         "team_code": code % 10,
                         "cost": 50, "sell": 50,
                         "ep": {g: 2.0 + i * 0.1 for g in GWS}})
            code += 1
    rows[-1]["ep"] = {g: star_ep for g in GWS}
    return pd.DataFrame(rows)


OWNED = [1, 2, 5, 6, 7, 8, 9, 14, 15, 16, 17, 18, 24, 25, 26]


def _state(**kw) -> SolveInput:
    kw.setdefault("owned_codes", list(OWNED))
    kw.setdefault("bank", 0)
    kw.setdefault("free_transfers", 2)
    kw.setdefault("gws", list(GWS))
    return SolveInput(**kw)


def _uniform(pool, value: float, gws=GWS) -> dict:
    return {int(c): {g: value for g in gws} for c in pool["code"]}


class Spy:
    """Wraps ``milp._solve``, counting calls and capturing the LP text."""

    def __init__(self, monkeypatch):
        self.problems: list[tuple[str, tuple[str, ...]]] = []
        real = milp._solve

        def spy(prob):
            real(prob)
            self.problems.append((
                str(prob.objective),
                tuple(sorted(str(c) for c in prob.constraints.values()))))

        monkeypatch.setattr(milp, "_solve", spy)

    @property
    def calls(self) -> int:
        return len(self.problems)

    def lp(self, i: int = 0):
        return self.problems[i]


def _solve(monkeypatch, pool, state, **kw):
    spy = Spy(monkeypatch)
    plan = solve_plan(pool, state, **KW, **kw)
    return spy, plan


# --- Block 1: byte-identity (plan A2) ------------------------------------

def test_no_p_play_runs_one_solve(monkeypatch):
    spy, _ = _solve(monkeypatch, _pool(), _state())
    assert spy.calls == 1


@pytest.mark.parametrize("value", [0.0, 0.5, 0.9, 1.0])
def test_a_uniform_p_play_builds_the_identical_problem(monkeypatch, value):
    """Not "the plan matches" — the *problem* matches, character for
    character. A uniform column would otherwise shift the whole bench block
    against the XI block by a constant nobody chose, and 0.0 in particular
    would collapse §F1b's ordering key to a field of zeros."""
    pool, state = _pool(), _state()
    base_spy, base_plan = _solve(monkeypatch, pool, state)
    spy, plan = _solve(monkeypatch, pool, state,
                       p_play=_uniform(pool, value))
    assert spy.calls == 1
    assert spy.lp() == base_spy.lp()
    assert plan == base_plan


def test_a_missing_player_is_absence(monkeypatch):
    """All-or-nothing coverage: a pool where half the players have a
    probability and half are silently nailed-on is the one direction that
    actively misleads, so a partially-wired caller fails closed."""
    pool, state = _pool(), _state()
    base_spy, base_plan = _solve(monkeypatch, pool, state)
    pp = _uniform(pool, 0.9)
    pp.pop(int(pool["code"].iloc[3]))
    spy, plan = _solve(monkeypatch, pool, state, p_play=pp)
    assert spy.calls == 1
    assert spy.lp() == base_spy.lp()
    assert plan == base_plan


def test_a_missing_gameweek_is_absence(monkeypatch):
    pool, state = _pool(), _state()
    base_spy, _ = _solve(monkeypatch, pool, state)
    pp = _uniform(pool, 0.9)
    pp[int(pool["code"].iloc[0])].pop(GWS[1])
    spy, _ = _solve(monkeypatch, pool, state, p_play=pp)
    assert spy.calls == 1
    assert spy.lp() == base_spy.lp()


@pytest.mark.parametrize("bad", [1.4, -0.1, float("nan"), None, "0.9", True])
def test_an_out_of_range_or_non_numeric_value_is_absence(monkeypatch, bad):
    """A caller that built this dict out of strings built it wrong, and
    coercing would hide that rather than fail closed. ``True`` is in the list
    because ``isinstance(True, int)`` and a bool is not a probability."""
    pool, state = _pool(), _state()
    base_spy, _ = _solve(monkeypatch, pool, state)
    pp = _uniform(pool, 0.9)
    pp[int(pool["code"].iloc[2])][GWS[0]] = bad
    spy, _ = _solve(monkeypatch, pool, state, p_play=pp)
    assert spy.calls == 1
    assert spy.lp() == base_spy.lp()


def test_a_locked_out_player_without_p_play_does_not_defeat_coverage(
        monkeypatch):
    """He is filtered out of the pool before the lookup, so the rest of the
    pool is still fully covered and §F1 runs."""
    pool = _pool()
    banned = int(pool["code"].iloc[-2])
    state = _state(locked_out=[banned])
    pp = {int(c): {g: 0.5 + (int(c) % 5) * 0.08 for g in GWS}
          for c in pool["code"] if int(c) != banned}
    spy, _ = _solve(monkeypatch, pool, state, p_play=pp)
    assert spy.calls == 2


def test_an_empty_dict_is_absence(monkeypatch):
    pool, state = _pool(), _state()
    base_spy, _ = _solve(monkeypatch, pool, state)
    spy, _ = _solve(monkeypatch, pool, state, p_play={})
    assert spy.calls == 1
    assert spy.lp() == base_spy.lp()


def _blank_pool(blank_team: int, blank_gw: int, gws) -> pd.DataFrame:
    """The 30-man pool over ``gws``, with one club's fixture missing in one
    week — the ``ep_matrix`` convention: a blank gameweek has no fixture rows
    and so is simply absent from the mapping."""
    rows, code = [], 1
    for pos, n in [("GKP", 4), ("DEF", 9), ("MID", 10), ("FWD", 7)]:
        for i in range(n):
            team = code % 10
            ep = {g: 2.0 + i * 0.1 for g in gws
                  if not (team == blank_team and g == blank_gw)}
            rows.append({"code": code, "position": pos, "team_code": team,
                         "cost": 50, "sell": 50, "ep": ep})
            code += 1
    return pd.DataFrame(rows)


def test_a_blanked_gameweek_is_not_absence(monkeypatch, capsys):
    """A club with no fixture in GW2 of a three-week horizon has no ``ep``
    entry for that week and no ``p_play`` for it either. That pair is not a
    hole in the wiring, it is a week the player cannot play, and counting it
    in the coverage denominator would turn every real blank into a silent
    degrade to the pre-v10 solve."""
    gws = [1, 2, 3]
    pool = _blank_pool(blank_team=3, blank_gw=2, gws=gws)
    blanked = {int(c) for c, t in zip(pool["code"], pool["team_code"])
               if t == 3}
    pp = {int(c): {g: 0.5 + (int(c) % 5) * 0.08 for g in gws
                   if not (int(c) in blanked and g == 2)}
          for c in pool["code"]}
    spy, _ = _solve(monkeypatch, pool, _state(gws=gws), p_play=pp)
    assert spy.calls == 2                    # accepted: §F1 ran
    assert "incomplete coverage" not in capsys.readouterr().out


def test_a_priced_week_without_p_play_is_still_absence(monkeypatch, capsys):
    """The other half of the same rule: the pool prices this (code, gw) and
    ``p_play`` has nothing for it, which is the partially-wired caller the
    gate exists for. Blanks are named first because they are the likelier
    cause, and the line still has to be printed."""
    gws = [1, 2, 3]
    pool = _blank_pool(blank_team=3, blank_gw=2, gws=gws)
    pp = {int(c): {g: 0.5 + (int(c) % 5) * 0.08 for g in gws}
          for c in pool["code"]}
    victim = next(int(c) for c, t in zip(pool["code"], pool["team_code"])
                  if t != 3)
    pp[victim].pop(2)
    spy, _ = _solve(monkeypatch, pool, _state(gws=gws), p_play=pp)
    assert spy.calls == 1                    # rejected: unweighted solve
    out = capsys.readouterr().out
    assert "incomplete coverage" in out
    assert "1 of " in out                    # exactly one pair, not a club's
    assert out.index("blanked gameweek") < out.index("partially-wired")


# --- Block 2: the two-pass (plan A1, §F1a) --------------------------------

def _varied(pool, xi_value=0.6, rest=0.95) -> dict:
    """A spread p_play — the best players fragile, everyone else not."""
    ranked = sorted(pool["code"], key=lambda c: -sum(
        pool.loc[pool["code"] == c, "ep"].iloc[0].values()))
    top = set(ranked[:11])
    return {int(c): {g: (xi_value if c in top else rest) for g in GWS}
            for c in pool["code"]}


def test_a_varied_p_play_runs_two_solves(monkeypatch):
    pool, state = _pool(), _state()
    spy, _ = _solve(monkeypatch, pool, state, p_play=_varied(pool))
    assert spy.calls == 2


def test_pass_two_pins_pass_ones_xi_and_captain(monkeypatch):
    pool, state = _pool(), _state()
    spy, plan = _solve(monkeypatch, pool, state, p_play=_varied(pool))
    _, second = spy.lp(1)

    def pins(prefix: str, t: int, value: str) -> list[str]:
        """Single-variable equality rows only — the composition constraints
        are sums and ``xi_.. + .. = 11.0`` would otherwise match ``= 1``."""
        return [c for c in second
                if c.startswith(f"{prefix}_") and "+" not in c
                and c.endswith(f" = {value}")
                and c.split(" ")[0].rsplit("_", 1)[1] == str(t)]

    for t in GWS:
        assert len(pins("xi", t, "1")) == 11
        assert len(pins("xi", t, "0")) == len(pool) - 11
        assert len(pins("cap", t, "1")) == 1
    assert len(plan.gw_plans) == len(GWS)


def _bench_coefficients(objective: str, prefix: str) -> list[float]:
    """The coefficients on every variable whose name starts with ``prefix``."""
    out = []
    for term in objective.replace("- ", "+ -").split(" + "):
        term = term.strip()
        if prefix in term:
            head = term.split("*")[0].strip()
            try:
                out.append(float(head))
            except ValueError:
                out.append(1.0)
    return out


def test_a_fragile_xi_raises_the_bench_weights_and_a_nailed_on_one_lowers(
        monkeypatch):
    fragile_pool, state = _pool(), _state()
    frail_spy, _ = _solve(monkeypatch, fragile_pool, state,
                          p_play=_varied(fragile_pool, xi_value=0.6))
    firm_spy, _ = _solve(monkeypatch, fragile_pool, state,
                         p_play=_varied(fragile_pool, xi_value=0.99))
    frail = max(_bench_coefficients(frail_spy.lp(1)[0], "slot_"))
    firm = max(_bench_coefficients(firm_spy.lp(1)[0], "slot_"))
    assert frail > firm


def test_the_frailty_is_one_at_the_population_rate_and_clamped_at_both_ends():
    lo, hi = FRAILTY_CLAMP
    assert _frailty(POPULATION_DNP) == pytest.approx(1.0)
    assert _frailty(0.0) == lo
    assert _frailty(1e-9) == lo
    assert _frailty(1.0) == hi
    assert lo < _frailty(POPULATION_DNP * 1.5) < hi


def test_the_clamp_binds_rather_than_going_to_zero(monkeypatch):
    """An almost-nailed-on XI clamps at 0.25 rather than pricing the bench at
    nothing — a bench worth nothing is a bench the solver fills with the
    cheapest legal bodies."""
    pool, state = _pool(), _state()
    spy, _ = _solve(monkeypatch, pool, state,
                    p_play=_varied(pool, xi_value=1.0, rest=0.5))
    coeffs = _bench_coefficients(spy.lp(1)[0], "slot_")
    assert coeffs and min(abs(c) for c in coeffs) > 0.0


def test_the_reserve_keeper_reads_the_xi_keeper_alone(monkeypatch):
    """Ten outfielders at 0.99 and a keeper at 0.5: his weight is computed
    from 0.5, not from the mean — he plays exactly when that one man does
    not."""
    pool, state = _pool(), _state()
    keepers = [int(c) for c in pool.loc[pool["position"] == "GKP", "code"]]
    pp = _varied(pool, xi_value=0.99, rest=0.99)
    for c in keepers:
        pp[c] = {g: 0.5 for g in GWS}
    spy, plan = _solve(monkeypatch, pool, state, p_play=pp)
    assert spy.calls == 2
    # The GK term rides on (sq - xi); its coefficient must reflect a frailty
    # computed from 0.5 and therefore be clamped up, not the outfield ~0.01.
    assert _frailty(1.0 - 0.5) == FRAILTY_CLAMP[1]
    assert _frailty(1.0 - 0.99) == FRAILTY_CLAMP[0]
    assert plan is not None


def test_a_bench_boost_week_is_not_rescaled(monkeypatch):
    """A boosted bench is not an autosub, which is why §F1a leaves the branch
    alone: every bench player scores in full under the chip."""
    pool = _pool()
    state = _state(bench_boost_gw=GWS[0])
    spy, _ = _solve(monkeypatch, pool, state, p_play=_varied(pool))
    obj = spy.lp(1)[0]
    # Variables are named slot_{code}_{gw}_{index}, so the gameweek is the
    # second-from-last field — matching on a trailing "_1" would catch slot
    # index 1 instead and pass for the wrong reason.
    boosted = [term for term in obj.replace("- ", "+ -").split(" + ")
               if "slot_" in term
               and term.strip().split("*")[-1].split("_")[-2] == str(GWS[0])]
    assert boosted == []
    # …and the un-boosted week still has its slot terms, so the assertion
    # above is about the chip and not about slots having vanished.
    other = [term for term in obj.replace("- ", "+ -").split(" + ")
             if "slot_" in term
             and term.strip().split("*")[-1].split("_")[-2] == str(GWS[1])]
    assert other


def test_bench_curve_none_still_solves_and_still_orders_and_weights(
        monkeypatch):
    pool, state = _pool(), _state()
    kw = dict(KW)
    kw["bench_curve"] = None
    spy = Spy(monkeypatch)
    plan = solve_plan(pool, state, **kw, p_play=_varied(pool))
    assert spy.calls == 2
    assert plan.gw_plans[0].bench


def test_an_infeasible_second_pass_returns_pass_ones_plan(monkeypatch,
                                                          capsys):
    pool, state = _pool(), _state()
    base_spy, base_plan = _solve(monkeypatch, pool, state)

    def impossible(plan, pool_, pp):
        # An XI of twelve is not a legal composition under any constraint set.
        return {"bench_scale": {}, "vice_scale": {},
                "fixed_xi": {t: list(pool_["code"][:12]) for t in GWS},
                "fixed_captain": {}}

    monkeypatch.setattr(milp, "_decision_scales", impossible)
    spy = Spy(monkeypatch)
    plan = solve_plan(pool, state, **KW, p_play=_varied(pool))
    assert spy.calls == 2
    assert plan == base_plan
    assert "second pass failed" in capsys.readouterr().out


def test_a_second_pass_that_raises_returns_pass_ones_plan(monkeypatch,
                                                          capsys):
    pool, state = _pool(), _state()
    _, base_plan = _solve(monkeypatch, pool, state)
    real = milp._solve
    calls = {"n": 0}

    def flaky(prob):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("solver died")
        real(prob)

    monkeypatch.setattr(milp, "_solve", flaky)
    plan = solve_plan(pool, state, **KW, p_play=_varied(pool))
    assert plan == base_plan
    assert "solver died" in capsys.readouterr().out


# --- Block 3: bench order (§F1b) -----------------------------------------

def _bench_key(pos, ep, p_play, t):
    """The shipped key, re-derived for a direct ordering assertion."""
    return sorted(ep, key=lambda c: (
        pos[c] == "GKP",
        -(ep[c] * (1.0 if p_play is None else p_play.get(c, {}).get(t, 1.0))),
        -ep[c]))


def test_a_fit_starter_outranks_an_equal_ep_doubt():
    """Spec §F1b's own rail: 90% fit beats a 50% doubt at equal EP."""
    pos = {1: "MID", 2: "MID"}
    ep = {1: 5.0, 2: 5.0}
    pp = {1: {1: 0.5}, 2: {1: 0.9}}
    assert _bench_key(pos, ep, pp, 1) == [2, 1]


def test_a_lower_ep_but_likelier_player_can_outrank_a_higher_one():
    pos = {1: "MID", 2: "MID"}
    ep = {1: 6.0, 2: 5.0}
    pp = {1: {1: 0.5}, 2: {1: 0.9}}      # 3.0 vs 4.5
    assert _bench_key(pos, ep, pp, 1) == [2, 1]


def test_a_tie_in_autosub_value_falls_back_to_todays_key():
    """Two players with identical ep x p_play but different ep resolve
    EP-descending, which is exactly the pre-v10 order."""
    pos = {1: "MID", 2: "MID"}
    ep = {1: 6.0, 2: 4.0}
    pp = {1: {1: 0.4}, 2: {1: 0.6}}      # 2.4 both
    assert _bench_key(pos, ep, pp, 1) == [1, 2]


def test_an_absent_p_play_is_the_pre_v10_key():
    pos = {1: "MID", 2: "MID", 3: "MID"}
    ep = {1: 4.0, 2: 6.0, 3: 5.0}
    assert _bench_key(pos, ep, None, 1) == [2, 3, 1]


def test_the_bench_keeper_is_still_last(monkeypatch):
    """The bench-GK convention, and not a value judgement about him."""
    pos = {1: "GKP", 2: "MID"}
    ep = {1: 9.0, 2: 1.0}
    pp = {1: {1: 1.0}, 2: {1: 0.1}}
    assert _bench_key(pos, ep, pp, 1) == [2, 1]

    pool, state = _pool(), _state()
    _, plan = _solve(monkeypatch, pool, state, p_play=_varied(pool))
    position = dict(zip(pool["code"], pool["position"]))
    for gp in plan.gw_plans:
        assert position[gp.bench[-1]] == "GKP"


# --- Block 4: vice (§F1c) -------------------------------------------------

def _vice_coefficients(objective: str) -> list[float]:
    return _bench_coefficients(objective, "vc_")


def test_a_doubtful_captain_grows_the_vice_term(monkeypatch):
    pool, state = _pool(), _state()
    doubt, _ = _solve(monkeypatch, pool, state,
                      p_play=_varied(pool, xi_value=0.5, rest=0.99))
    firm, _ = _solve(monkeypatch, pool, state,
                     p_play=_varied(pool, xi_value=0.995, rest=0.5))
    assert max(_vice_coefficients(doubt.lp(1)[0])) > \
        max(_vice_coefficients(firm.lp(1)[0]))


def test_an_absent_p_play_leaves_the_vice_coefficient_at_vice_weight(
        monkeypatch):
    """A1's "floor at today's value", which is a *default* and not a numeric
    floor: with no scale the multiplier is exactly 1.0."""
    pool, state = _pool(), _state()
    spy, _ = _solve(monkeypatch, pool, state)
    coeffs = _vice_coefficients(spy.lp(0)[0])
    assert coeffs
    # vice_weight * decay^t * ep — every coefficient is a multiple of 0.1.
    assert all(c > 0 for c in coeffs)


def test_the_vice_scale_is_the_captains_not_the_vices(monkeypatch):
    """Give the two men different p_play and assert which the coefficient
    tracks. Leaving the armband free in pass two would let the solver
    re-elect a captain under a weight computed from a different one."""
    pool, state = _pool(), _state()
    pp = _varied(pool, xi_value=0.7, rest=0.95)
    spy, plan = _solve(monkeypatch, pool, state, p_play=pp)
    captain = plan.gw_plans[0].captain
    vice = plan.gw_plans[0].vice
    assert captain != vice
    scales = milp._decision_scales(plan, pool, milp._p_play_lookup(
        pool, state, pp))
    expected = milp._frailty(1.0 - pp[captain][GWS[0]])
    assert scales["vice_scale"][GWS[0]] == pytest.approx(expected)
    assert scales["fixed_captain"][GWS[0]] == captain
