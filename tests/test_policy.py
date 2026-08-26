import pandas as pd

from gaffer.optimize.milp import GwPlan, Plan
from gaffer.optimize.policy import (NEAR_MISS_BAND, Decision, Thresholds,
                                    decide)


def _freq(rows) -> pd.DataFrame:
    """Rows as (kind, code, gw, label, frequency); count is derived."""
    return pd.DataFrame(
        [{"kind": k, "code": c, "gw": g, "label": lab,
          "count": int(round(f * 100)), "frequency": f}
         for k, c, g, lab, f in rows],
        columns=["kind", "code", "gw", "label", "count", "frequency"])


def _raw(buys=(), sells=(), captain=9, hits=0, gw=5) -> Plan:
    gp = GwPlan(gw=gw, squad=[], xi=[], xi_rows=[], bench=[], captain=captain,
                vice=0, buys=list(buys), sells=list(sells), hits=hits,
                expected_pts=0.0)
    return Plan(objective=0.0, gw_plans=[gp])


TH = Thresholds(transfer=0.60, irreversible=0.75)


def test_thresholds_carry_the_spec_defaults():
    assert Thresholds().transfer == 0.60
    assert Thresholds().irreversible == 0.75


def test_a_transfer_above_sixty_percent_is_recommended():
    freq = _freq([("buy", 1, 5, "buy", 0.80), ("sell", 2, 5, "sell", 0.75),
                  ("captain", 9, 5, "captain", 1.0)])
    d = decide(freq, _raw(buys=[1], sells=[2]), TH)
    assert d.buys == [1] and d.sells == [2]
    assert d.hold is False


def test_a_transfer_exactly_at_the_bar_is_recommended():
    """>= 60%, not > 60%: the bar is a bar, not a strict inequality."""
    freq = _freq([("buy", 1, 5, "buy", 0.60), ("sell", 2, 5, "sell", 0.60),
                  ("captain", 9, 5, "captain", 1.0)])
    assert decide(freq, _raw(buys=[1], sells=[2]), TH).buys == [1]


def test_a_transfer_below_the_bar_is_held():
    freq = _freq([("buy", 1, 5, "buy", 0.55), ("sell", 2, 5, "sell", 0.55),
                  ("captain", 9, 5, "captain", 1.0)])
    d = decide(freq, _raw(buys=[1], sells=[2]), TH)
    assert d.buys == [] and d.sells == [] and d.hold is True


def test_a_held_decision_lists_its_near_misses_with_frequencies():
    freq = _freq([("buy", 1, 5, "buy", 0.55), ("sell", 2, 5, "sell", 0.50),
                  ("buy", 7, 5, "buy", 0.05),
                  ("captain", 9, 5, "captain", 1.0)])
    d = decide(freq, _raw(buys=[1], sells=[2]), TH)
    labels = {(m["kind"], m["code"]): m["frequency"] for m in d.near_misses}
    assert labels[("buy", 1)] == 0.55
    # 5% is not a near miss, it is a non-starter.
    assert ("buy", 7) not in labels


def test_the_near_miss_band_is_the_documented_width():
    assert NEAR_MISS_BAND == 0.20


def test_a_hit_needs_the_irreversible_bar():
    below = _freq([("hit", 0, 5, "hit", 0.70),
                   ("buy", 1, 5, "buy", 0.90), ("sell", 2, 5, "sell", 0.90),
                   ("captain", 9, 5, "captain", 1.0)])
    assert decide(below, _raw(buys=[1], sells=[2], hits=1), TH).hit is False

    above = _freq([("hit", 0, 5, "hit", 0.80),
                   ("buy", 1, 5, "buy", 0.90), ("sell", 2, 5, "sell", 0.90),
                   ("captain", 9, 5, "captain", 1.0)])
    assert decide(above, _raw(buys=[1], sells=[2], hits=1), TH).hit is True


def test_a_chip_needs_the_irreversible_bar():
    below = _freq([("chip", 0, 5, "bboost", 0.70),
                   ("captain", 9, 5, "captain", 1.0)])
    assert decide(below, _raw(), TH).chip is None

    above = _freq([("chip", 0, 5, "bboost", 0.90),
                   ("captain", 9, 5, "captain", 1.0)])
    d = decide(above, _raw(), TH)
    assert d.chip == "bboost" and d.chip_gw == 5


def test_the_wildcard_is_irreversible_like_every_other_chip():
    freq = _freq([("chip", 0, 5, "wildcard", 0.70),
                  ("captain", 9, 5, "captain", 1.0)])
    assert decide(freq, _raw(), TH).chip is None


def test_the_captain_is_the_plurality_winner_even_below_every_bar():
    """There is no 'hold' for the armband: someone wears it."""
    freq = _freq([("captain", 9, 5, "captain", 0.40),
                  ("captain", 4, 5, "captain", 0.35),
                  ("captain", 7, 5, "captain", 0.25)])
    d = decide(freq, _raw(captain=4), TH)
    assert d.captain == 9
    assert d.captain_frequency == 0.40


def test_a_captain_tie_breaks_towards_the_raw_optimum():
    """A coin flip that always lands the same way is better than one that
    lands differently every time the solver is re-run."""
    freq = _freq([("captain", 9, 5, "captain", 0.50),
                  ("captain", 4, 5, "captain", 0.50)])
    assert decide(freq, _raw(captain=4), TH).captain == 4


def test_with_no_captain_rows_the_raw_optimums_captain_survives():
    """Degradation: an empty sweep must not produce a captainless advice."""
    d = decide(_freq([]), _raw(captain=6), TH)
    assert d.captain == 6 and d.hold is True


def test_raw_optimum_agrees_when_the_gated_moves_match_it():
    freq = _freq([("buy", 1, 5, "buy", 0.90), ("sell", 2, 5, "sell", 0.90),
                  ("captain", 9, 5, "captain", 1.0)])
    assert decide(freq, _raw(buys=[1], sells=[2]), TH).raw_optimum_agrees


def test_raw_optimum_disagrees_when_it_wanted_a_different_player():
    freq = _freq([("buy", 1, 5, "buy", 0.90), ("sell", 2, 5, "sell", 0.90),
                  ("captain", 9, 5, "captain", 1.0)])
    assert not decide(freq, _raw(buys=[7], sells=[2]), TH).raw_optimum_agrees


def test_raw_optimum_disagrees_when_the_gate_held_it_back():
    freq = _freq([("buy", 1, 5, "buy", 0.30), ("sell", 2, 5, "sell", 0.30),
                  ("captain", 9, 5, "captain", 1.0)])
    assert not decide(freq, _raw(buys=[1], sells=[2]), TH).raw_optimum_agrees


def test_a_buy_without_a_passing_sell_still_records_the_buy():
    """decide() reports what cleared the bar; making it *legal* is
    coherent_plan's job, and conflating the two would hide the gap."""
    freq = _freq([("buy", 1, 5, "buy", 0.90), ("sell", 2, 5, "sell", 0.30),
                  ("captain", 9, 5, "captain", 1.0)])
    d = decide(freq, _raw(buys=[1], sells=[2]), TH)
    assert d.buys == [1] and d.sells == []


def test_decide_returns_the_frequency_table_it_was_given():
    """The report prints it next to the recommendation, so the decision
    carries its own evidence."""
    freq = _freq([("captain", 9, 5, "captain", 1.0)])
    d = decide(freq, _raw(), TH)
    assert isinstance(d, Decision)
    assert list(d.frequencies["kind"]) == ["captain"]


def test_buys_and_sells_come_back_in_descending_frequency():
    freq = _freq([("buy", 1, 5, "buy", 0.70), ("buy", 3, 5, "buy", 0.95),
                  ("captain", 9, 5, "captain", 1.0)])
    assert decide(freq, _raw(buys=[1, 3]), TH).buys == [3, 1]


# --- coherence re-solve ----------------------------------------------------

from gaffer.optimize.milp import SolveInput, solve_plan
from gaffer.optimize.policy import coherent_plan
from tests.test_milp import _owned_state
from tests.test_v4c_degradation import GOLDEN_KW, golden_pool


def test_a_held_decision_re_solves_with_the_week_pinned_shut():
    pool = golden_pool()
    state = _owned_state(pool)
    d = Decision(hold=True, captain=int(pool.loc[0, "code"]))
    plan = coherent_plan(pool, state, d, **GOLDEN_KW)
    assert plan.gw_plans[0].buys == [] and plan.gw_plans[0].sells == []


def test_a_gated_swap_appears_in_the_coherent_plan():
    pool = golden_pool()
    state = _owned_state(pool)
    out_code = state.owned_codes[-1]
    in_code = [int(c) for c in pool["code"]
               if c not in state.owned_codes][0]
    d = Decision(buys=[in_code], sells=[out_code], captain=in_code)
    plan = coherent_plan(pool, state, d, **GOLDEN_KW)
    assert in_code in plan.gw_plans[0].buys
    assert out_code in plan.gw_plans[0].sells


def test_a_buy_with_no_gated_sell_gets_a_sell_chosen_by_the_solver():
    """The consistency rail: the MILP finds the cheapest way to make room,
    rather than the policy inventing one."""
    pool = golden_pool()
    state = _owned_state(pool)
    in_code = [int(c) for c in pool["code"]
               if c not in state.owned_codes][0]
    d = Decision(buys=[in_code], sells=[], captain=in_code)
    plan = coherent_plan(pool, state, d, **GOLDEN_KW)
    first = plan.gw_plans[0]
    assert in_code in first.buys
    assert len(first.sells) >= 1
    assert len(first.squad) == 15


def test_the_coherent_plan_keeps_the_gated_captain():
    """The armband is decided by plurality, not by whatever the re-solve
    would have picked on its own."""
    pool = golden_pool()
    state = _owned_state(pool)
    wanted = state.owned_codes[0]
    d = Decision(captain=wanted, hold=True)
    plan = coherent_plan(pool, state, d, **GOLDEN_KW)
    assert plan.gw_plans[0].captain == wanted


def test_the_captain_override_promotes_him_into_the_xi_if_needed():
    """A captain who is not in the re-solve's XI is an illegal armband."""
    pool = golden_pool()
    state = _owned_state(pool)
    d = Decision(captain=state.owned_codes[0], hold=True)
    plan = coherent_plan(pool, state, d, **GOLDEN_KW)
    first = plan.gw_plans[0]
    assert first.captain in first.xi


def test_an_infeasible_forced_set_falls_back_to_the_raw_plan():
    """A gate that cannot be satisfied must degrade to advice, not to a
    traceback in front of a deadline."""
    pool = golden_pool()
    state = _owned_state(pool)
    # Every spare player forced in at once: no bank, no FTs, not legal.
    spares = [int(c) for c in pool["code"] if c not in state.owned_codes]
    d = Decision(buys=spares, sells=[], captain=state.owned_codes[0])
    plan = coherent_plan(pool, state, d, **GOLDEN_KW)
    assert len(plan.gw_plans[0].squad) == 15


def test_coherent_plan_passes_the_solver_config_through():
    """Same knobs as the deterministic solve, or the re-solve is optimizing a
    different problem than the sweep was."""
    import inspect

    src = inspect.getsource(coherent_plan)
    assert "**solve_cfg" in src
    assert "fixed_moves=" in src


# --- B6: the printed percentage must belong to the printed captain ---------

def test_the_frequency_of_a_captain_the_sweep_never_picked_is_none():
    from gaffer.optimize.policy import captain_frequency_of

    freqs = _freq([("captain", 9, 5, "Nine", 0.7),
                   ("captain", 4, 5, "Four", 0.3)])
    assert captain_frequency_of(freqs, 9) == 0.7
    assert captain_frequency_of(freqs, 4) == 0.3
    assert captain_frequency_of(freqs, 11) is None


def test_an_empty_frequency_table_has_no_captain_frequency():
    from gaffer.optimize.policy import captain_frequency_of

    assert captain_frequency_of(pd.DataFrame(), 9) is None


def test_a_dropped_plurality_captain_does_not_lend_out_his_percentage():
    """B6. The plurality winner is silently dropped when he is not in the
    re-solved squad — but his frequency kept flowing into the report and got
    printed next to whoever actually took the armband."""
    from gaffer.optimize.policy import captain_frequency_of

    pool = golden_pool()
    state = _owned_state(pool)
    # A code the sweep loved but the squad cannot contain.
    outsider = int(max(c for c in pool["code"] if c not in state.owned_codes))
    freqs = _freq([("captain", outsider, 1, "Outsider", 0.9)])
    d = Decision(captain=outsider, captain_frequency=0.9, hold=True,
                 frequencies=freqs)
    plan = coherent_plan(pool, state, d, **GOLDEN_KW)
    actual = plan.gw_plans[0].captain
    assert actual != outsider, "fixture no longer drops the wanted captain"
    assert captain_frequency_of(freqs, actual) is None
