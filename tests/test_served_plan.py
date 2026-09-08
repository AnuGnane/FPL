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
             {"chip": "3xc", "gw": 8, "play_now": True, "threshold": "abc"}]
    assert chip_by_gw(table) == {6: "bboost", 8: "3xc"}
    assert thresholds(table) == {6: 2.5}
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
