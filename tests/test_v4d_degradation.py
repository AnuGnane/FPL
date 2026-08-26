"""The v4d degradation rail.

Four things are pinned:

1. ``tilt_ep`` at lam = 0 returns the input values unchanged, whatever the
   cover table says.
2. ``tilted_captaincy`` at lam = 0 is argmax raw EP — the v4c armband.
3. ``gaffer advise``'s printed block with no league is character-for-character
   what v4c printed. This re-runs the v4c rail after the CLI grew two
   conditional lines, which is the whole point.
4. The protected source-text orderings inside ``run_advise`` still hold, and
   nothing v4d inserted mentions the tilted pool.

If a later task legitimately changes one of these, that task's *gate* says so
and the pin here is updated deliberately — never quietly.
"""

from __future__ import annotations

import pytest

from gaffer.league_mode import (Strategy, compute_strategy, tilt_ep,
                                tilted_captaincy)


# --- rail 1: the tilt is the identity at lam = 0 ---------------------------

def test_tilt_at_zero_lambda_returns_the_same_values():
    ep_by = {(1, 5): 4.0, (2, 5): 7.25, (3, 6): 0.0}
    cover = {1: 1.0, 2: 0.35, 3: 0.0}
    out = tilt_ep(ep_by, cover, 0.0)
    assert out == ep_by
    assert all(out[key] is ep_by[key] or out[key] == ep_by[key]
               for key in ep_by)


def test_tilt_at_zero_lambda_ignores_a_nonsense_cover_table():
    ep_by = {(1, 5): 4.0}
    assert tilt_ep(ep_by, {1: 17.5}, 0.0) == ep_by
    assert tilt_ep(ep_by, {}, 0.0) == ep_by


# --- rail 2: the armband does not move at lam = 0 --------------------------

def test_captaincy_at_zero_lambda_is_the_raw_ep_argmax():
    ep_of = {1: 9.0, 2: 8.6, 3: 7.0}
    for cover in ({}, {1: 1.0}, {2: 1.0, 3: 0.5}):
        assert tilted_captaincy([3, 2, 1], ep_of, cover, 0.0) == (1, 2)


def test_a_neutral_strategy_leaves_lambda_at_exactly_zero():
    """The dial's own rail: a dead heat is 0.0, not 1e-17."""
    import pandas as pd

    rivals = pd.DataFrame({"entry": [11], "entry_name": ["Level"],
                           "total": [500]})
    s = compute_strategy(500, rivals, 20)
    assert s.lam == 0.0
    assert isinstance(s, Strategy)
    assert tilt_ep({(1, 20): 5.0}, {1: 0.9}, s.lam) == {(1, 20): 5.0}


# --- rail 3: the printed advise block --------------------------------------

def test_the_no_league_advise_output_is_still_byte_identical(tmp_path,
                                                             monkeypatch):
    """Re-run the v4c rail now that the captain line has two conditional
    fragments. With no league both are absent and the block is unchanged."""
    from tests.test_v4c_degradation import (
        test_advise_prints_exactly_the_pre_v4c_block)

    test_advise_prints_exactly_the_pre_v4c_block(tmp_path, monkeypatch)


# --- rail 4: the protected source-text seams -------------------------------

def test_the_advise_seams_still_hold_after_v4d():
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    league = src.index("fetch_rival_entries(")
    strategy = src.index("compute_strategy(")
    tilt = src.index("tilt_ep(")
    pool = src.index("pool = build_pool(")
    assert league < strategy < tilt < pool
    assert "build_pool(players, pool_ep," in src
    assert "except Exception" in src
    assert "summary_overall_points" in src
    assert "pool_ep" not in src[src.index("ep_gw1 ="):]


def test_nothing_v4d_inserted_reads_the_tilted_pool():
    """cover, cap_cover and the captaincy seam all read ep_by. A tilted
    number on a printed table would be a lie, and the pool is the only
    consumer of the tilt."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    for marker in ("cover_table(", "captain_cover(", "tilted_captaincy("):
        line_start = src.rindex("\n", 0, src.index(marker)) + 1
        line_end = src.index("\n", src.index(marker))
        assert "pool_ep" not in src[line_start:line_end]
    assert src.count("pool_ep = tilt_ep(") == 1
