"""v17g §2.7, §2.8 — the frozen seam between gather and build, and the
recording that gives it a second adapter."""
from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from gaffer.inputs import (FRAMES, INT_KEYED, PAIR_KEYED, SCALARS, Inputs,
                           LiveModels, MilpSolver, Outputs, Predictions,
                           RecordedComponents, Solver, load_inputs,
                           save_inputs)


def _inputs(**over) -> Inputs:
    """A small, complete Inputs. Two players, one gameweek, no league.

    The nested ``priors``, the ``prior_advice`` dict and the non-empty
    ``win_probs`` are the three the serializer writes without touching, so
    they are populated here rather than left at the empty value that would
    let the round trip pass by saying nothing.
    """
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
        strategy=None,
        win_probs=[{"name": "Rivals", "total": 512, "p_win": 0.24}],
        priors={"lam": {"1": [0.4, 0.9]}, "theta": {"hit": 4.0}},
        dgw_probs={}, prior_advice={"gw": 6, "moves": [{"out": 200}]},
        price_timing=True, price_fall={}, difficulty={(1, 7): 0.4})
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


def test_the_recording_covers_every_field_of_inputs():
    """A field added later with a default would be dropped on save and
    silently defaulted on load, and every other test here would still pass."""
    assert set(FRAMES) | set(PAIR_KEYED) | set(INT_KEYED) | set(SCALARS) == {
        f.name for f in dataclasses.fields(Inputs)}


def test_a_numpy_scalar_is_recorded_as_a_number_not_a_string(tmp_path):
    """v17g §2.8: pandas 3 boxes to native ints here, but the fixture is read
    back under whatever pandas comes next, and ``"100"`` matches no row."""
    import numpy as np

    save_inputs(_inputs(rival_captains={np.int64(9): np.int64(100)},
                        dgw_probs={np.int64(12): np.float64(0.8)},
                        through=np.int64(6)), tmp_path)
    back = load_inputs(tmp_path)
    assert back.rival_captains == {9: 100}
    assert back.dgw_probs == {12: 0.8}
    assert back.through == 6 and isinstance(back.through, int)


def test_something_that_is_not_a_number_is_refused_rather_than_stringified(
        tmp_path):
    """The old ``default=str`` recorded any object as its repr, which reads
    back as a plausible string and is never the value that was gathered."""
    with pytest.raises(TypeError, match="not recordable"):
        save_inputs(_inputs(deadline=object()), tmp_path)


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


def test_the_pair_keyed_maps_keep_their_tuple_keys(tmp_path):
    """JSON has no tuple key at all, so each goes to a parquet of three
    columns. An empty one is a real recording and not a broken gather: the
    ticker answers with an empty map for any fixture it cannot rate."""
    original = _inputs(ep_by={(100, 7): 6.0},
                       difficulty={(1, 7): 0.4, (2, 8): 0.9})
    save_inputs(original, tmp_path)
    back = load_inputs(tmp_path)
    assert back.ep_by == {(100, 7): 6.0}
    assert back.difficulty == {(1, 7): 0.4, (2, 8): 0.9}
    save_inputs(_inputs(difficulty={}), tmp_path)
    assert load_inputs(tmp_path).difficulty == {}


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


def test_each_adapter_satisfies_its_protocol():
    """``Solver``'s second adapter, the tests' scripted one, arrives with the
    fixture that needs it; ``Predictions`` has both of its own already."""
    assert isinstance(LiveModels(), Predictions)
    assert isinstance(RecordedComponents("."), Predictions)
    assert isinstance(MilpSolver(), Solver)


@pytest.mark.parametrize("method, target, args", [
    ("solve", "solve_plan", ("POOL", "STATE")),
    ("coherent", "coherent_plan", ("POOL", "STATE", "DECISION")),
    ("scenarios", "run_scenarios", ("POOL", "STATE", "XMINS")),
    ("alternatives", "alternative_plans", ("POOL", "STATE", "INCUMBENT")),
])
def test_the_milp_solver_passes_its_arguments_straight_through(
        monkeypatch, method, target, args):
    """v17g §2.5: every method is a pass-through, so no solve changes — which
    is what the golden board's unmoved result rests on."""
    seen = {}
    monkeypatch.setattr(f"gaffer.inputs.{target}",
                        lambda *a, **kw: seen.update(a=a, kw=kw) or "plan")
    assert getattr(MilpSolver(), method)(*args, decay=0.85) == "plan"
    assert seen == {"a": args, "kw": {"decay": 0.85}}


def test_live_models_hands_the_five_arguments_to_predict_components(
        monkeypatch):
    """The five are positional at the call site and keyword-only here, so an
    order that drifted would swap two frames rather than raise."""
    seen = {}
    monkeypatch.setattr("gaffer.advise.predict_components",
                        lambda *a: seen.update(a=a) or "comp")
    assert LiveModels().components(pred_frame="P", tg_future="T",
                                   players="PL", avail="A",
                                   pens="PE") == "comp"
    assert seen["a"] == ("P", "T", "PL", "A", "PE")


@pytest.mark.parametrize("exists, expected", [(False, None), (True, "cal")])
def test_the_calibration_map_is_optional(monkeypatch, exists, expected):
    """A models directory trained before calibration existed has no such
    file, and None is the identity map, not an error."""
    monkeypatch.setattr("gaffer.models.persistence.model_exists",
                        lambda name: exists)
    monkeypatch.setattr("gaffer.models.persistence.load_model",
                        lambda name: "cal")
    assert LiveModels().calibration() == expected


def test_live_models_names_the_models_it_cannot_find(monkeypatch):
    monkeypatch.setattr("gaffer.models.persistence.model_exists",
                        lambda name: name != "saves")
    assert LiveModels().missing() == ["saves"]


def test_recorded_components_serves_the_predictions_not_the_blended_frame(
        tmp_path):
    """It stands in for ``predict_components``, which runs *before* the blend
    and the pen rescale. Serving ``Inputs.comp`` would send an already
    rescaled frame back through the rescale, which keys off a column the
    recording carries."""
    predicted = pd.DataFrame([{"code": 100, "gw": 7, "ep_pen_taker": 1.0}])
    predicted.to_parquet(tmp_path / "predicted.parquet")
    save_inputs(_inputs(comp=pd.DataFrame([{"code": 100, "gw": 7,
                                            "ep_pen_taker": 0.5}])), tmp_path)
    rec = RecordedComponents(tmp_path)
    assert rec.missing() == []
    pd.testing.assert_frame_equal(
        rec.components(pred_frame=None, tg_future=None, players=None,
                       avail=None, pens=None), predicted)
    assert rec.calibration() is None


def test_the_recorded_frame_can_be_named(tmp_path):
    """The task that records the file picks its name; this one only serves
    it."""
    frame = pd.DataFrame([{"code": 100, "gw": 7}])
    frame.to_parquet(tmp_path / "other.parquet")
    pd.testing.assert_frame_equal(
        RecordedComponents(tmp_path, filename="other.parquet").components(
            pred_frame=None, tg_future=None, players=None, avail=None,
            pens=None), frame)
