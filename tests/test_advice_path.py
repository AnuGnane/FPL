"""v18b — the advice path tells the truth (specs/2026-09-12-v18b-advice-path-design.md).

Rulings 2 and 3 of the polish programme's design: the ladder catches the
domain error only, and the solver switch is recorded rather than silent.
Each rail here was planted-fault tested before it was trusted (the v17g
rule): the ladder catch widened back to ``Exception`` fails the first
test; the ``opt`` line removed fails the third.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pulp
import pytest

from dataclasses import asdict

from gaffer.advise import build_advice
from gaffer.errors import GafferError
from gaffer.optimize import milp
from tests.advice_fixture import ScriptedSolver, a_plan, tiny_cfg, tiny_inputs


def test_a_programming_error_inside_the_ladder_propagates(monkeypatch):
    def miswired(*_a, **_kw):
        raise TypeError("step_context_from() takes keyword arguments")

    monkeypatch.setattr("gaffer.advise.ladder_payload", miswired)
    with pytest.raises(TypeError):
        build_advice(tiny_inputs(), tiny_cfg(), solver=ScriptedSolver())


def test_a_domain_error_inside_the_ladder_is_one_line_and_the_objective_served(
        monkeypatch, capsys):
    def no_sigmas(*_a, **_kw):
        raise GafferError("no σ table for GW3")

    monkeypatch.setattr("gaffer.advise.ladder_payload", no_sigmas)
    plan = a_plan(captain=116, vice=117)
    out = build_advice(tiny_inputs(), tiny_cfg(),
                       solver=ScriptedSolver(plan=plan))
    assert out.ladder is None
    assert out.advice.captain["code"] == 116
    assert "ladder: not built" in capsys.readouterr().out


def test_the_fallback_solver_is_recorded_on_the_state_and_highs_is_not():
    plan = a_plan(captain=116, vice=117)
    plan.solver = "cbc"
    out = build_advice(tiny_inputs(), tiny_cfg(),
                       solver=ScriptedSolver(plan=plan))
    assert out.state.opt["solver"] == "cbc"

    plan = a_plan(captain=116, vice=117)
    plan.solver = "highs"
    out = build_advice(tiny_inputs(), tiny_cfg(),
                       solver=ScriptedSolver(plan=plan))
    assert "solver" not in out.state.opt


def _a_problem() -> pulp.LpProblem:
    prob = pulp.LpProblem("tiny", pulp.LpMaximize)
    x = pulp.LpVariable("x", 0, 1, cat="Binary")
    prob += x
    return prob


def test_solve_names_highs_when_it_runs_and_cbc_when_it_falls_back(monkeypatch):
    assert milp._solve(_a_problem()) == "highs"

    class Broken:
        def __init__(self, *a, **kw):
            pass

        def actualSolve(self, *a, **kw):
            raise RuntimeError("no shared library")

    monkeypatch.setattr(pulp, "HiGHS", Broken)
    prob = _a_problem()
    assert milp._solve(prob) == "cbc"
    assert pulp.LpStatus[prob.status] == "Optimal"


def test_two_builds_with_different_clocks_differ_only_in_their_stamp():
    plan = a_plan(captain=116, vice=117)
    t1 = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 9, 12, 11, 0, tzinfo=timezone.utc)
    one = build_advice(tiny_inputs(), tiny_cfg(), solver=ScriptedSolver(plan=plan),
                       now=t1)
    two = build_advice(tiny_inputs(), tiny_cfg(), solver=ScriptedSolver(plan=plan),
                       now=t2)
    assert one.state.generated_at == t1.isoformat()
    assert two.state.generated_at == t2.isoformat()
    a, b = asdict(one.advice), asdict(two.advice)
    assert a.pop("generated_at") != b.pop("generated_at")
    assert a == b
