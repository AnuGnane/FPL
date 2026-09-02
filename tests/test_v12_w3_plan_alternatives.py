"""§4.3 on the wire: the alternatives ride the artifact and the plan endpoint.

No route is added and ``plan_by_gw`` does not change shape — v11's bank
trajectory reads it week by week and would blank permanently on a key it could
not parse. So the alternatives are a sibling key carrying weeks in the same
shape, and the router builds them through the same loop, which is what keeps
"Plan B's bank" and "Plan A's bank" the same arithmetic rather than two.

Every degradation the timeline already survives, an alternative survives too:
a missing key, a key that is not a list, a week that is not a dict, a gap that
is not a number. A malformed alternative costs the reader a tab, never the
board.
"""

from __future__ import annotations

import pytest

from gaffer.web.routers import plan as plan_router


def _week(gw, buys=(), sells=(), hits=0):
    return {"gw": gw, "hits": hits, "expected_pts": 60.0,
            "buys": [dict(b) for b in buys], "sells": [dict(s) for s in sells]}


def _advice(weeks, alternatives=None):
    out = {"gw": 5, "deadline": "2026-09-18T17:30:00Z", "chip_table": [],
           "captain": None, "vice": None, "plan_by_gw": weeks}
    if alternatives is not None:
        out["alternative_plans"] = alternatives
    return out


@pytest.fixture()
def wired(monkeypatch):
    import pandas as pd

    from gaffer.artifacts import SolveState

    pool = pd.DataFrame({"code": [100, 200, 300],
                         "name": ["In", "Out", "Other"],
                         "cost": [80.0, 75.0, 60.0],
                         "sell": [78.0, 74.0, 59.0]})

    def install(advice, bank=15):
        monkeypatch.setattr(plan_router, "load_advice", lambda gw: advice)
        state = SolveState(pool=pool, bank=bank, opt={"hit_cost": 4},
                           generated_at="2026-09-01T09:00:00+00:00",
                           owned_codes=[200], gws=[5, 6, 7], gw=5,
                           deadline="", mode="weekly", free_transfers=1,
                           lam=0.0, league_eo={}, avail_by_gw={})
        monkeypatch.setattr(plan_router, "load_solve_state", lambda gw: state)
    return install


def test_an_artifact_with_no_alternatives_serves_an_empty_list(wired):
    """Every payload on disk today. The board draws one tab and no strip."""
    wired(_advice([_week(5)]))
    assert plan_router.plan(5).alternatives == []


def test_each_alternative_is_labelled_and_carries_its_gap(wired):
    wired(_advice([_week(5)], [
        {"gap": 0.4, "plan_by_gw": [_week(5, buys=[{"code": 100,
                                                    "name": "In"}])]},
        {"gap": 1.8, "plan_by_gw": [_week(5)]}]))
    alts = plan_router.plan(5).alternatives
    assert [a.label for a in alts] == ["Plan B", "Plan C"]
    assert [a.gap for a in alts] == [0.4, 1.8]


def test_an_alternatives_weeks_are_priced_by_the_same_loop(wired):
    """The board prints Plan B's bank beside Plan A's; two implementations of
    the running total would disagree within a week."""
    wired(_advice([_week(5)], [
        {"gap": 0.4, "plan_by_gw": [
            _week(5, buys=[{"code": 100, "name": "In"}],
                  sells=[{"code": 200, "name": "Out"}])]}]))
    week = plan_router.plan(5).alternatives[0].weeks[0]
    assert week.buys[0].price == 8.0
    assert week.bank == pytest.approx(0.9)      # 1.5 + 7.4 - 8.0


def test_an_unpriced_move_blanks_an_alternatives_bank_too(wired):
    wired(_advice([_week(5)], [
        {"gap": 0.4, "plan_by_gw": [
            _week(5, buys=[{"code": 999, "name": "Ghost"}]), _week(6)]}]))
    banks = [w.bank for w in plan_router.plan(5).alternatives[0].weeks]
    assert banks == [None, None]


def test_an_alternative_carries_no_captain_even_on_the_head_week(wired):
    """The armband belongs to the plan that was recommended. Printing the
    recommendation's captain on an alternative that never chose him would be
    the board's most confident lie."""
    wired(_advice([_week(5)], [{"gap": 0.4, "plan_by_gw": [_week(5)]}]))
    out = plan_router.plan(5)
    assert out.alternatives[0].weeks[0].captain is None


def test_a_negative_gap_survives_to_the_wire(wired):
    """Plan A is the coherent plan; an alternative can be ahead of it."""
    wired(_advice([_week(5)], [{"gap": -1.2, "plan_by_gw": [_week(5)]}]))
    assert plan_router.plan(5).alternatives[0].gap == -1.2


def test_a_gap_that_is_not_a_number_is_None_and_not_zero(wired):
    """0.0 is "exactly level", which is a real and different claim."""
    wired(_advice([_week(5)], [{"gap": "eh", "plan_by_gw": [_week(5)]}]))
    assert plan_router.plan(5).alternatives[0].gap is None


@pytest.mark.parametrize("payload", ["nonsense", {"a": 1}, 7, None])
def test_a_malformed_alternatives_key_costs_a_tab_and_not_the_board(wired,
                                                                    payload):
    wired(_advice([_week(5)], payload))
    out = plan_router.plan(5)
    assert out.alternatives == []
    assert len(out.weeks) == 1


def test_an_alternative_that_is_not_a_dict_is_dropped_and_the_rest_stand(
        wired):
    wired(_advice([_week(5)], ["nonsense",
                               {"gap": 1.0, "plan_by_gw": [_week(5)]}]))
    alts = plan_router.plan(5).alternatives
    assert [a.label for a in alts] == ["Plan B"]
