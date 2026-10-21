"""Holiday F-164: ``gaffer.optimize.formation`` pinned on its own.

v18d §2 made ``XI_BOUNDS`` one table and ``formation_legal`` one predicate
for the MILP, ``backtest``, ``live_gw`` and ``review``; until now it was
reached only through those callers.
"""
from __future__ import annotations

import pytest

from gaffer.optimize.formation import XI_BOUNDS, formation_legal


def _xi(d: int, m: int, f: int, g: int = 1) -> list[str]:
    return ["GKP"] * g + ["DEF"] * d + ["MID"] * m + ["FWD"] * f


@pytest.mark.parametrize("shape", [(3, 4, 3), (5, 4, 1), (4, 5, 1)])
def test_the_common_shapes_are_legal(shape):
    assert formation_legal(_xi(*shape))


def test_two_keepers_are_illegal():
    assert not formation_legal(_xi(3, 4, 2, g=2))


def test_two_defenders_are_illegal():
    assert not formation_legal(_xi(2, 5, 3))


def test_four_forwards_are_illegal():
    assert not formation_legal(_xi(3, 3, 4))


def test_a_ten_man_list_is_illegal_even_inside_every_bound():
    assert not formation_legal(_xi(3, 4, 2))


def test_the_bounds_admit_an_eleven():
    assert sum(lo for lo, _ in XI_BOUNDS.values()) <= 11
    assert sum(hi for _, hi in XI_BOUNDS.values()) >= 11
