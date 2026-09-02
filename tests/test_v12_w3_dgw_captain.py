"""§4.6: the captain's ceiling is the gameweek's, not the better fixture's.

``ep_matrix`` collapses a double gameweek by summing EP and taking the
**max** p_haul, and says why in its own docstring: it is a probability, so it
cannot be added. That is right for the number it has and wrong for the question
the captain table asks — in a double, the ceiling printed under "P(2+ returns)"
was the better of two fixtures, which is a ranking number wearing a
probability's label, and the thing a doubled-up captain is picked for is
exactly what it could not show.

The replacement is not new arithmetic: ``uncertainty.bands_by_player_gw`` has
keyed on ``(code, gw)`` with EP summed across a double since v8g. This is a
re-wiring, and the tests are mostly about what happens when it is absent.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.optimize.differentials import captain_table


def _ep() -> pd.DataFrame:
    return pd.DataFrame({
        "code": [1, 2, 3, 4, 5],
        "name": ["A", "B", "C", "D", "E"],
        "position": ["MID", "MID", "FWD", "DEF", "GKP"],
        "ep": [9.0, 8.0, 7.0, 6.0, 5.0],
        # The best-single-fixture ceiling: B looks the most explosive.
        "p_haul": [0.10, 0.40, 0.20, 0.05, 0.01]})


XI = [1, 2, 3, 4, 5]
EO = {1: 60.0, 2: 10.0, 3: 10.0, 4: 5.0, 5: 5.0}


def test_with_no_haul_map_the_table_is_the_table_it_was():
    out = captain_table(_ep(), XI, EO)
    assert list(out.columns) == ["code", "name", "position", "ep", "p_haul",
                                 "league_eo", "differential"]


def test_a_haul_map_replaces_the_column_rather_than_adding_one():
    """Two ceilings on one row is the v9c failure — two quantities under one
    heading — with the heading left ambiguous."""
    out = captain_table(_ep(), XI, EO,
                        haul={c: 0.3 for c in XI})
    assert "p_haul_total" in out.columns
    assert "p_haul" not in out.columns


def test_the_differential_rule_reads_the_new_ceiling():
    """A is heavily owned so is never a differential; between B and C the
    rule must follow the band, not the attacking p_haul that ranks B first.

    B is the whole test. On ``ep_matrix``'s attacking ``p_haul`` he is the
    most explosive name on the shortlist (0.40, comfortably above that
    column's median of 0.10) and lightly owned, so the old rule called him a
    differential. On the gameweek's own point distribution he is the *worst*
    ceiling of the five, and the rule now says so.
    """
    haul = {1: 0.30, 2: 0.05, 3: 0.50, 4: 0.20, 5: 0.10}
    out = captain_table(_ep(), XI, EO, haul=haul).set_index("code")
    assert bool(out.loc[3, "differential"]) is True
    assert bool(out.loc[2, "differential"]) is False


def test_a_map_covering_nobody_leaves_the_old_column_and_says_so(capsys):
    """A component frame with no minutes model produces no bands, and a
    captain table is not worth failing over a ceiling."""
    out = captain_table(_ep(), XI, EO, haul={999: 0.4})
    assert "p_haul" in out.columns and "p_haul_total" not in out.columns
    assert "no shortlisted captain carries a points band" in \
        capsys.readouterr().out


def test_a_partially_covered_shortlist_keeps_the_new_column_with_nulls():
    """One player with no band is one blank cell, not a fallback for the
    table: the other four still have the honest number."""
    out = captain_table(_ep(), XI, EO, haul={1: 0.3, 2: 0.2}).set_index("code")
    assert out.loc[1, "p_haul_total"] == 0.3
    assert pd.isna(out.loc[5, "p_haul_total"])


def test_a_double_gameweek_captain_is_ranked_on_both_fixtures():
    """The whole point. Two 0.25 fixtures are a much better bet than one, and
    ``max`` could not say so."""
    ep = _ep()
    # C plays twice: ep_matrix summed his EP and took the better fixture's
    # p_haul (0.20). The band over the summed EP is far higher.
    out = captain_table(ep, XI, EO,
                        haul={1: 0.10, 2: 0.12, 3: 0.55, 4: 0.02, 5: 0.01})
    top_ceiling = out.sort_values("p_haul_total", ascending=False)
    assert int(top_ceiling.iloc[0]["code"]) == 3


def test_advise_builds_the_map_for_the_advised_gameweek_only():
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    assert "bands_by_player_gw(comp)" in src
    assert "if band_gw == gw" in src
    assert "haul=haul_by_code or None" in src
