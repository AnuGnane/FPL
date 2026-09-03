"""v12 W5 §6.5 — the trace on /api/plan/{gw}.

The byte-identity gate lives here. The trace is outside the solver by
construction (tests/test_v12_w5_trace.py proves nothing that decides can import
it), so what is left to prove is that turning it on changed nothing else on the
payload the board already draws.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from gaffer.artifacts import POOL_COLS, SolveState
from gaffer.web.routers import plan as plan_router


def _pool():
    rows = [{"code": c, "name": n, "position": p, "team_code": 1, "cost": 80,
             "sell": 74, "owned": c == 200, "gw": g, "ep_raw": ep}
            for c, n, p, ep in ((100, "In", "MID", 6.0),
                                (200, "Out", "MID", 4.0))
            for g in (5, 6, 7)]
    return pd.DataFrame(rows, columns=POOL_COLS)


def _advice(weeks, chips=(), alts=()):
    out = {"gw": 5, "plan_by_gw": weeks, "chip_table": list(chips),
           "captain": {"code": 100, "name": "In", "position": "MID",
                       "ep": 6.0},
           "vice": {"code": 200, "name": "Out", "position": "MID",
                    "ep": 4.0}}
    if alts:
        out["alternative_plans"] = list(alts)
    return out


def _week(gw, buys=(), sells=(), hits=0):
    return {"gw": gw, "hits": hits, "buys": list(buys), "sells": list(sells),
            "expected_pts": 60.0}


@pytest.fixture()
def wired(monkeypatch):
    def install(weeks, chips=(), lam=0.0, cover=None, alts=(), opt=None):
        monkeypatch.setattr(plan_router, "load_advice",
                            lambda gw: _advice(weeks, chips, alts))
        state = SolveState(
            pool=_pool(), bank=15,
            opt={"hit_cost": 4, "decay": 0.5, "ft_value": 1.5,
                 "itb_value": 0.05, "decision_priors": False, **(opt or {})},
            generated_at="2026-09-01T09:00:00+00:00", deadline="",
            owned_codes=[200], gws=[5, 6, 7], gw=5, mode="weekly",
            free_transfers=1, lam=lam, league_eo={}, cover=cover,
            avail_by_gw={})
        monkeypatch.setattr(plan_router, "load_solve_state", lambda gw: state)
        return state
    return install


P = {"code": 100, "name": "In", "position": "MID", "ep": 6.0}
S = {"code": 200, "name": "Out", "position": "MID", "ep": 4.0}


def test_a_week_with_moves_carries_a_trace(wired):
    wired([_week(5, buys=[P], sells=[S])])
    week = plan_router.plan(5).weeks[0]
    assert week.trace is not None
    assert week.trace.moves[0].buy_code == 100
    assert week.trace.moves[0].sell_code == 200
    # 2.0 a week over weeks 5,6,7 at decay 0.5 -> 2.0 * 1.75
    assert week.trace.moves[0].ep_gain == pytest.approx(3.5)


def test_a_week_with_no_moves_carries_a_trace_with_no_moves(wired):
    """Not a null. "This week does nothing" is a fact the board can print;
    "there is no trace" is a wiring failure and they must not look alike."""
    wired([_week(5)])
    week = plan_router.plan(5).weeks[0]
    assert week.trace is not None and week.trace.moves == []


def test_the_hit_charge_on_the_trace_matches_the_weeks_hit_cost(wired):
    wired([_week(5, buys=[P], sells=[S], hits=1)])
    week = plan_router.plan(5).weeks[0]
    assert week.hit_cost == 4
    assert week.trace.hit_cost == pytest.approx(4.0)


def test_the_transfer_friction_reaches_the_trace_from_the_solve_state(wired):
    """``ft_use_penalty`` is in ``SolveState.opt`` on every run advise has
    written since v9c, and it is a charge: leaving it off the trace would
    flatter every move on the board by exactly the friction the solver paid.
    """
    wired([_week(5), _week(6, buys=[P], sells=[S])],
          opt={"ft_use_penalty": 0.2})
    weeks = plan_router.plan(5).weeks
    assert weeks[1].trace.ft_use_penalty == pytest.approx(0.2 * 0.5 * 1)


def test_the_terminal_bank_is_valued_on_the_horizons_last_week_only(wired):
    """``(itb_value / 10) * bank[T[-1]]`` — the objective's one bank term, on
    the one week it applies to. The running bank of an earlier week is not
    priced by the objective at all."""
    wired([_week(5), _week(6), _week(7)])
    weeks = plan_router.plan(5).weeks
    assert weeks[0].trace.bank_value is None
    # No moves, so the bank is still SolveState.bank: 15 tenths = 1.5m.
    assert weeks[2].trace.bank_value == pytest.approx(0.05 * 1.5)


def test_theta_reaches_the_trace_from_the_chip_table(wired):
    wired([_week(5)], chips=[{"chip": "wildcard", "gw": 5, "play_now": True,
                              "threshold": 12.5}])
    assert plan_router.plan(5).weeks[0].trace.theta == pytest.approx(12.5)


def test_a_chip_week_is_still_charged_what_the_base_plan_paid(wired):
    """``plan_by_gw`` is the base solve. ``advise`` never sets
    ``wildcard_gw``, so a week the chip table *recommends* a wildcard for was
    still solved with its transfers charged and the free-transfer recurrence
    running normally. Waiving the friction on the chip label would report a
    charge the objective did make as zero, and then run every later week's FT
    count forward from the wrong number.
    """
    wired([_week(5, buys=[P], sells=[S])],
          chips=[{"chip": "wildcard", "gw": 5, "play_now": True,
                  "threshold": 12.5}],
          opt={"ft_use_penalty": 0.2})
    week = plan_router.plan(5).weeks[0]
    assert week.trace.ft_use_penalty == pytest.approx(0.2)
    assert week.trace.ft_used == 1
    assert week.trace.ft_after == 1
    # And the reader is told which plan these terms belong to.
    assert "base plan" in week.trace.note
    # θ still comes from the chip table: the recommendation is real, it is
    # only the *pricing* that predates it.
    assert week.trace.theta == pytest.approx(12.5)


def test_a_threshold_that_is_not_a_number_is_no_threshold(wired):
    """0.0 is a real θ — "play it whenever it is not actively worse" — so a
    threshold the artifact wrote as a string must not become one."""
    wired([_week(5)], chips=[{"chip": "wildcard", "gw": 5, "play_now": True,
                              "threshold": "n/a"}])
    assert plan_router.plan(5).weeks[0].trace.theta is None


def test_a_player_the_pool_cannot_name_is_named_from_the_advice(wired):
    """The pool is the solver's candidate list and a move can name a player
    who is not on it. "300" on the board is a database key shown to a human.
    """
    gone = {"code": 300, "name": "Gone", "position": "FWD", "ep": 1.0}
    wired([_week(5, buys=[P], sells=[gone])])
    moves = plan_router.plan(5).weeks[0].trace.moves
    assert {m.sell_name for m in moves} == {"—", "Gone"}


def test_a_nan_expected_points_is_not_a_zero(wired):
    """``_float`` defaults a NaN to 0.0, which would price this swap as a
    measured tie against a player the pool has no reading for."""
    state = wired([_week(5, buys=[P], sells=[S])])
    state.pool.loc[state.pool["code"] == 100, "ep_raw"] = float("nan")
    move = plan_router.plan(5).weeks[0].trace.moves[0]
    assert move.ep_gain is None
    assert "not in the pool" in move.note


def test_the_lambda_tilt_reaches_the_trace(wired):
    wired([_week(5, buys=[P], sells=[S])], lam=0.5,
          cover={100: 1.0, 200: 0.0})
    assert plan_router.plan(5).weeks[0].trace.moves[0].lambda_tilt < 0


def test_the_price_charge_reaches_the_trace_through_w2s_own_reader(wired,
                                                                   monkeypatch):
    """Orchestrator ruling 1. The same reader the objective's term uses, so
    the board prints the charge the solver applied rather than a second
    estimate of it."""
    wired([_week(5), _week(6, buys=[P], sells=[S])])
    monkeypatch.setattr(plan_router, "_price_falls",
                        lambda state: (True, {200: 0.8}))
    trace = plan_router.plan(5).weeks[1].trace
    assert trace.price_charge == pytest.approx(0.8 * 0.1 * 0.05)


def test_price_timing_off_reports_no_charge_and_says_why(wired, monkeypatch):
    wired([_week(5), _week(6, buys=[P], sells=[S])])
    monkeypatch.setattr(plan_router, "_price_falls",
                        lambda state: (False, {}))
    trace = plan_router.plan(5).weeks[1].trace
    assert trace.price_charge is None
    assert "price_timing is off" in trace.note


def test_a_missing_price_reader_costs_the_charge_and_not_the_plan(wired,
                                                                  monkeypatch):
    """W5 may land on a tree where W2's reader moved or was renamed. The
    import failure is a printed line and a null charge, never a 500."""
    def boom(*a, **k):
        raise ImportError("no such module")

    wired([_week(5), _week(6, buys=[P], sells=[S])])
    monkeypatch.setattr(plan_router, "_price_falls", boom)
    out = plan_router.plan(5)
    assert out.weeks[1].expected_pts == 60.0
    assert out.weeks[1].trace is None


def test_the_alternatives_carry_no_trace(wired):
    """The trace is the objective's terms at the plan the solver *returned*.
    Plan B was returned by a different solve, priced against a different XI,
    and the free-transfer count the trace runs forward is the recommended
    plan's. The board says so under the strip rather than showing numbers
    that would silently be Plan A's."""
    wired([_week(5, buys=[P], sells=[S])],
          alts=[{"gap": 0.4, "plan_by_gw": [_week(5, buys=[P], sells=[S])]}])
    out = plan_router.plan(5)
    assert out.weeks[0].trace is not None
    assert out.alternatives[0].weeks[0].trace is None


def test_the_payload_is_byte_identical_with_the_trace_off(wired,
                                                          monkeypatch):
    """§6.5's gate. Everything the board already drew must be exactly what it
    was; the only difference the trace makes is the key it adds — on the
    recommended plan's weeks *and* on every alternative's, which is why both
    are stripped rather than only the first."""
    wired([_week(5, buys=[P], sells=[S], hits=1), _week(6), _week(7)],
          alts=[{"gap": 0.4, "plan_by_gw": [_week(6, buys=[P], sells=[S])]}])
    with_trace = plan_router.plan(5).model_dump()
    monkeypatch.setattr(plan_router, "TRACE", False)
    without = plan_router.plan(5).model_dump()

    def strip(payload):
        def weeks(rows):
            return [{k: v for k, v in w.items() if k != "trace"}
                    for w in rows]
        return {**payload, "weeks": weeks(payload["weeks"]),
                "alternatives": [{**a, "weeks": weeks(a["weeks"])}
                                 for a in payload["alternatives"]]}

    assert json.dumps(strip(with_trace), sort_keys=True) == json.dumps(
        strip(without), sort_keys=True)
    assert all(w["trace"] is None for w in without["weeks"])
    assert with_trace["alternatives"][0]["weeks"][0]["trace"] is None


def test_a_trace_that_throws_costs_the_trace_and_not_the_plan(wired,
                                                              monkeypatch):
    """A decoration must never be the reason a plan does not render — the
    board's own rule for the price movers (PlannerBoard.tsx:63-65)."""
    def boom(*a, **k):
        raise ValueError("nope")

    wired([_week(5, buys=[P], sells=[S])])
    monkeypatch.setattr(plan_router, "trace_plan", boom)
    out = plan_router.plan(5)
    assert out.weeks[0].expected_pts == 60.0
    assert out.weeks[0].trace is None


def test_a_pool_with_no_ep_column_does_not_stop_the_plan(wired):
    wired([_week(5, buys=[P], sells=[S])])
    state = plan_router.load_solve_state(5)
    state.pool = state.pool.drop(columns=["ep_raw"])
    out = plan_router.plan(5)
    assert out.weeks[0].buys[0].code == 100
    assert out.weeks[0].trace.moves[0].ep_gain is None
