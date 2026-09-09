"""If the fixture cannot build, every test that uses it is testing the
fixture rather than the code (v17g §5)."""
from __future__ import annotations

from gaffer.advise import build_advice
from gaffer.league_mode import Strategy
from tests.advice_fixture import (GW, ScriptedSolver, a_plan,
                                  a_scratch_working_directory,  # noqa: F401
                                  recording, tiny_cfg, tiny_inputs, tiny_my,
                                  tiny_squad, without_the_ladder)


def test_the_tiny_board_builds_an_advice_end_to_end():
    out = build_advice(tiny_inputs(), tiny_cfg(), solver=ScriptedSolver())
    assert out.advice.gw == GW
    assert out.state.gw == GW
    assert len(out.advice.xi) == 11
    assert out.advice.captain["code"]


def test_the_scripted_solver_records_the_pool_and_the_state_it_was_handed():
    solver = ScriptedSolver()
    build_advice(tiny_inputs(), tiny_cfg(), solver=solver)
    assert solver.names[0] == "solve"
    _, kw = solver.calls[0]
    assert list(kw["pool"].columns) == ["code", "position", "team_code",
                                        "cost", "sell", "ep"]
    assert kw["state"].gws == [7, 8]


def test_a_scripted_captain_reaches_the_served_plan(monkeypatch):
    """With the ladder off, which is the only way the served plan is the
    solver's: :func:`without_the_ladder` says why."""
    without_the_ladder(monkeypatch)
    plan = a_plan(captain=116, vice=117)
    out = build_advice(tiny_inputs(), tiny_cfg(),
                       solver=ScriptedSolver(plan=plan))
    assert out.ladder is None
    assert out.advice.captain["code"] == 116
    assert out.advice.vice["code"] == 117


def test_with_the_ladder_on_the_scripted_plan_is_only_the_objective_block():
    """The other half of the same fact, so nobody reads the test above as
    "the fixture cannot serve a scripted plan": the ladder re-solves every
    rung for real, so the scripted plan is the *objective* the restraint walk
    was measured against and the served moves are the chosen rung's."""
    plan = a_plan(buys=[118], sells=[112], hits=1)
    out = build_advice(tiny_inputs(), tiny_cfg(),
                       solver=ScriptedSolver(plan=plan))
    assert out.ladder is not None
    assert out.advice.restraint["chosen"] == "hits0"
    assert [b["code"] for b in out.advice.objective["buys"]] == [118]
    # The rung's own plan: fifteen opening buys, not the scripted one.
    assert len(out.advice.buys) == 15


def test_a_weekly_board_builds_from_an_owned_squad():
    """The mode the sweep, the chips and the alternative plans are gated on:
    all three read ``state.owned_codes``, so a fixture that could only build
    the initial squad could not carry a claim about any of them."""
    out = build_advice(tiny_inputs(my=tiny_my()), tiny_cfg(),
                       solver=ScriptedSolver())
    assert out.advice.mode == "weekly"
    assert out.state.owned_codes == tiny_squad()


def test_a_scripted_sweep_puts_the_three_solver_calls_in_order():
    """The sweep is the mode with three calls rather than one, and the order
    is what a source-order pin used to read off the text."""
    from gaffer.optimize.scenarios import ScenarioRun

    plan = a_plan()
    solver = ScriptedSolver(
        plan=plan, coherent=a_plan(captain=113),
        scenarios=ScenarioRun(plans=[plan, plan], attempted=2, completed=2,
                              failures=0, seed=99))
    out = build_advice(tiny_inputs(my=tiny_my()), tiny_cfg(scenarios_n=2),
                       solver=solver)
    assert solver.names == ["solve", "scenarios", "coherent"]
    # The seed the sweep was *asked* for moves with the gameweek; the seed the
    # report carries is the run's own, which is why both are worth reading.
    assert solver.calls[1][1]["seed"] == tiny_cfg().scenarios_seed + GW
    assert out.advice.scenarios["seed"] == 99


def test_a_scripted_alternative_reaches_the_advice_with_its_gap():
    """The alternatives are the fourth protocol call, and ``max_gap`` on the
    recording is the config knob that let them run at all."""
    alt = a_plan(buys=[118], sells=[112], gap=1.25)
    solver = ScriptedSolver(alternatives=[alt])
    out = build_advice(tiny_inputs(my=tiny_my()),
                       tiny_cfg(alt_plan_max_gap=2.0), solver=solver)
    assert solver.names == ["solve", "alternatives"]
    assert solver.calls[1][1]["max_gap"] == 2.0
    assert [r["gap"] for r in out.advice.alternative_plans] == [1.25]


def test_the_chip_pricers_are_recorded_though_the_solver_protocol_skips_them(
        monkeypatch):
    """The claim the fixture exists to let a test make about chips — that
    they are priced on the *untilted* pool — cannot be read off
    ``solver.calls``, because ``inputs.Solver`` leaves chip pricing out on
    purpose. :func:`recording` is where it is read instead."""
    chips = recording(monkeypatch, "chip_baseline")
    solver = ScriptedSolver()
    strategy = Strategy(lam=0.4, gap=10, weeks_left=5, stance="chase",
                        rival_name="Rival", cover_weights={112: 0.5})
    inputs = tiny_inputs(my=tiny_my(chips_by_gw={}), strategy=strategy,
                         league_eo={112: 60.0}, cover={112: 0.6})
    build_advice(inputs, tiny_cfg(), solver=solver)

    chip_pool = chips[0][0][0]
    solved_pool = solver.calls[0][1]["pool"]
    assert dict(zip(chip_pool["code"], chip_pool["ep"]))[112][GW] == \
        inputs.ep_by[(112, GW)]
    assert dict(zip(solved_pool["code"], solved_pool["ep"]))[112][GW] != \
        inputs.ep_by[(112, GW)]


def test_the_tiny_board_also_solves_for_real():
    """One real MILP over the fixture, so the shape is known to be solvable
    and a test that wants the real solver can have it."""
    from gaffer.inputs import MilpSolver

    out = build_advice(tiny_inputs(), tiny_cfg(), solver=MilpSolver())
    assert len(out.advice.xi) == 11
    assert out.advice.expected_pts > 0


def test_the_real_solver_picks_the_squad_the_scripted_plan_scripts():
    """The property the scripted default rests on (§5): the board's best
    player per position is also its cheapest, so a real solve of it returns
    :func:`tiny_squad` — and a test may script a plan without wondering
    whether the solver would have agreed."""
    from gaffer.inputs import MilpSolver

    out = build_advice(tiny_inputs(), tiny_cfg(), solver=MilpSolver())
    served = [p["code"] for p in out.advice.xi + out.advice.bench]
    assert sorted(served) == sorted(tiny_squad())
    assert [p["code"] for p in out.advice.xi] == a_plan().gw_plans[0].xi


def test_the_scripted_solver_is_the_protocol_s_second_adapter():
    """The review's test for a seam that is real rather than hypothetical:
    one adapter is a hypothetical seam, two make it a real one. The other
    half of the claim is ``test_inputs``'
    ``test_each_adapter_satisfies_its_protocol``, which could only name
    ``MilpSolver`` until this class existed."""
    from gaffer.inputs import Solver

    assert isinstance(ScriptedSolver(), Solver)
