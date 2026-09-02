"""One set of EO thresholds, in one unit.

Two modules defined a constant called DIFFERENTIAL_EO. They meant the same
threshold on the same quantity — rival effective ownership — and they held 0.3
and 30.0. Nothing was wrong on either side, and nothing would have gone wrong
until somebody changed one of them.

The unit is the fraction, because that is what a share should be and because a
reader who sees 0.30 cannot read it as a count. `league_eo` on the frames stays
a percentage, so the two comparisons inside differentials.py multiply at the
point of comparison — the conversion is at the read site, which is the rule §2.2
sets.
"""

from __future__ import annotations

import pathlib
import re

import pandas as pd

from gaffer.optimize.differentials import (ALTERNATIVE_EO, DIFFERENTIAL_EO,
                                           TEMPLATE_EO, captain_table,
                                           transfer_alternatives)


def test_all_three_constants_are_fractions():
    """The import-time claim §2.2 asks for. A value of 30.0 here would clamp
    every fraction-shaped comparison in the tree to True."""
    for value in (DIFFERENTIAL_EO, ALTERNATIVE_EO, TEMPLATE_EO):
        assert 0.0 < value < 1.0


def test_the_three_hold_the_values_they_always_held():
    """The merge is a move and a rescale, not a re-tuning. Any change to these
    numbers is a decision somebody has to make on purpose."""
    assert (DIFFERENTIAL_EO, ALTERNATIVE_EO, TEMPLATE_EO) == (0.30, 0.20, 0.70)


def test_no_other_module_defines_an_EO_threshold():
    """§2.2's grep. Matches a name ending in _EO assigned a numeric literal, so
    FIELD_EO_PATH (a string) and FIELD_EO_COLS (a list) do not count and the
    parameter default `min_eo=50.0` does not either — it is a parameter, not a
    module constant, and it is named here so a later reader knows it was seen.
    """
    pattern = re.compile(r"^[A-Z_]*_EO\s*=\s*-?\d", re.MULTILINE)
    # Rooted at the repo rather than at the cwd: several suites chdir into a
    # tmp_path, and a grep over a directory that is not there passes vacuously.
    src = pathlib.Path(__file__).parents[1] / "src"
    hits = {p.relative_to(src).as_posix() for p in src.rglob("*.py")
            if pattern.search(p.read_text())}
    assert hits == {"gaffer/optimize/differentials.py"}


def _ep(league_eo_pct):
    return pd.DataFrame({
        "code": [1, 2], "name": ["A", "B"], "position": ["MID", "MID"],
        "ep": [6.0, 5.9], "p_haul": [0.3, 0.3],
    }), {1: league_eo_pct, 2: league_eo_pct}


def test_the_captain_table_still_reads_a_percentage_column():
    """The regression the rescale could have caused: `league_eo` on the frame
    is a percent, the constant is now a fraction, and a comparison that forgot
    to convert would mark every player in the league a differential."""
    ep, eo = _ep(45.0)          # 45% owned: not a differential
    out = captain_table(ep, [1, 2], eo)
    assert not out["differential"].any()

    ep, eo = _ep(5.0)           # 5% owned: is one
    out = captain_table(ep, [1, 2], eo)
    assert out["differential"].all()


def test_the_alternatives_still_read_a_percentage_column():
    ep, eo = _ep(45.0)
    assert transfer_alternatives(ep, 1, eo).empty
    ep, eo = _ep(5.0)
    assert len(transfer_alternatives(ep, 1, eo)) == 1


def test_the_league_eo_column_is_returned_in_percent_unchanged():
    """Why the conversion is at the read site and not on the column: this
    number is served, and rescaling it would move a figure on a page."""
    ep, eo = _ep(45.0)
    assert captain_table(ep, [1, 2], eo)["league_eo"].tolist() == [45.0, 45.0]
