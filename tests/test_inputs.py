"""v17g §2.7, §2.8 — the frozen seam between gather and build, and the
recording that gives it a second adapter."""
from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from gaffer.inputs import (Inputs, LiveModels, MilpSolver, Outputs,
                           Predictions, RecordedComponents, Solver,
                           load_inputs, save_inputs)


def _inputs(**over) -> Inputs:
    """A small, complete Inputs. Two players, one gameweek, no league."""
    players = pd.DataFrame([
        {"code": 100, "name": "In", "position": "MID", "team_code": 1,
         "now_cost": 80, "price_change_percent": 0.0},
        {"code": 200, "name": "Out", "position": "MID", "team_code": 2,
         "now_cost": 75, "price_change_percent": 0.0}])
    comp = pd.DataFrame([{"code": 100, "gw": 7, "p_play": 0.9, "ep": 6.0},
                         {"code": 200, "gw": 7, "p_play": 0.8, "ep": 4.0}])
    fields = dict(
        gw=7, gws=[7, 8], deadline="2026-10-01T17:30:00Z", through=6,
        gap_warning=None, players=players, comp=comp, components=comp.copy(),
        ep_named=pd.DataFrame([{"code": 100, "gw": 7, "ep": 6.0,
                                "name": "In", "position": "MID"}]),
        ep_by={(100, 7): 6.0, (200, 7): 4.0}, my=None, league_eo={},
        cover={}, cap_cover={}, rival_captains={}, rival_names={},
        strategy=None, win_probs=[], priors=None, dgw_probs={},
        prior_advice=None, price_timing=True, price_fall={})
    fields.update(over)
    return Inputs(**fields)


def test_inputs_is_frozen_so_a_pass_cannot_edit_the_board():
    with pytest.raises(dataclasses.FrozenInstanceError):
        _inputs().gw = 8


def test_outputs_is_frozen_and_carries_the_three_things_run_advise_banks():
    assert [f.name for f in dataclasses.fields(Outputs)] == [
        "advice", "state", "ladder"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        Outputs(advice=None, state=None, ladder=None).ladder = {}


def test_the_round_trip_returns_every_field_unchanged(tmp_path):
    """v17g §2.8: the recording is the second adapter of the Inputs seam, so
    it has to be exact, not close."""
    original = _inputs()
    save_inputs(original, tmp_path)
    back = load_inputs(tmp_path)
    for f in dataclasses.fields(Inputs):
        a, b = getattr(original, f.name), getattr(back, f.name)
        if isinstance(a, pd.DataFrame):
            pd.testing.assert_frame_equal(a, b)
        else:
            assert a == b, f.name


def test_the_integer_keys_survive_json(tmp_path):
    """JSON has no integer keys. A silently stringified code moves the pool
    and nothing would say so."""
    original = _inputs(league_eo={100: 12.5}, cover={100: 0.4},
                       cap_cover={200: 0.1}, rival_captains={9: 100},
                       rival_names={9: "Rivals"}, dgw_probs={12: 0.8},
                       price_fall={100: 0.7})
    save_inputs(original, tmp_path)
    back = load_inputs(tmp_path)
    assert back.league_eo == {100: 12.5}
    assert back.cover == {100: 0.4}
    assert back.cap_cover == {200: 0.1}
    assert back.rival_captains == {9: 100}
    assert back.rival_names == {9: "Rivals"}
    assert back.dgw_probs == {12: 0.8}
    assert back.price_fall == {100: 0.7}


def test_a_squad_and_a_strategy_round_trip(tmp_path):
    from gaffer.data.entry import MyTeam
    from gaffer.league_mode import Strategy

    my = MyTeam(entry_id=5, bank=12, free_transfers=1, current_gw=7,
                picks=pd.DataFrame([{"code": 100, "sell": 80}]),
                chips_used=["wildcard"], chips_by_gw={3: "wildcard"})
    strat = Strategy(lam=0.4, gap=12, weeks_left=30, stance="chase",
                     rival_name="Rivals", cover_weights={9: 1.0})
    save_inputs(_inputs(my=my, strategy=strat), tmp_path)
    back = load_inputs(tmp_path)
    assert back.my.bank == 12 and back.my.chips_by_gw == {3: "wildcard"}
    pd.testing.assert_frame_equal(back.my.picks, my.picks)
    assert back.strategy == strat
    assert back.strategy.cover_weights == {9: 1.0}


def test_every_protocol_has_two_adapters():
    """The review's test for a real seam: one adapter is a hypothetical one."""
    assert isinstance(LiveModels(), Predictions)
    assert isinstance(RecordedComponents("."), Predictions)
    assert isinstance(MilpSolver(), Solver)


def test_the_milp_solver_passes_its_arguments_straight_through(monkeypatch):
    """v17g §2.5: the adapter is a pass-through, so no solve changes."""
    seen = {}
    monkeypatch.setattr("gaffer.inputs.solve_plan",
                        lambda pool, state, **kw: seen.update(
                            pool=pool, state=state, kw=kw) or "plan")
    assert MilpSolver().solve("POOL", "STATE", decay=0.85) == "plan"
    assert seen == {"pool": "POOL", "state": "STATE", "kw": {"decay": 0.85}}


def test_recorded_components_serves_the_fixture_and_claims_no_models(tmp_path):
    comp = pd.DataFrame([{"code": 100, "gw": 7, "ep": 6.0}])
    save_inputs(_inputs(comp=comp), tmp_path)
    rec = RecordedComponents(tmp_path)
    assert rec.missing() == []
    pd.testing.assert_frame_equal(
        rec.components(pred_frame=None, tg_future=None, players=None,
                       avail=None, pens=None), comp)
    assert rec.calibration() is None
