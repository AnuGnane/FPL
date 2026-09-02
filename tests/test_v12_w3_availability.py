"""§4.4: the sweep can ask "did he play", and off is off to the byte.

The rail that matters most here is the negative one. A scenario sweep is the
gate on every transfer the tool recommends, so a change to its draws is a
change to every recommendation — and with ``draw_availability`` off, not one
number may move. That is asserted by re-solving the same seed both ways and
comparing the plans, not by reading the code.

The second rail is the separation of the two streams. Availability is drawn
from ``seed + 1`` and the normal is drawn for every cell whether or not the
cell survives, so the on and off arms differ in which cells were zeroed and in
nothing else. If the availability draw consumed from the noise generator, every
comparison the §4.4 gate makes would be measuring two changes at once.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gaffer.optimize.milp import SolveInput
from gaffer.optimize.scenarios import (availability_draw, noised_pool,
                                       run_scenarios)

SOLVE_KW = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
                itb_value=0.05, hit_cost=4)


def _pool() -> pd.DataFrame:
    rows, code = [], 1
    for pos, n in [("GKP", 4), ("DEF", 9), ("MID", 10), ("FWD", 7)]:
        for i in range(n):
            rows.append({"code": code, "position": pos,
                         "team_code": (code % 6) + 1,
                         "cost": 40, "sell": 40,
                         "ep": {5: 1.0 + (code % 7) * 0.4}})
            code += 1
    return pd.DataFrame(rows)


def _state() -> SolveInput:
    return SolveInput(owned_codes=[], bank=1000, free_transfers=15, gws=[5])


def _xmins(pool) -> dict:
    return {(int(c), 5): 70.0 for c in pool["code"]}


def _p_play(pool, value=0.5) -> dict:
    return {int(c): {5: value} for c in pool["code"]}


def _signature(run) -> list:
    """Squad *and* objective per scenario.

    The objective is not decoration. On a small pinned pool two different
    noised boards routinely pick the same fifteen players, so a squad-only
    signature cannot see a shifted noise stream — and the shifted stream is
    exactly what the separation rail below exists to catch. Measured: sharing
    one generator between the two draws leaves the squads identical and moves
    every objective.
    """
    return [(sorted(p.gw_plans[0].squad), round(p.objective, 6))
            for p in run.plans]


def test_with_the_switch_off_the_sweep_is_the_pre_v12_sweep():
    """The whole feature's cost of admission."""
    pool, xm = _pool(), _xmins(_pool())
    before = run_scenarios(pool, _state(), xm, n=3, seed=7, **SOLVE_KW)
    after = run_scenarios(pool, _state(), xm, n=3, seed=7,
                          p_play=_p_play(pool), draw_availability=False,
                          **SOLVE_KW)
    assert _signature(before) == _signature(after)


def test_the_switch_on_with_no_probabilities_is_also_the_pre_v12_sweep(capsys):
    """And says so. A sweep that believes it models availability and models
    none is the failure v10's lever guard was written about."""
    pool, xm = _pool(), _xmins(_pool())
    before = run_scenarios(pool, _state(), xm, n=2, seed=7, **SOLVE_KW)
    after = run_scenarios(pool, _state(), xm, n=2, seed=7, p_play={},
                          draw_availability=True, **SOLVE_KW)
    assert _signature(before) == _signature(after)
    assert "no p_play reached the sweep" in capsys.readouterr().out


def test_the_switch_on_changes_the_boards_it_draws():
    pool, xm = _pool(), _xmins(_pool())
    off = run_scenarios(pool, _state(), xm, n=4, seed=7, **SOLVE_KW)
    on = run_scenarios(pool, _state(), xm, n=4, seed=7, p_play=_p_play(pool),
                       draw_availability=True, **SOLVE_KW)
    assert _signature(off) != _signature(on)


def test_the_noise_stream_is_untouched_by_the_availability_draw():
    """The separation. With every player certain to play, the availability
    draw consumes from its own generator and zeroes nothing, so the boards
    must be identical to the off arm — which is only true if the two draws do
    not share an rng."""
    pool, xm = _pool(), _xmins(_pool())
    off = run_scenarios(pool, _state(), xm, n=3, seed=11, **SOLVE_KW)
    certain = run_scenarios(pool, _state(), xm, n=3, seed=11,
                            p_play=_p_play(pool, 1.0),
                            draw_availability=True, **SOLVE_KW)
    assert _signature(off) == _signature(certain)


def test_a_player_who_did_not_play_scores_nothing_that_week():
    pool = _pool()
    blanked = noised_pool(pool, _xmins(pool), np.random.default_rng(1),
                          unavailable=frozenset({(3, 5)}))
    assert blanked.loc[blanked["code"] == 3, "ep"].iloc[0][5] == 0.0
    assert blanked.loc[blanked["code"] == 4, "ep"].iloc[0][5] > 0.0


def test_a_certain_player_is_never_drawn_out_and_a_doubtful_one_sometimes_is():
    pool, rng = _pool(), np.random.default_rng(3)
    assert availability_draw(pool, _p_play(pool, 1.0), rng) == frozenset()
    coin = _p_play(pool, 0.5)
    drawn = [len(availability_draw(pool, coin, rng)) for _ in range(20)]
    assert min(drawn) > 0 and max(drawn) < len(pool)


def test_a_player_with_no_probability_is_available_and_not_absent():
    """"We have no appearance probability for him" is not "he will not play"
    — noise_ep's own rule about his variance, applied to his outcome."""
    pool = _pool()
    silent = availability_draw(pool, {}, np.random.default_rng(1))
    assert silent == frozenset()


def test_a_blank_gameweek_is_never_drawn_for():
    """A week the pool does not price is not a week he was unavailable in."""
    pool = _pool()
    p_play = {int(c): {5: 0.0, 6: 0.0} for c in pool["code"]}
    drawn = availability_draw(pool, p_play, np.random.default_rng(1))
    assert all(gw == 5 for _, gw in drawn)


def test_the_sweep_is_reproducible_with_the_draw_on():
    pool, xm = _pool(), _xmins(_pool())
    kw = dict(n=3, seed=5, p_play=_p_play(pool), draw_availability=True)
    a = run_scenarios(pool, _state(), xm, **kw, **SOLVE_KW)
    b = run_scenarios(pool, _state(), xm, **kw, **SOLVE_KW)
    assert _signature(a) == _signature(b)


def test_the_config_key_defaults_off_and_reads_from_the_scenarios_section(
        tmp_path, monkeypatch):
    """OFF until its gate passes (CONVENTIONS §6, orchestrator ruling
    2026-09-02). An unmeasured arm that ships on by default is an arm the
    gate is asked to un-ship, which is not how a pre-registered rule works.
    A passing captain-support check flips this one line and this one test."""
    from gaffer.config import load_config

    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n")
    assert load_config(path).draw_availability is False
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n"
                    "[scenarios]\ndraw_availability = true\n")
    assert load_config(path).draw_availability is True


def test_the_shipped_default_leaves_the_advice_path_on_the_pre_v12_sweep():
    """The consequence of the default, asserted where a reader will look for
    it: out of the box, ``advise`` passes ``p_play=None`` and the sweep is the
    one v11 shipped. Nothing about this cycle reaches a user's advice until
    the gate says it may."""
    from gaffer.config import Config

    assert Config(entry_id=1, league_id=2).draw_availability is False


def test_the_support_driver_guards_its_lever_before_it_measures():
    """v10's lesson as a rail on the instrument itself: a driver that prints a
    delta without checking that the two arms differ is a driver that reports
    zeros as evidence.

    T8-T11 final review, Important 2: **kept** as source assertions, and
    deliberately so on both counts. ``scripts/v12_w3_support.py`` is a gate
    driver that runs against a real banked board and cannot be executed from
    a test at all, so its *shape* is the only thing a suite can hold — one
    ``run_scenarios`` call (the v10 count rail, verbatim), the guard before
    the measurement, the solve keywords taken from the state rather than
    re-invented. The two quantities its guard branches on are covered
    behaviourally above: ``availability_draw`` blanks nobody on an empty
    ``p_play`` and somebody on a doubtful one, which is exactly the
    "disconnected lever" the sentence names.
    """
    from pathlib import Path

    src = Path("scripts/v12_w3_support.py").read_text()
    assert "the lever is disconnected" in src
    assert src.index("W3_SUPPORT_LEVER") < src.index("W3_SUPPORT_DONE")
    # One board, one seed, one noise stream: the arms differ in the draw.
    assert src.count("run_scenarios(") == 1
    assert "solve_kw_from_state(state)" in src
