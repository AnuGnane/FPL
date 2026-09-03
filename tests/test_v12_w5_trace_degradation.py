"""v12 W5 §6.5 — what the trace does when its inputs are not there.

The trace reads a solve state written by whatever build last ran ``advise``,
joined to an advice payload written by the same run. Every one of these cases
is a real artifact this router has to draw *something* for: a decoration must
never be the reason a plan does not render, and "unknown" must never be
printed as a zero.

Same fixtures as ``tests/test_v12_w5_trace.py``, deliberately: the two files
disagree about behaviour, not about the pool.
"""
from __future__ import annotations

import pytest

from gaffer.trace import trace_plan

from tests.test_v12_w5_trace import EP, GWS, NAMES, POS, run, week


def test_an_empty_plan_traces_to_an_empty_list():
    """Not one blank week. A plan with no weeks in it is what a solve that
    found no horizon writes, and the board already has an empty state for it.
    """
    assert run([]) == []


def test_a_week_with_no_keys_at_all_is_a_no_move_week_and_not_a_crash():
    """``plan_by_gw`` written by an older build carries fewer keys. A week
    that does nothing is a fact the board can print; a KeyError is not."""
    out = run([{"gw": 5}])
    assert out[0].moves == []
    # 0.0, not None: nothing was moved, so nothing is unknown.
    assert out[0].ep_gain == pytest.approx(0.0)
    assert out[0].hit_cost == pytest.approx(0.0)
    assert out[0].ft_use_penalty == pytest.approx(0.0)


def test_a_pool_with_no_positions_pairs_nothing_and_says_so():
    """Two unknown positions are not a position match. ``None == None`` would
    pair a keeper with a striker on a pool that lost its position column, and
    a guessed pair prices a swap that was never made."""
    out = run([week(5, buys=[100, 300], sells=[200, 400])], positions={})
    assert [m.ep_gain for m in out[0].moves] == [None] * 4
    assert all("of the same position to pair this move with" in m.note
               for m in out[0].moves)
    assert out[0].ep_gain is None


def test_an_empty_pool_prices_nothing_and_names_the_reason():
    out = run([week(5, buys=[100], sells=[200])], ep_by={})
    assert out[0].moves[0].ep_gain is None
    assert "not in the pool" in out[0].moves[0].note
    assert out[0].ep_gain is None


def test_an_empty_horizon_prices_nothing_and_names_the_empty_horizon():
    """``SolveState.gws`` missing or empty: every week is outside the solved
    horizon, and the week says which horizon it was outside of."""
    out = run([week(5, buys=[100], sells=[200], hits=1)], gws=[])
    assert out[0].moves[0].ep_gain is None
    assert "outside the solved horizon" in out[0].moves[0].note
    assert "not in the solved horizon []" in out[0].note
    # Undecayed rather than dropped: the hit was still taken.
    assert out[0].hit_cost == pytest.approx(4.0)
    assert out[0].bank_value is None


def test_a_week_outside_the_horizon_still_traces_the_rest_of_the_plan():
    """One bad week costs its own numbers and not its neighbours'."""
    out = trace_plan([week(5, buys=[100], sells=[200]), week(99)],
                     gws=GWS, ep_by=EP, positions=POS, names=NAMES,
                     decay=0.5, hit_cost=4, ft_value=1.5, itb_value=0.05,
                     free_transfers=1)
    assert out[0].ep_gain == pytest.approx(3.5)
    assert out[1].ep_gain == pytest.approx(0.0)
    assert "GW99 is not in the solved horizon" in out[1].note
