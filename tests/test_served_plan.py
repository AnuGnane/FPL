"""v17f — the served plan, owned once
(specs/2026-09-08-v17f-served-plan-design.md)."""
from __future__ import annotations

import json
import math

import pandas as pd
import pytest

from gaffer.artifacts import POOL_COLS


def _pool(rows=((100, "In", "MID", 80, 78, 6.0), (200, "Out", "MID", 75, 74, 4.0))):
    out = [{"code": c, "name": n, "position": p, "team_code": 1, "cost": cost,
            "sell": sell, "owned": c == 200, "gw": g, "ep_raw": ep}
           for c, n, p, cost, sell, ep in rows for g in (5, 6, 7)]
    return pd.DataFrame(out, columns=POOL_COLS)


# --- the models ---------------------------------------------------------

def test_the_models_are_frozen_and_ignore_keys_they_do_not_know():
    from gaffer.served import ServedMove

    move = ServedMove.model_validate({"code": 1, "name": "A", "position": "MID",
                                      "ep": 5.0, "p_haul": 0.3})
    assert move.model_dump(exclude_unset=True) == {"code": 1, "name": "A",
                                                   "position": "MID", "ep": 5.0}
    with pytest.raises(Exception):
        move.price = 1.0          # frozen


def test_a_nameless_move_is_named_by_its_code():
    from gaffer.served import ServedMove

    assert ServedMove.model_validate({"code": 7}).name == "7"


def test_a_captain_that_cannot_name_a_player_is_none_and_the_plan_stands():
    from gaffer.served import ServedPlan

    plan = ServedPlan.model_validate({"gw": 5, "captain": {"name": "Salah"},
                                      "vice": "not a dict"})
    assert plan.captain is None and plan.vice is None and plan.gw == 5


def test_plan_by_gw_keyed_by_gameweek_loads_by_its_values():
    from gaffer.served import ServedPlan

    plan = ServedPlan.model_validate({"gw": 5, "plan_by_gw": {
        "5": {"gw": 5, "hits": 0}, "6": {"gw": 6, "hits": 1}}})
    assert [w.gw for w in plan.plan_by_gw] == [5, 6]


def test_a_gap_that_is_not_a_number_is_none_and_not_zero():
    from gaffer.served import ServedAlternative

    assert ServedAlternative.model_validate({"gap": "abc"}).gap is None
    assert ServedAlternative.model_validate({"gap": -0.4}).gap == -0.4


def test_a_restraint_default_invents_no_hit_price():
    """v17b §3.3: ``hit_cost`` is not invented; readers fall back to the
    config's default."""
    from gaffer.served import ServedRestraint

    assert ServedRestraint().hit_cost is None


def test_a_file_that_is_not_the_shape_advise_writes_fails_to_validate():
    from pydantic import ValidationError

    from gaffer.served import ServedPlan

    with pytest.raises(ValidationError):
        ServedPlan.model_validate({"gw": 5, "hits": "one"})
    with pytest.raises(ValidationError):
        ServedPlan.model_validate({"gw": 5, "plan_by_gw": ["not a week"]})


# --- the pool readers, moved from the router -----------------------------

def test_pool_prices_read_cost_and_sell_in_millions():
    from gaffer.served import pool_prices

    buy, sell = pool_prices(_pool())
    assert buy == {100: 8.0, 200: 7.5} and sell == {100: 7.8, 200: 7.4}


def test_a_pool_with_no_sell_column_prices_only_the_buys():
    from gaffer.served import pool_prices

    buy, sell = pool_prices(_pool().drop(columns=["sell"]))
    assert buy == {100: 8.0, 200: 7.5} and sell == {}


def test_a_nan_or_non_numeric_price_leaves_that_side_unpriced():
    from gaffer.served import pool_prices

    pool = _pool()
    pool["sell"] = pool["sell"].astype(float)
    pool.loc[pool["code"] == 200, "sell"] = float("nan")
    pool["cost"] = "cheap"
    buy, sell = pool_prices(pool)
    assert buy == {} and sell == {100: 7.8}


def test_a_pool_with_no_code_column_prices_nothing():
    from gaffer.served import pool_prices, trace_inputs

    assert pool_prices(_pool().drop(columns=["code"])) == ({}, {})
    assert trace_inputs(_pool().drop(columns=["code"])) == ({}, {}, {})


def test_trace_inputs_keep_a_nan_ep_out_rather_than_as_zero():
    from gaffer.served import trace_inputs

    pool = _pool()
    pool.loc[(pool["code"] == 100) & (pool["gw"] == 6), "ep_raw"] = float("nan")
    ep_by, positions, names = trace_inputs(pool)
    assert (100, 6) not in ep_by and ep_by[(100, 5)] == 6.0
    assert positions[100] == "MID" and names[200] == "Out"


def test_chip_and_theta_lookups_read_only_played_rows():
    from gaffer.served import chip_by_gw, thresholds

    table = [{"chip": "bboost", "gw": 6, "play_now": True, "threshold": 2.5},
             {"chip": "wildcard", "gw": None, "play_now": True, "threshold": 1.0},
             {"chip": "freehit", "gw": 7, "play_now": False, "threshold": 0.0},
             {"chip": "3xc", "gw": 8, "play_now": True, "threshold": "abc"},
             # θ = 0.0 is a real threshold — "play it in any week that is not
             # actively worse" — and must survive the read.
             {"chip": "freehit", "gw": 9, "play_now": True, "threshold": 0.0}]
    assert chip_by_gw(table) == {6: "bboost", 8: "3xc", 9: "freehit"}
    assert thresholds(table) == {6: 2.5, 9: 0.0}
    assert chip_by_gw("nonsense") == {} and thresholds(None) == {}


# --- the wire exports ---------------------------------------------------

def test_schemas_re_exports_the_served_models_and_the_generator_emits_them():
    from gaffer import served
    from gaffer.web import schemas
    from scripts.gen_types import _models

    names = {m.__name__ for m in schemas.WIRE_EXPORTS}
    assert names == {"PlanMoveTrace", "PlanWeekTrace", "ServedMove", "ServedWeek",
                     "ServedStep", "ServedRestraint", "ServedObjective",
                     "ServedAlternative", "ServedPlan"}
    assert schemas.PlanWeekTrace is served.PlanWeekTrace
    emitted = {name for name, _ in _models()}
    assert names <= emitted


# --- the passes ---------------------------------------------------------

P = {"code": 100, "name": "In", "position": "MID", "ep": 6.0}
S = {"code": 200, "name": "Out", "position": "MID", "ep": 4.0}


def _state(pool=None, bank=15, opt=None, **kw):
    from gaffer.artifacts import SolveState

    return SolveState(pool=_pool() if pool is None else pool, bank=bank,
                      opt={"hit_cost": 4, "decay": 0.5, "ft_value": 1.5,
                           "itb_value": 0.05, "decision_priors": False,
                           **(opt or {})},
                      generated_at="2026-09-01T09:00:00+00:00", deadline="",
                      owned_codes=[200], gws=[5, 6, 7], gw=5, mode="weekly",
                      free_transfers=1, lam=0.0, league_eo={}, cover=None,
                      avail_by_gw={}, **kw)


def _week(gw, buys=(), sells=(), hits=0):
    return {"gw": gw, "hits": hits, "buys": list(buys), "sells": list(sells),
            "expected_pts": 60.0}


def _plan(weeks, **kw):
    from gaffer.served import ServedPlan

    return ServedPlan.model_validate({"gw": 5, "plan_by_gw": weeks, **kw})


def test_priced_prices_buys_at_cost_and_sells_at_value_and_the_xi_at_cost():
    from gaffer.served import priced

    plan = _plan([_week(5, buys=[P], sells=[S])], buys=[P], sells=[S], xi=[P],
                 bench=[S], captain=P, vice=S)
    out = priced(plan, {100: 8.0, 200: 7.5}, {100: 7.8, 200: 7.4})
    week = out.plan_by_gw[0]
    assert (week.buys[0].price, week.sells[0].price) == (8.0, 7.4)
    assert (out.buys[0].price, out.sells[0].price) == (8.0, 7.4)
    assert (out.xi[0].price, out.bench[0].price) == (8.0, 7.5)
    assert (out.captain.price, out.vice.price) == (8.0, 7.5)
    assert plan.plan_by_gw[0].buys[0].price is None      # a value, not a mutation


def test_a_move_the_pool_cannot_price_is_none():
    from gaffer.served import priced

    out = priced(_plan([_week(5, buys=[{"code": 999, "name": "Ghost"}])]), {}, {})
    assert out.plan_by_gw[0].buys[0].price is None


def test_charged_prices_the_hits_and_lands_the_chip_on_its_week():
    from gaffer.served import charged

    out = charged(_plan([_week(5, hits=1), _week(6)]), hit_cost=4, chips={6: "bboost"})
    assert [w.hit_cost for w in out.plan_by_gw] == [4, 0]
    assert [w.chip for w in out.plan_by_gw] == [None, "bboost"]


def test_banked_runs_the_bank_forward_and_blanks_from_the_first_unpriced_move():
    from gaffer.served import banked, priced

    plan = priced(_plan([_week(5, sells=[S]), _week(6, buys=[P]),
                         _week(7, buys=[{"code": 999, "name": "Ghost"}]), _week(8)]),
                  {100: 8.0}, {200: 7.4})
    out = banked(plan, 1.5)
    assert out.bank == 1.5
    assert [w.bank for w in out.plan_by_gw] == [8.9, 0.9, None, None]


def test_banked_keeps_a_week_with_no_moves_and_a_none_start_is_never_zero():
    from gaffer.served import banked

    assert banked(_plan([_week(5)]), 1.5).plan_by_gw[0].bank == 1.5
    out = banked(_plan([_week(5)]), None)
    assert out.bank is None and out.plan_by_gw[0].bank is None


def test_banked_runs_the_objective_week_and_every_alternative_from_the_start():
    from gaffer.served import banked, priced

    plan = priced(_plan([_week(5, sells=[S])],
                        objective={"buys": [P], "sells": [], "hits": 1,
                                   "expected_pts": 60.0,
                                   "week": _week(5, buys=[P], hits=1)},
                        alternative_plans=[{"gap": 0.4, "plan_by_gw": [_week(5, buys=[P])]}]),
                  {100: 8.0}, {200: 7.4})
    out = banked(plan, 15.0)
    assert out.plan_by_gw[0].bank == 22.4
    assert out.objective.week.bank == 7.0
    assert out.alternative_plans[0].plan_by_gw[0].bank == 7.0


def test_traced_hangs_a_trace_on_the_served_weeks_and_the_objective_and_never_an_alternative():
    from gaffer.served import banked, priced, traced

    plan = banked(priced(_plan([_week(5, buys=[P], sells=[S], hits=1), _week(6)],
                               objective={"buys": [P], "sells": [S], "hits": 1,
                                          "expected_pts": 60.0,
                                          "week": _week(5, buys=[P], sells=[S], hits=1)},
                               alternative_plans=[{"gap": 0.4,
                                                   "plan_by_gw": [_week(6, buys=[P], sells=[S])]}]),
                         {100: 8.0}, {200: 7.4}), 15.0)
    out = traced(plan, state=_state(), thresholds={}, ft_lambda=None,
                 price_timing=False, price_fall={})
    assert out.plan_by_gw[0].trace is not None
    assert out.plan_by_gw[0].trace.moves[0].buy_code == 100
    assert out.plan_by_gw[0].trace.hit_cost == 4.0
    assert out.plan_by_gw[1].trace is not None          # a week that does nothing still has one
    assert out.objective.week.trace is not None
    assert out.alternative_plans[0].plan_by_gw[0].trace is None


def test_a_trace_that_throws_costs_the_trace_and_not_the_plan(monkeypatch, capsys):
    from gaffer.served import traced

    def boom(*a, **k):
        raise ValueError("nope")

    monkeypatch.setattr("gaffer.trace.trace_plan", boom)
    out = traced(_plan([_week(5, buys=[P], sells=[S])]), state=_state(),
                 thresholds={}, ft_lambda=None, price_timing=False, price_fall={})
    assert out.plan_by_gw[0].expected_pts == 60.0
    assert out.plan_by_gw[0].trace is None
    assert "trace" in out.plan_by_gw[0].model_fields_set     # written as None, not left unset
    assert "plan trace unavailable" in capsys.readouterr().out


def test_a_chip_week_is_charged_what_the_base_plan_paid_and_the_note_says_so():
    from gaffer.served import charged, traced

    plan = charged(_plan([_week(5, buys=[P], sells=[S], hits=1)]), hit_cost=4,
                   chips={5: "wildcard"})
    out = traced(plan, state=_state(), thresholds={5: 1.0}, ft_lambda=None,
                 price_timing=False, price_fall={})
    trace = out.plan_by_gw[0].trace
    assert trace.hit_cost == 4.0 and trace.theta == 1.0
    assert "a wildcard is recommended this week" in trace.note


def test_completed_is_the_one_pass_over_a_solve_state(monkeypatch):
    from gaffer.served import completed

    monkeypatch.setattr("gaffer.served.price_falls", lambda state: (True, {200: 0.8}))
    plan = _plan([_week(5, buys=[P], sells=[S], hits=1), _week(6, buys=[P], sells=[S])],
                 objective={"buys": [P], "sells": [S], "hits": 1, "expected_pts": 60.0,
                            "week": _week(5, buys=[P], sells=[S], hits=1)})
    out = completed(plan, state=_state(), chip_table=[
        {"chip": "bboost", "gw": 6, "play_now": True, "threshold": 2.0}])
    assert out.generated_at == "2026-09-01T09:00:00+00:00" and out.bank == 1.5
    week = out.plan_by_gw[0]
    assert (week.buys[0].price, week.sells[0].price, week.hit_cost) == (8.0, 7.4, 4)
    assert week.bank == 0.9 and week.trace is not None
    assert out.plan_by_gw[1].bank == 0.3
    assert out.plan_by_gw[1].chip == "bboost" and out.plan_by_gw[1].trace.theta == 2.0
    assert out.plan_by_gw[1].trace.price_charge == pytest.approx(0.8 * 0.1 * 0.05)
    assert out.objective.week.bank == 0.9 and out.objective.week.trace is not None


def test_decorated_tags_the_served_buys_and_carries_frequencies_only_where_seen():
    from gaffer.served import decorated

    plan = _plan([], buys=[P], sells=[S], xi=[P])
    out = decorated(plan, tags={100: "attack"}, frequencies={("buy", 100): 0.7})
    assert out.buys[0].tag == "attack" and out.buys[0].frequency == 0.7
    assert out.sells[0].frequency is None and "tag" not in out.sells[0].model_fields_set
    assert "tag" not in out.xi[0].model_fields_set
    dumped = out.model_dump(exclude_unset=True)
    assert "tag" not in dumped["xi"][0] and "tag" not in dumped["sells"][0]


def test_with_alternatives_types_the_rows_advise_built():
    from gaffer.served import with_alternatives

    out = with_alternatives(_plan([]), [{"gap": 0.4, "plan_by_gw": [_week(5, buys=[P])]},
                                        {"gap": None, "plan_by_gw": {"5": _week(5)}}])
    assert [a.gap for a in out.alternative_plans] == [0.4, None]
    assert out.alternative_plans[1].plan_by_gw[0].gw == 5
    assert with_alternatives(_plan([]), None).alternative_plans == []


# --- the loader ---------------------------------------------------------

def _write_state(bank=15):
    from gaffer.artifacts import save_solve_state

    save_solve_state(_state(bank=bank))


def test_the_loader_backfills_a_file_written_before_v17f_from_its_solve_state(tmp_path, monkeypatch):
    from pathlib import Path

    from gaffer.artifacts import served_plan

    monkeypatch.chdir(tmp_path)
    Path("reports").mkdir()
    _write_state()
    Path("reports/gw5-advice.json").write_text(json.dumps({
        "gw": 5, "deadline": "x", "buys": [P], "sells": [S], "hits": 1,
        "captain": P, "vice": S, "expected_pts": 60.0,
        "chip_table": [{"chip": "bboost", "gw": 6, "play_now": True}],
        "plan_by_gw": [_week(5, buys=[P], sells=[S], hits=1), _week(6)],
        "alternative_plans": [{"gap": 0.4, "plan_by_gw": [_week(6, buys=[P], sells=[S])]}]}))
    plan = served_plan(5)
    assert plan.generated_at == "2026-09-01T09:00:00+00:00" and plan.bank == 1.5
    assert plan.plan_by_gw[0].bank == 0.9 and plan.plan_by_gw[0].trace is not None
    assert plan.plan_by_gw[1].chip == "bboost"
    assert plan.alternative_plans[0].plan_by_gw[0].buys[0].price == 8.0
    assert plan.alternative_plans[0].plan_by_gw[0].trace is None
    assert plan.captain.price == 8.0


def test_the_loader_serves_a_v17f_file_as_written_without_the_solve_state(tmp_path, monkeypatch):
    from pathlib import Path

    from gaffer.artifacts import served_plan

    monkeypatch.chdir(tmp_path)
    Path("reports").mkdir()                        # no solve state on disk
    Path("reports/gw5-advice.json").write_text(json.dumps({
        "gw": 5, "generated_at": "2026-09-02T00:00:00+00:00", "bank": 2.5,
        "buys": [{**P, "price": 8.0}], "plan_by_gw": [
            {**_week(5, buys=[{**P, "price": 8.0}]), "hit_cost": 0, "chip": None,
             "bank": -5.5, "trace": None}]}))
    plan = served_plan(5)
    assert plan.bank == 2.5 and plan.plan_by_gw[0].bank == -5.5
    assert plan.plan_by_gw[0].trace is None


def test_a_missing_advice_is_the_same_sentence_load_advice_raises(tmp_path, monkeypatch):
    from gaffer.artifacts import served_plan
    from gaffer.errors import GafferError

    monkeypatch.chdir(tmp_path)
    with pytest.raises(GafferError, match="gaffer advise"):
        served_plan(9)


def test_a_file_that_will_not_validate_is_a_gaffer_error_naming_the_field(tmp_path, monkeypatch):
    from pathlib import Path

    from gaffer.artifacts import served_plan
    from gaffer.errors import GafferError

    monkeypatch.chdir(tmp_path)
    Path("reports").mkdir()
    Path("reports/gw5-advice.json").write_text(json.dumps({"gw": 5, "hits": "one"}))
    with pytest.raises(GafferError, match="hits"):
        served_plan(5)


def test_advice_gws_enumerates_ascending_and_ignores_a_stem_that_is_not_a_number(tmp_path, monkeypatch):
    from pathlib import Path

    from gaffer.artifacts import advice_gws, advice_path

    monkeypatch.chdir(tmp_path)
    assert advice_gws() == []
    Path("reports").mkdir()
    for name in ("gw7-advice.json", "gw5-advice.json", "gwX-advice.json", "gw6.json"):
        Path("reports", name).write_text("{}")
    assert advice_gws() == [5, 7]
    assert advice_path(5) == Path("reports/gw5-advice.json")
