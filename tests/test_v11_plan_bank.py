"""The bank, across the horizon the advice run solved.

``plan_by_gw`` has never carried money — ``advise.py:966-970`` writes ``gw``,
``hits``, ``buys``, ``sells`` and ``expected_pts`` and nothing else — so the
trajectory is arithmetic done here, over the starting bank on ``SolveState``
and the two price columns ``plan.py`` already joins out of the pool.

The assertion that matters is not the addition. It is what happens when one
move has no price: ``_prices`` leaves a side unpriced whenever the pool lacks
the column or the cell is not a number, and a running total that skipped such
a move would report a bank that is wrong by exactly that player's price, with
nothing on the page to say so. A wrong number a reader trusts is worse than a
missing one he can see, so the week goes ``None`` — and so does every week
after it, because there is no point at which the sum re-synchronises.
"""

from __future__ import annotations

import pytest

from gaffer.web.routers import plan as plan_router


def _advice(weeks):
    return {"gw": 5, "deadline": "2026-09-18T17:30:00Z", "chip_table": [],
            "captain": None, "vice": None, "plan_by_gw": weeks}


def _week(gw, buys=(), sells=(), hits=0):
    return {"gw": gw, "hits": hits, "expected_pts": 60.0,
            "buys": [dict(b) for b in buys], "sells": [dict(s) for s in sells]}


@pytest.fixture()
def wired(monkeypatch):
    """A three-week plan, priced, over a bank of 1.5m (15 tenths)."""
    import pandas as pd

    from gaffer.artifacts import SolveState

    pool = pd.DataFrame({"code": [100, 200, 300],
                         "name": ["In", "Out", "Other"],
                         "cost": [80.0, 75.0, 60.0],
                         "sell": [78.0, 74.0, 59.0]})

    def install(weeks, bank=15):
        monkeypatch.setattr(plan_router, "load_advice",
                            lambda gw: _advice(weeks))
        # Every keyword ``SolveState`` requires: the dataclass has no defaults
        # before ``pool``, so a shorter construction is a TypeError rather than
        # a fixture.
        state = SolveState(gw=5, gws=[5, 6, 7],
                           deadline="2026-09-18T17:30:00Z",
                           generated_at="2026-09-01T09:00:00+00:00",
                           mode="weekly", bank=bank, free_transfers=1,
                           owned_codes=[200], lam=0.0, league_eo={},
                           avail_by_gw={}, opt={"hit_cost": 4}, pool=pool)
        monkeypatch.setattr(plan_router, "load_solve_state", lambda gw: state)
        return state
    return install


def test_the_starting_bank_is_the_solve_states_own(wired):
    """Tenths of a million on disk, millions on the wire — the conversion the
    module's own ``_price`` helper already performs for every price."""
    wired([_week(5)])
    out = plan_router.plan(5)
    assert out.bank == 1.5


def test_a_week_that_buys_and_sells_moves_the_bank_by_the_difference(wired):
    wired([_week(5, buys=[{"code": 100, "name": "In"}],
                 sells=[{"code": 200, "name": "Out"}])])
    out = plan_router.plan(5)
    # 1.5 + 7.4 (sell of 200) - 8.0 (buy of 100) = 0.9
    assert out.weeks[0].bank == pytest.approx(0.9)


def test_the_trajectory_runs_forward_across_weeks(wired):
    wired([_week(5, sells=[{"code": 200, "name": "Out"}]),
           _week(6, buys=[{"code": 100, "name": "In"}]),
           _week(7)])
    banks = [w.bank for w in plan_router.plan(5).weeks]
    assert banks == pytest.approx([8.9, 0.9, 0.9])


def test_a_week_with_no_moves_carries_the_bank_unchanged(wired):
    wired([_week(5), _week(6)])
    assert [w.bank for w in plan_router.plan(5).weeks] == [1.5, 1.5]


def test_an_unpriced_move_makes_that_week_and_every_later_week_unknown(wired):
    """The rule this whole task exists for. Code 999 is not in the pool, so
    ``_prices`` has no price for it; the alternative — skipping it — would
    report a bank that is exactly one player's price too high, confidently."""
    wired([_week(5), _week(6, buys=[{"code": 999, "name": "Ghost"}]),
           _week(7)])
    banks = [w.bank for w in plan_router.plan(5).weeks]
    assert banks[0] == 1.5
    assert banks[1] is None
    assert banks[2] is None


def test_the_starting_bank_survives_a_broken_trajectory(wired):
    """The week-level break says nothing about the week-zero fact. A reader
    who cannot be told what the plan does to his money can still be told what
    he has."""
    wired([_week(5, buys=[{"code": 999, "name": "Ghost"}])])
    out = plan_router.plan(5)
    assert out.bank == 1.5
    assert out.weeks[0].bank is None


def test_a_solve_state_with_no_usable_bank_is_None_and_not_zero(wired):
    """0.0 is "he is fully invested", which is a real and different state."""
    wired([_week(5)], bank=None)
    out = plan_router.plan(5)
    assert out.bank is None
    assert out.weeks[0].bank is None


def test_every_pre_existing_field_is_untouched(wired):
    """The degradation direction. ``Timeline.tsx`` reads eight fields off each
    week and this task may not disturb one of them."""
    wired([_week(5, buys=[{"code": 100, "name": "In", "position": "MID",
                           "ep": 6.1}], hits=1)])
    week = plan_router.plan(5).weeks[0]
    assert (week.gw, week.hits, week.hit_cost) == (5, 1, 4)
    assert week.expected_pts == 60.0
    assert week.buys[0].price == 8.0
