"""v16 §4 — the objective's week one on /api/plan/{gw}, traced, when it
differs from the served plan."""
from __future__ import annotations

from tests.test_v12_w5_plan_trace import P, S, _week, wired  # noqa: F401
from gaffer.web.routers import plan as plan_router


def _with_objective(wired, agrees):
    state = wired([_week(5, buys=[P], sells=[S])])
    real = plan_router.load_advice

    def advice(gw):
        out = real(gw)
        out["objective"] = {"buys": [P], "sells": [S], "hits": 1, "expected_pts": 58.0}
        out["restraint"] = {"chosen": "hits0", "bar": 0.6, "agrees": agrees,
                            "steps": [], "note": None}
        return out
    plan_router.load_advice = advice
    return state


def test_a_disagreeing_objective_is_served_with_its_own_trace(wired, monkeypatch):
    _with_objective(wired, agrees=False)
    out = plan_router.plan(5)
    assert out.objective is not None
    assert out.objective.gw == 5 and out.objective.hits == 1
    assert out.objective.hit_cost == 4
    assert out.objective.trace is not None
    assert out.objective.trace.moves[0].buy_code == 100
    assert out.objective.captain is None            # never the armband


def test_an_agreeing_objective_is_not_repeated(wired):
    _with_objective(wired, agrees=True)
    assert plan_router.plan(5).objective is None


def test_a_payload_without_the_block_serves_none(wired):
    wired([_week(5, buys=[P], sells=[S])])
    assert plan_router.plan(5).objective is None
