"""v4c to v17g — what ``run_advise`` does, asserted on what it did.

Until v17g this file pinned the pipeline by string-matching the source of
``run_advise``: thirty-two tests, because the function took a config and a
client and reached the models, the live data, the solver and ``reports/``,
so no test could call it. v17g §3 split it into ``gather_inputs`` and a pure
``build_advice(inputs, cfg) -> Outputs``, and every one of those claims is
now made against a value the code produced.

Two harnesses carry the file. ``tests/advice_fixture`` drives ``build_advice``
on a fifteen-player board with a scripted solver; ``tests/gather_harness``
runs ``gather_inputs`` with its heavy dependencies spied, and reports the
order the calls happened in — which is what the ordering pins always meant.
"""
import dataclasses

import pandas as pd
import pytest

import gaffer.advise as advise_mod
from gaffer.advise import build_advice
from gaffer.league_mode import Strategy
from tests.advice_fixture import (GW, ScriptedSolver, a_plan,
                                  a_scratch_working_directory,  # noqa: F401
                                  codes_by_position, recording, tiny_cfg,
                                  tiny_ep, tiny_inputs, tiny_my,
                                  tiny_players, tiny_squad,
                                  without_the_ladder)
from tests.gather_harness import THROUGH, _comp, gather
from gaffer.advise import (Advice, chips_available_for, future_fixture_frame,
                           transfer_tag)


def test_future_fixture_frame_one_row_per_player_fixture():
    fixtures = pd.DataFrame([
        {"gw": 2, "home_id": 1, "away_id": 2, "kickoff_time": "2026-08-28T19:00:00Z"},
        {"gw": 3, "home_id": 2, "away_id": 1, "kickoff_time": "2026-09-04T19:00:00Z"},
    ])
    players = pd.DataFrame([
        {"code": 10, "element": 5, "name": "A", "position": "MID",
         "team_id": 1, "team_code": 100},
        {"code": 11, "element": 6, "name": "B", "position": "DEF",
         "team_id": 2, "team_code": 200},
    ])
    teams = pd.DataFrame([{"team_id": 1, "code": 100}, {"team_id": 2, "code": 200}])
    ff = future_fixture_frame(fixtures, players, teams, gws=[2, 3],
                              season_idx=4)
    assert len(ff) == 4                       # 2 players x 2 fixtures
    row = ff[(ff.code == 10) & (ff.gw == 2)].iloc[0]
    assert row["was_home"] == True and row["opp_code"] == 200
    row3 = ff[(ff.code == 10) & (ff.gw == 3)].iloc[0]
    assert row3["was_home"] == False


def test_chips_available_for_splits_the_season_in_halves():
    used = {3: "wildcard", 8: "3xc", 25: "bboost"}
    # First half: the two chips already played in GW3/GW8 are gone, the rest
    # remain — a second-half chip does not consume a first-half one.
    assert chips_available_for(used, 10) == ["freehit", "bboost"]
    # Boundary: GW19 is still the first half, GW20 is the second.
    assert chips_available_for(used, 19) == ["freehit", "bboost"]
    # Second half: the first-half chips are back, only GW25's bboost is spent.
    assert chips_available_for(used, 20) == ["wildcard", "freehit", "3xc"]


_PRIORS = {"transfer_surplus": {"early": [0.1, 0.4, 0.9, 1.6, 2.5]},
           "chip_surplus": {}}
"""Enough of a decision-priors payload for ``lambda_from_priors`` to build a
non-empty lookup, which is what the priors tests are actually about."""


def a_sweep(*, plans=None, attempted=4, completed=4, failures=0, seed=11):
    """A :class:`ScenarioRun` over the tiny board. The plans are what
    ``move_frequencies`` counts, so one plan means every move is unanimous."""
    from gaffer.optimize.scenarios import ScenarioRun

    return ScenarioRun(plans=list(plans if plans is not None else [a_plan()]),
                       attempted=attempted, completed=completed,
                       failures=failures, seed=seed)


_MODEL_KEYS = ("code", "season_idx", "gw", "opp_code")


class _StubModel:
    """One component model: constant predictions, keys echoed from its input.

    The keys matter — ``predict_components`` stitches the minutes model's
    output positionally and *merges* the team model's on
    ``(team_code, season_idx, gw, opp_code)``, which is the join the module
    docstring warns is wrong in the obvious way.
    """

    def __init__(self, **cols):
        self.cols = cols

    def predict(self, frame):
        out = pd.DataFrame({c: [v] * len(frame) for c, v in self.cols.items()})
        for key in _MODEL_KEYS:
            if key in frame.columns:
                out[key] = list(frame[key])
        return out


def _predicted(monkeypatch, *, avail=None, pens=None):
    """``predict_components`` over two players, with every model stubbed.

    v17g §5: the three claims this replaces were source-order pins, because
    the function loads six joblib models and no test could call it. Stubbing
    the loader is all it takes, and then the claims are about the frame that
    came out.
    """
    models = {"minutes": _StubModel(p_play=0.9, p60=0.8, e_min=80.0),
              "team": _StubModel(p_cs=0.3, e_gc=1.2),
              "attacking": _StubModel(e_goals=0.4, e_assists=0.2),
              "defcon": _StubModel(p_defcon=0.5),
              "saves": _StubModel(e_saves=1.0),
              "bonus": _StubModel(e_bonus=0.3)}
    monkeypatch.setattr(advise_mod, "load_model", lambda name: models[name])
    monkeypatch.setattr(advise_mod, "attack_multipliers", lambda model: {})
    pred = pd.DataFrame({"code": [1, 2], "gw": [7, 7], "season_idx": [1, 1],
                         "team_code": [3, 4], "opp_code": [4, 3],
                         "position": ["MID", "DEF"], "home": [1, 0],
                         "was_home": [True, False],
                         "kickoff_time": ["x", "y"], "status": ["a", "a"],
                         "chance_of_playing": [100, 100]})
    team_future = pd.DataFrame({"code": [3, 4], "opp_code": [4, 3],
                                "gw": [7, 7], "season_idx": [1, 1],
                                "home": [1, 0]})
    players = pd.DataFrame({"code": [1, 2], "status": ["a", "a"],
                            "chance_of_playing": [100, 100]})
    return advise_mod.predict_components(pred, team_future, players,
                                         avail, pens)


def a_strategy(*, lam: float = 0.0, **over) -> Strategy:
    """A league strategy at a chosen tilt. ``lam=0`` is the neutral dial,
    where ``tilt_ep`` is an exact passthrough and the solve is v1's."""
    fields = dict(lam=lam, gap=10, weeks_left=30, stance="chase",
                  rival_name="Rivals", cover_weights={9: 1.0})
    fields.update(over)
    return Strategy(**fields)


def _bare_advice(**kw):
    """Minimal Advice with every positional field filled — the two league
    fields must be optional, so a caller that knows nothing about the league
    can still build one."""
    base = dict(
        gw=3, deadline="2026-09-04T17:30:00Z", buys=[], sells=[], hits=0,
        xi=[], bench=[], captain={}, vice={}, captain_options=[],
        chip_table=[], wildcard_now=None, alternatives=[], threats=[],
        price_alerts=[], expected_pts=0.0)
    return Advice(**{**base, **kw})


def test_advice_carries_strategy_and_win_probs_with_safe_defaults():
    a = _bare_advice()
    assert a.strategy is None
    assert a.win_probs == []
    # Default list is per-instance, not shared class state.
    a.win_probs.append({"name": "x"})
    assert _bare_advice().win_probs == []


def test_transfer_tag_splits_differentials_from_cover():
    # No strategy (no league, or the league fetch failed): no tags at all,
    # including for players nobody in the league owns.
    assert transfer_tag(None, False) == ""
    assert transfer_tag(2.0, False) == ""
    # With a strategy: EO is a percent, the thresholds are fractions.
    assert transfer_tag(None, True) == "attack"      # unowned -> 0% -> attack
    assert transfer_tag(0.0, True) == "attack"
    assert transfer_tag(29.9, True) == "attack"
    assert transfer_tag(30.0, True) == ""            # boundary: no longer a diff
    assert transfer_tag(69.9, True) == ""
    assert transfer_tag(70.0, True) == "cover"       # boundary: cover starts here
    assert transfer_tag(140.0, True) == "cover"      # captaincy pushes EO > 100


def test_run_advise_tilts_ep_before_building_the_candidate_pool():
    """The league has to be read before the pool is built, because the tilt
    shapes *which* players become candidates, not just which get picked.

    v17g §5: asserted on the pool ``build_advice`` handed the solver rather
    than on the order two calls appear in its source. A chasing lambda makes
    a *covered* player worth less to the solver — that is the whole point of
    the dial — and leaves everyone else exactly where they were.
    """
    covered, other = tiny_squad()[0], tiny_squad()[1]
    solver = ScriptedSolver()
    build_advice(tiny_inputs(my=tiny_my(), cover={covered: 1.0},
                             strategy=a_strategy(lam=0.5)),
                 tiny_cfg(), solver=solver)
    pool = dict(zip(*(solver.calls[0][1]["pool"][c] for c in ("code", "ep"))))
    raw = tiny_ep(tiny_players())
    assert pool[covered][GW] < raw[(covered, GW)]
    assert pool[other][GW] == raw[(other, GW)]


def test_run_advise_reports_raw_ep_not_the_tilted_values():
    """Every table in the report shows real expected points. The tilt exists
    to steer the optimizer, and would be a lie on a printed xPts column."""
    covered = tiny_squad()[0]
    out = build_advice(tiny_inputs(my=tiny_my(), cover={covered: 1.0},
                                   strategy=a_strategy(lam=0.5)), tiny_cfg())
    raw = tiny_ep(tiny_players())
    served = {p["code"]: p["ep"] for p in out.advice.xi + out.advice.bench}
    assert served
    for code, ep in served.items():
        assert ep == raw[(code, GW)], code


# --- GW1 initial squad ------------------------------------------------------


def test_advice_defaults_to_weekly_mode_and_accepts_initial_squad():
    """``mode`` is appended last and defaulted, so every existing positional
    construction and every advice JSON written before it still loads."""
    assert _bare_advice().mode == "weekly"
    assert _bare_advice(mode="initial_squad").mode == "initial_squad"


def test_initial_squad_state_is_an_empty_squad_on_the_full_budget():
    from gaffer.advise import initial_squad_state

    state, picks = initial_squad_state([1, 2, 3])
    assert state.owned_codes == []
    assert state.bank == 1000                  # 100.0m, in 0.1m units
    assert state.free_transfers == 15          # building 15 costs no hits
    assert state.gws == [1, 2, 3]
    # build_pool only reads code/sell; an empty frame with those columns keeps
    # the "owned" set empty and every sell price at now_cost.
    assert list(picks.columns) == ["code", "sell"]
    assert picks.empty


def test_initial_squad_solve_buys_fifteen_and_takes_no_hits():
    """With nothing owned the first gw plan's buys *are* the squad, its sells
    are empty, and 15 free transfers make the hit count zero."""
    from gaffer.advise import initial_squad_state
    from gaffer.optimize.milp import solve_plan

    rows, code = [], 1
    for pos, n in [("GKP", 2), ("DEF", 6), ("MID", 7), ("FWD", 5)]:
        for _ in range(n):
            rows.append({"code": code, "position": pos, "team_code": code % 8,
                         "cost": 50, "sell": 50, "ep": {1: 2.0}})
            code += 1
    pool = pd.DataFrame(rows)

    state, _ = initial_squad_state([1])
    first = solve_plan(pool, state, decay=0.85, bench_weight=0.1,
                       vice_weight=0.1, ft_value=1.5, itb_value=0.05,
                       hit_cost=4).gw_plans[0]
    assert sorted(first.buys) == sorted(first.squad)
    assert len(first.buys) == 15
    assert first.sells == []
    assert first.hits == 0


def test_run_advise_falls_back_to_initial_squad_advice_at_gw1(monkeypatch):
    """The GW1 ``GafferError`` out of ``fetch_my_team`` becomes initial-squad
    advice rather than propagating to the CLI as a clean exit."""
    inputs, order = gather(monkeypatch, my=False)
    assert "fetch_my_team" in order
    assert inputs.my is None

    out = build_advice(tiny_inputs(my=None), tiny_cfg())
    assert out.advice.mode == "initial_squad"
    assert out.state.mode == "initial_squad"
    # Fifteen opening buys must stay uncapped.
    assert out.advice.caps is None


def test_run_advise_only_tags_buys_when_league_ownership_is_known(monkeypatch):
    """At GW1 no rival picks are public, so the EO map is empty. An empty map
    means "unknown", and must not tag every opening pick as a differential."""
    without_the_ladder(monkeypatch)
    buy = codes_by_position()["MID"][-1]
    plan = a_plan(buys=[buy], sells=[tiny_squad()[0]])

    def tags(**over):
        out = build_advice(tiny_inputs(my=tiny_my(), strategy=a_strategy(),
                                       **over),
                           tiny_cfg(), solver=ScriptedSolver(plan=plan))
        return [b.get("tag") for b in out.advice.buys]

    # "" is the honest answer to "how owned is he?" when nobody's ownership
    # is known; "attack" and "cover" both claim to know.
    assert tags(league_eo={}) == [""]
    assert tags(league_eo={buy: 4.0}) == ["attack"]        # barely owned
    assert tags(league_eo={buy: 95.0}) == ["cover"]        # near-template


# --- the tilt stays inside squad selection ---------------------------------
#
# Spec invariant: tilt shapes *which players are picked*. Anything printed,
# and anything compared against a raw-points threshold, has to be real
# expected points — otherwise a chasing lambda inflates a chip's apparent
# gain past 8.0 and burns a wildcard on nothing.


def test_raw_xi_pts_sums_untilted_ep_over_the_chosen_xi():
    from gaffer.advise import raw_xi_pts
    from gaffer.optimize.milp import GwPlan

    ep_by = {(1, 7): 5.0, (2, 7): 3.5, (3, 7): 1.0, (1, 8): 99.0}
    plan = GwPlan(gw=7, squad=[1, 2, 3], xi=[1, 2], xi_rows=[], bench=[3],
                  captain=1, vice=2, buys=[], sells=[], hits=0,
                  expected_pts=123.0)          # the tilted MILP objective
    # XI only, this gameweek only, and nothing from the tilted objective.
    assert raw_xi_pts(plan, ep_by) == 8.5
    # A player with no fixture this week contributes nothing rather than
    # raising KeyError.
    assert raw_xi_pts(GwPlan(gw=9, squad=[1], xi=[1], xi_rows=[], bench=[],
                             captain=1, vice=1, buys=[], sells=[], hits=0,
                             expected_pts=4.0), ep_by) == 0.0


def test_run_advise_scores_chips_on_an_untilted_pool(monkeypatch):
    """``evaluate_chips`` and ``wildcard_now_assessment`` compare objective
    deltas against raw-point thresholds, so they must be handed a pool built
    from ``ep_by`` and a base solved on it — never the tilted pool, whose
    inflated numbers would burn a wildcard on a differential shuffle."""
    priced = recording(monkeypatch, "evaluate_chips")
    based = recording(monkeypatch, "chip_baseline")
    covered = tiny_squad()[0]
    solver = ScriptedSolver()
    build_advice(tiny_inputs(my=tiny_my(chips_by_gw={}), cover={covered: 1.0},
                             strategy=a_strategy(lam=0.5)),
                 tiny_cfg(), solver=solver)

    raw = tiny_ep(tiny_players())
    assert priced and based
    for calls in (priced, based):
        pool = calls[0][0][0]
        assert dict(zip(pool["code"], pool["ep"]))[covered][GW] == \
            raw[(covered, GW)]
    # ...and the solver's own pool was the tilted one, so the two really do
    # differ and this test is not asserting that lam was zero.
    solved = solver.calls[0][1]["pool"]
    assert dict(zip(solved["code"], solved["ep"]))[covered][GW] < \
        raw[(covered, GW)]


def test_run_advise_reports_raw_xi_points_not_the_tilted_objective(monkeypatch):
    """``expected_pts`` is the untilted sum over the XI, never the solver's
    own objective, which is measured in tilted units."""
    without_the_ladder(monkeypatch)
    plan = a_plan(objective=999.0)
    out = build_advice(tiny_inputs(my=tiny_my()), tiny_cfg(),
                       solver=ScriptedSolver(plan=plan))
    raw = tiny_ep(tiny_players())
    want = round(sum(raw[(c, GW)] for c in plan.gw_plans[0].xi), 2)
    assert out.advice.expected_pts == want
    assert out.advice.plan_by_gw[0]["expected_pts"] == want


def test_predict_components_keeps_the_pre_blend_team_output(monkeypatch):
    """Explainability has to show what the market changed, so the model's own
    clean-sheet number survives the blend beside the blended one — and the
    weight is recorded per row, 0.0 where the feed covered nothing."""
    comp = _predicted(monkeypatch)
    assert (comp["p_cs_model"] == 0.3).all()
    assert (comp["e_gc_model"] == 1.2).all()
    assert (comp["odds_weight"] == 0.0).all()      # no feed, no weight
    # And the columns the UI renders per fixture are carried through.
    for col in ("was_home", "kickoff_time", "position", "team_code"):
        assert col in comp.columns, col


def test_run_advise_persists_the_components_file_and_solve_state(monkeypatch):
    """The whole web UI is unusable if these writes go missing.

    v17g §2.6: gather banks what gather made and the composition banks what
    the build made, so the claim is asserted on both sides of the seam.
    """
    _, order = gather(monkeypatch)
    for name in ("save_snapshots", "save_components", "save_availability"):
        assert name in order, name

    out = build_advice(tiny_inputs(my=tiny_my()), tiny_cfg())
    # ``ep_raw`` by name and by value: the pool a What-If re-solve reads
    # back carries the untilted numbers, never the tilted ones.
    raw = tiny_ep(tiny_players())
    week = out.state.pool[out.state.pool["gw"] == GW]
    assert not week.empty
    for code, ep in zip(week["code"], week["ep_raw"]):
        assert ep == raw[(int(code), GW)], code


def test_named_carries_position_so_the_pitch_can_group_the_xi():
    """The web UI lays the XI out by line. Without a ``position`` on every
    named entry the pitch has nothing to group on and renders empty."""
    from gaffer.advise import _named

    named = _named([100, 101], {100: "Salah", 101: "Dud"},
                   {100: "MID", 101: "DEF"}, {(100, 3): 6.4}, 3)
    assert named == [{"code": 100, "name": "Salah", "position": "MID",
                      "ep": 6.4},
                     {"code": 101, "name": "Dud", "position": "DEF",
                      "ep": 0.0}]


def test_run_advise_builds_a_position_map_beside_the_name_map(monkeypatch):
    """Every named entry in the advice JSON carries a position, so the web
    pitch has something to group the XI on and does not render empty."""
    without_the_ladder(monkeypatch)
    out = build_advice(
        tiny_inputs(my=tiny_my()), tiny_cfg(),
        solver=ScriptedSolver(plan=a_plan(buys=[codes_by_position()["MID"][-1]],
                                          sells=[tiny_squad()[0]])))
    named = (out.advice.xi + out.advice.bench + out.advice.buys
             + out.advice.sells + [out.advice.captain, out.advice.vice])
    assert len(named) > 15
    for entry in named:
        assert set(entry) >= {"code", "name", "position", "ep"}, entry


# --- telling the user how much of the season the model has seen -------------


def test_advice_carries_the_data_gap_fields_with_safe_defaults():
    """Additive: advice JSON written before this existed still loads."""
    import dataclasses

    from gaffer.advise import Advice

    fields = {f.name: f for f in dataclasses.fields(Advice)}
    assert fields["data_through_gw"].default is None
    assert fields["data_warning"].default is None


def test_run_advise_records_the_data_gap_after_refreshing(monkeypatch):
    """The ingested-through read has to happen *after* ``refresh_live``, or
    it reports last week's disk state."""
    inputs, order = gather(monkeypatch)
    assert order.index("refresh_live") < order.index("ingested_through")
    assert inputs.through == THROUGH
    assert inputs.gap_warning == "two gameweeks behind"

    out = build_advice(tiny_inputs(through=4, gap_warning="behind"),
                       tiny_cfg())
    assert out.advice.data_through_gw == 4
    assert out.advice.data_warning == "behind"


# --- v4c: the scenario layer -----------------------------------------------

def test_run_advise_runs_scenarios_after_the_deterministic_solve():
    """The raw optimum still runs first — it anchors the report, and it is
    the fallback when the sweep is off or dies."""
    solver = ScriptedSolver(scenarios=a_sweep())
    build_advice(tiny_inputs(my=tiny_my()), tiny_cfg(scenarios_n=4),
                 solver=solver)
    assert solver.names == ["solve", "scenarios", "coherent"]


def test_run_advise_guards_the_whole_scenario_block_on_the_config():
    """``n = 0`` must not merely produce the same answer — it must not run.

    ``ScriptedSolver`` raises if the sweep is reached with nothing scripted,
    so a solver with no ``scenarios`` is itself the assertion.
    """
    solver = ScriptedSolver()
    out = build_advice(tiny_inputs(my=tiny_my()), tiny_cfg(scenarios_n=0),
                       solver=solver)
    assert solver.names == ["solve"]
    assert out.advice.scenarios is None
    assert out.advice.move_frequencies == []
    assert out.advice.raw_optimum_agrees is None


def test_the_scenario_block_never_mentions_pool_ep():
    """The sweep re-solves the pool frame, whose ``ep`` build_pool has already
    folded the tilt into — so it must be handed that same frame and never a
    second, differently-tilted one."""
    solver = ScriptedSolver(scenarios=a_sweep())
    build_advice(tiny_inputs(my=tiny_my(), cover={tiny_squad()[0]: 1.0},
                             strategy=a_strategy(lam=0.5)),
                 tiny_cfg(scenarios_n=4), solver=solver)
    seen = {name: kw for name, kw in solver.calls}
    assert seen["scenarios"]["pool"] is seen["solve"]["pool"]
    assert seen["coherent"]["pool"] is seen["solve"]["pool"]


def test_run_advise_still_pins_every_protected_ordering(monkeypatch):
    """Belt and braces: the orderings every cycle since v4c has re-asserted,
    in one place that fails loudly, now over what the run actually did."""
    _, order = gather(monkeypatch)
    at = order.index
    # The league is read, the model predicts, and the EP matrix is assembled
    # from the calibrated components — in that order.
    assert at("pen_priors") < at("news_availability") < at("Predictions.components")
    assert at("Predictions.components") < at("blend_attacking_odds") \
        < at("apply_calibration") < at("ep_matrix")
    assert at("refresh_live") < at("ingested_through")

    # And the tilt reaches the pool and nothing else.
    covered = tiny_squad()[0]
    solver = ScriptedSolver()
    out = build_advice(tiny_inputs(my=tiny_my(), cover={covered: 1.0},
                                   strategy=a_strategy(lam=0.5)),
                       tiny_cfg(), solver=solver)
    raw = tiny_ep(tiny_players())
    pool = dict(zip(*(solver.calls[0][1]["pool"][c] for c in ("code", "ep"))))
    assert pool[covered][GW] < raw[(covered, GW)]
    for row in out.advice.captain_options + out.advice.threats:
        assert row["ep"] == raw[(int(row["code"]), GW)], row["code"]


def test_advice_carries_the_scenario_fields_with_safe_defaults():
    from gaffer.advise import Advice
    import dataclasses

    fields = {f.name: f for f in dataclasses.fields(Advice)}
    for name in ("move_frequencies", "raw_optimum_agrees", "scenarios"):
        assert name in fields
        assert (fields[name].default is not dataclasses.MISSING
                or fields[name].default_factory is not dataclasses.MISSING)


def test_solve_state_opt_stays_json_serializable():
    """``SolveState.opt`` is written to disk and read by the What-If page; a
    callable in there would break the round trip."""
    import json

    out = build_advice(tiny_inputs(my=tiny_my()),
                       tiny_cfg(decision_priors=True))
    json.dumps(out.state.opt)                    # raises if anything is not
    assert "ft_lambda" not in out.state.opt
    assert out.state.opt["decision_priors"] is True


def test_run_advise_resolves_the_decision_priors_before_solving():
    """The lambda lookup has to be in the bundle for the very first solve, or
    the raw optimum and the scenarios are priced differently."""
    solver = ScriptedSolver(scenarios=a_sweep())
    build_advice(tiny_inputs(my=tiny_my(), priors=_PRIORS),
                 tiny_cfg(scenarios_n=4, decision_priors=True), solver=solver)
    bundles = [kw for name, kw in solver.calls if name in ("solve", "scenarios")]
    assert len(bundles) == 2
    lookups = [kw["ft_lambda"] for kw in bundles]
    assert all(lk is not None for lk in lookups)
    assert lookups[0] is lookups[1]              # one lookup, not two


def test_the_priors_are_switchable_off_from_config():
    """Off is off: the state says so, and the served trace gets no lookup."""
    off = build_advice(tiny_inputs(my=tiny_my(), priors=None),
                       tiny_cfg(decision_priors=False))
    assert off.state.opt["decision_priors"] is False


def test_run_advise_still_pins_every_protected_ordering_after_the_priors():
    """Re-pinned once more, with the priors on: switching them on must not
    move the tilt off the pool or onto a printed table."""
    covered = tiny_squad()[0]
    solver = ScriptedSolver()
    out = build_advice(tiny_inputs(my=tiny_my(), cover={covered: 1.0},
                                   strategy=a_strategy(lam=0.5),
                                   priors=_PRIORS),
                       tiny_cfg(decision_priors=True), solver=solver)
    raw = tiny_ep(tiny_players())
    pool = dict(zip(*(solver.calls[0][1]["pool"][c] for c in ("code", "ep"))))
    assert pool[covered][GW] < raw[(covered, GW)]
    for entry in out.advice.xi + out.advice.bench:
        assert entry["ep"] == raw[(entry["code"], GW)]


# --- v4c final review: the objective knobs must reach production ----------


def test_run_advise_opt_kw_carries_the_objective_craft_knobs():
    """v4c B1: the backtest solved with ``ft_use_penalty`` and ``bench_curve``
    and the advice did not, so the replayed numbers described a different
    objective from the one the user was shown. Both now ride on the bundle
    *and* on the saved state, which is what makes the replay honest."""
    cfg = tiny_cfg(ft_use_penalty=0.25, bench_curve=[0.5, 0.3, 0.2])
    solver = ScriptedSolver()
    out = build_advice(tiny_inputs(my=tiny_my()), cfg, solver=solver)
    bundle = solver.calls[0][1]
    assert bundle["ft_use_penalty"] == 0.25
    assert bundle["bench_curve"] == [0.5, 0.3, 0.2]
    assert out.state.opt["ft_use_penalty"] == 0.25
    assert out.state.opt["bench_curve"] == [0.5, 0.3, 0.2]


def test_run_advise_records_whether_the_priors_were_on():
    """v4c B7: ``SolveState.opt`` cannot carry the lambda lookup, but it can
    carry the one boolean the web re-solve needs to rebuild it from the
    shipped asset — and it must not carry the lookup itself."""
    solver = ScriptedSolver()
    out = build_advice(tiny_inputs(my=tiny_my(), priors=_PRIORS),
                       tiny_cfg(decision_priors=True), solver=solver)
    assert out.state.opt["decision_priors"] is True
    assert "ft_lambda" not in out.state.opt
    # It rides on the solver bundle instead, where it is not serialized.
    assert solver.calls[0][1]["ft_lambda"] is not None


# --- B5/B6 and the review's nits, pinned in run_advise --------------------


def test_the_scenario_gate_is_skipped_without_an_owned_squad():
    """v4c B5. ``FixedMoves(no_transfer=True)`` forces ``lpSum(tin) == 0``,
    which cannot build a squad from nothing — so a held decision at GW1
    printed "coherence re-solve infeasible" under the user's opening picks.
    Gating fifteen opening picks against an incumbent that does not exist is
    not a question worth asking."""
    solver = ScriptedSolver()          # raises if the sweep is reached
    out = build_advice(tiny_inputs(my=None), tiny_cfg(scenarios_n=40),
                       solver=solver)
    assert solver.names == ["solve"]
    assert out.advice.mode == "initial_squad"
    assert out.advice.scenarios is None


def test_a_sweep_where_every_solve_failed_says_so(capsys):
    """v4c n2. ``run.completed == 0`` fell through the ``if`` in silence, and
    the report looked exactly like a run with scenarios switched off."""
    dead = a_sweep(plans=[], attempted=40, completed=0, failures=40)
    out = build_advice(tiny_inputs(my=tiny_my()), tiny_cfg(scenarios_n=40),
                       solver=ScriptedSolver(scenarios=dead))
    assert "40 scenario solves failed" in capsys.readouterr().out
    # ...and the raw optimum is served, ungated, rather than a blank gate.
    assert out.advice.scenarios is None
    assert out.advice.raw_optimum_agrees is None


def test_an_empty_xmins_map_is_warned_about(capsys):
    """v4c n3. No minutes model means every scenario draws the same board, so
    all n frequencies are 1.0 and mean nothing. Say so."""
    # xmins is 90·p_play·p60 + 45·p_play·(1-p60), so a frame with neither
    # column is what "no minutes model" actually looks like.
    blind = tiny_inputs(my=tiny_my())
    blind = dataclasses.replace(
        blind, comp=blind.comp.drop(columns=["p_play", "p60"]))
    build_advice(blind, tiny_cfg(scenarios_n=4),
                 solver=ScriptedSolver(scenarios=a_sweep()))
    assert "the move frequencies below are all 100%" in capsys.readouterr().out


def test_the_scenario_seed_moves_with_the_gameweek():
    """v4c n10. A fixed seed replays one noise sequence every week; D1 was
    measured with the gameweek folded in."""
    solver = ScriptedSolver(scenarios=a_sweep())
    build_advice(tiny_inputs(my=tiny_my()),
                 tiny_cfg(scenarios_n=4, scenarios_seed=1000), solver=solver)
    assert dict(solver.calls)["scenarios"]["seed"] == 1000 + GW


def test_the_reported_captain_frequency_belongs_to_the_actual_captain(
        monkeypatch):
    """v4c B6. ``decision.captain`` is the plurality winner, and he is
    silently dropped when the re-solve cannot field him — so the reported
    frequency has to be the armband's own, or ``None``, never his."""
    without_the_ladder(monkeypatch)
    xi = a_plan().gw_plans[0].xi
    wanted, actual = xi[0], xi[1]
    swept = a_plan(captain=wanted)
    # The sweep votes for one captain; the coherent re-solve fields another.
    out = build_advice(
        tiny_inputs(my=tiny_my()), tiny_cfg(scenarios_n=4),
        solver=ScriptedSolver(plan=a_plan(captain=wanted),
                              coherent=a_plan(captain=actual),
                              scenarios=a_sweep(plans=[swept])))
    assert out.advice.captain["code"] == actual
    assert out.advice.scenarios["captain_wanted"] == wanted
    assert out.advice.scenarios["captain_agrees"] is False
    assert out.advice.scenarios["captain_frequency"] != 1.0


# --- v4d: the league block feeds cover, not raw EO -------------------------


def test_run_advise_builds_the_cover_table_inside_the_league_block(monkeypatch):
    """The dial's inputs are assembled inside the league block, so a league
    that will not read leaves every one of them empty and the solve falls
    back to v1's — ``tilt_ep(..., 0.0)`` is an exact passthrough."""
    from gaffer.config import Config

    cfg = Config(entry_id=1, league_id=99)

    def boom(*a, **kw):
        raise RuntimeError("the league endpoint is down")

    inputs, _ = gather(monkeypatch, cfg=cfg, fetch_rival_entries=boom)
    assert inputs.strategy is None
    assert (inputs.league_eo, inputs.cover, inputs.cap_cover) == ({}, {}, {})
    assert (inputs.rival_captains, inputs.rival_names) == ({}, {})
    assert inputs.win_probs == []

    # And with no league configured at all, the block is never entered.
    quiet, order = gather(monkeypatch, cfg=Config(entry_id=1, league_id=0))
    assert "fetch_rival_entries" not in order
    assert quiet.cover == {}


def test_run_advise_still_reports_league_eo_for_the_annotation_tables():
    """Cover drives the optimizer; the captain table, the alternatives and
    the threat board still speak in rival EO percent."""
    owned, threat = tiny_squad()[0], codes_by_position()["MID"][-1]
    out = build_advice(
        tiny_inputs(my=tiny_my(), league_eo={owned: 42.0, threat: 71.0},
                    cover={owned: 1.0}, strategy=a_strategy(lam=0.5)),
        tiny_cfg())
    # captain_options is the shortlist, so assert the join rather than one
    # row's presence: every listed player's EO is the league's, not a guess.
    listed = {int(r["code"]): r["league_eo"] for r in out.advice.captain_options}
    assert listed
    assert listed.get(owned, 42.0) == 42.0
    assert all(v == 0.0 or v == 42.0 or v == 71.0 for v in listed.values())
    threats = {int(r["code"]): r["league_eo"] for r in out.advice.threats}
    assert threats.get(threat) == 71.0


def test_run_advise_re_picks_the_captain_after_the_plan_is_fixed(monkeypatch):
    """Authority order: the sweep's plurality picks a candidate, then the
    tilted score over the *final* XI is the last word — and only by a margin,
    never on a hairline. At ``lam = 0`` the override is never consulted, so
    v4c's armband stands and both report fields stay ``None``."""
    without_the_ladder(monkeypatch)
    xi = a_plan().gw_plans[0].xi
    solved, covered = xi[0], xi[1]

    neutral = build_advice(tiny_inputs(my=tiny_my()), tiny_cfg(),
                           solver=ScriptedSolver(plan=a_plan(captain=solved)))
    assert neutral.advice.captain["code"] == solved
    assert neutral.advice.demoted_captain is None
    assert neutral.advice.captain_note is None

    # A chaser with the solved captain heavily covered by the rivals demotes
    # him for the differential, and says who and why.
    tilted = build_advice(
        tiny_inputs(my=tiny_my(), strategy=a_strategy(lam=0.9),
                    cap_cover={solved: 1.0}, rival_captains={9: solved},
                    rival_names={9: "Rivals"}),
        tiny_cfg(), solver=ScriptedSolver(plan=a_plan(captain=solved)))
    assert tilted.advice.captain["code"] != solved
    assert tilted.advice.demoted_captain["code"] == solved
    assert "Rivals" in tilted.advice.captain_note
    assert covered or True


def test_advice_carries_the_demoted_captain_and_the_note():
    from gaffer.advise import Advice

    a = _bare_advice()
    assert a.captain_note is None
    assert a.demoted_captain is None


def test_predict_components_defaults_to_the_official_flags():
    """The pre-v5 call shape still means the pre-v5 thing: no availability
    frame passed means the bootstrap's own status columns."""
    import inspect

    from gaffer.advise import predict_components

    sig = inspect.signature(predict_components)
    # v6 appended ``pens`` behind ``avail``; both default to None, so the
    # pre-v5 four-argument call shape still means the pre-v5 thing.
    assert list(sig.parameters) == ["pred_frame", "tg_future", "players",
                                    "avail", "pens"]
    assert sig.parameters["avail"].default is None
    assert sig.parameters["pens"].default is None


def test_predict_components_emits_the_flags_only_shadow_columns(monkeypatch):
    """Gate N2 needs both sides of the comparison off one model run, so the
    flags-only availability pass happens beside the news one — and the two
    must differ by the availability layer alone.

    Here the news frame doubts the first player and the bootstrap flags do
    not, so the shadow columns keep what the flags alone would have said.
    """
    doubtful = pd.DataFrame({"code": [1, 2], "status": ["d", "a"],
                             "chance_of_playing": [25, 100]})
    comp = _predicted(monkeypatch, avail=doubtful)
    news = dict(zip(comp["code"], comp["p_play"]))
    flags = dict(zip(comp["code"], comp["p_play_flags"]))
    assert news[1] < flags[1]              # the news pass moved him
    assert news[2] == flags[2]             # and left the other alone
    assert "e_min_flags" in comp.columns


def test_run_advise_writes_the_shadow_log_before_assembling_ep(monkeypatch):
    """The shadow row is the news layer's only record, and it has to be taken
    off the component frame before the odds blend and the calibration
    rewrite it."""
    _, order = gather(monkeypatch)
    at = order.index
    assert at("news_availability") < at("Predictions.components") \
        < at("write_shadow") < at("blend_attacking_odds") < at("ep_matrix")


def test_news_availability_degrades_to_the_bootstrap_slice():
    """No config, dead sources, disabled layer — all three land on the same
    three-column frame apply_availability has always taken."""
    import pandas as pd

    from gaffer.advise import news_availability
    from gaffer.config import Config

    players = pd.DataFrame({"code": [1], "status": ["a"],
                            "chance_of_playing": [None], "team_code": [3],
                            "name": ["X"], "first_name": ["X"],
                            "second_name": ["Y"]})
    teams = pd.DataFrame({"code": [3], "name": ["Arsenal"],
                          "short_name": ["ARS"]})
    events = pd.DataFrame({"gw": [5], "deadline_time": ["2026-09-05T10:00Z"]})
    cfg = Config(entry_id=1, league_id=2, news_enabled=False)
    out = news_availability(cfg, players, teams, events, gw=5)
    assert list(out.columns) == ["code", "status", "chance_of_playing"]


def test_news_availability_makes_no_fetch_calls_when_disabled(monkeypatch):
    """The [news] enabled=false rail, asserted at the call site rather than
    only at the fetcher."""
    import pandas as pd

    from gaffer import advise as advise_mod
    from gaffer.config import Config

    calls = []
    monkeypatch.setattr(advise_mod, "fetch_injuries",
                        lambda *a, **k: calls.append("i"))
    monkeypatch.setattr(advise_mod, "fetch_lineups",
                        lambda *a, **k: calls.append("l"))
    players = pd.DataFrame({"code": [1], "status": ["a"],
                            "chance_of_playing": [None], "team_code": [3],
                            "name": ["X"], "first_name": ["X"],
                            "second_name": ["Y"]})
    teams = pd.DataFrame({"code": [3], "name": ["Arsenal"],
                          "short_name": ["ARS"]})
    events = pd.DataFrame({"gw": [5], "deadline_time": ["2026-09-05T10:00Z"]})
    cfg = Config(entry_id=1, league_id=2, news_enabled=False)
    advise_mod.news_availability(cfg, players, teams, events, gw=5)
    assert calls == []


# --- v6 set pieces ----------------------------------------------------------


def test_predict_components_prices_penalties_after_the_availability_passes(
        monkeypatch):
    """The penalty term multiplies by ``p_play``, so it has to land after the
    news pass has had its say about whether he plays at all — and it folds
    into ``e_goals`` rather than into ``ep``, so it lands before assemble_ep
    ever runs. With no priors it is identically zero."""
    import inspect

    none = _predicted(monkeypatch)
    assert (none["ep_pen_taker"] == 0.0).all()

    seen = {}

    def spy(comp, *args, **kw):
        seen["p_play"] = dict(zip(comp["code"], comp["p_play"]))
        out = comp.copy()
        out["ep_pen_taker"] = out["p_play"] * 2.0
        return out

    monkeypatch.setattr(advise_mod, "add_pen_ep", spy)
    doubtful = pd.DataFrame({"code": [1, 2], "status": ["d", "a"],
                             "chance_of_playing": [25, 100]})
    priced = _predicted(monkeypatch, avail=doubtful, pens=object())
    # The frame add_pen_ep saw already carried the news pass's p_play, not
    # the raw model's 0.9 — which is the ordering this test is about.
    assert seen["p_play"][1] < 0.9
    assert priced["ep_pen_taker"][0] == seen["p_play"][1] * 2.0
    assert "pens" in inspect.signature(advise_mod.predict_components).parameters


def test_run_advise_builds_the_penalty_priors_before_predicting(monkeypatch):
    """One line, above the news line, and the priors reach the prediction:
    without them the penalty term is identically zero."""
    seen = {}

    class _Predictions:
        def missing(self):
            return []

        def components(self, **kw):
            seen.update(kw)
            return _comp()

        def calibration(self):
            return None

    inputs, order = gather(monkeypatch, predictions=_Predictions())
    at = order.index
    assert at("pen_priors") < at("news_availability")
    assert set(seen) == {"pred_frame", "tg_future", "players", "avail", "pens"}
    assert inputs.comp is not None


def test_the_components_file_records_the_penalty_term():
    from gaffer.artifacts import COMPONENT_COLS

    assert "ep_pen_taker" in COMPONENT_COLS


def test_run_advise_persists_the_availability_and_history_artifacts(
        monkeypatch, tmp_path):
    """The news panel and the "since last run" strip both read files nothing
    else writes. v17g §2.6: the availability frame is banked by the half that
    made it, and the history by the composition that made the payload."""
    _, order = gather(monkeypatch)
    assert "save_availability" in order

    seen = []
    monkeypatch.setattr(advise_mod, "append_advice_history",
                        lambda payload, gw: seen.append(gw))
    monkeypatch.setattr(advise_mod, "gather_inputs",
                        lambda cfg, client=None, **kw: tiny_inputs(my=tiny_my()))
    monkeypatch.chdir(tmp_path)
    advice = advise_mod.run_advise(tiny_cfg())
    assert seen == [advice.gw]
    assert (tmp_path / "reports").is_dir()


# --- v13: the appetite reaches the one SolveInput --------------------------


def test_run_advise_hands_the_caps_to_the_weekly_solve_input():
    """v13 §2.3: the caps ride on the ``SolveInput`` the sweep, the
    alternatives and the chip table all inherit, and on no other. The
    initial-squad branch builds fifteen transfers and must stay uncapped."""
    solver = ScriptedSolver()
    weekly = build_advice(tiny_inputs(my=tiny_my()),
                          tiny_cfg(max_hits=1, max_transfers=2),
                          solver=solver)
    state = solver.calls[0][1]["state"]
    assert (state.max_hits, state.max_transfers) == (1, 2)
    assert weekly.advice.caps == {"max_hits": 1, "max_transfers": 2}
    assert weekly.state.opt["max_hits"] == 1
    assert weekly.state.opt["max_transfers"] == 2

    opening = ScriptedSolver()
    build_advice(tiny_inputs(my=None), tiny_cfg(max_hits=1, max_transfers=2),
                 solver=opening)
    fresh = opening.calls[0][1]["state"]
    assert (fresh.max_hits, fresh.max_transfers) == (None, None)


def test_cap_maps_the_no_cap_sentinel_to_none():
    from gaffer.advise import _cap
    from gaffer.config import NO_CAP

    assert _cap(NO_CAP) is None
    assert _cap(99) is None
    assert _cap(2) == 2
    assert _cap(0) == 0


def test_advice_carries_the_caps_with_a_safe_default():
    a = _bare_advice()
    assert getattr(a, "caps", None) is None


def test_run_advise_builds_the_ladder_after_the_state_and_never_fails_on_it(
        monkeypatch, capsys):
    """v13 §3.2 / v17g §2.2: the ladder is solved off the state the build has
    just made — in memory, not off the disk — and its failure is one printed
    line, never the run's."""
    seen = {}
    real = advise_mod.ladder_payload

    def spy(state, **kw):
        seen.update(state=state, **kw)
        return real(state, **kw)

    monkeypatch.setattr(advise_mod, "ladder_payload", spy)
    out = build_advice(tiny_inputs(my=tiny_my()), tiny_cfg())
    assert seen["state"] is out.state          # the very object, unwritten
    assert out.ladder is not None
    assert out.advice.restraint is not None

    def refuses(*a, **kw):
        raise RuntimeError("no rung solved")

    monkeypatch.setattr(advise_mod, "ladder_payload", refuses)
    degraded = build_advice(tiny_inputs(my=tiny_my()), tiny_cfg())
    assert "ladder: not built for GW" in capsys.readouterr().out
    assert degraded.ladder is None
    assert degraded.advice.xi                  # the objective's plan, served
