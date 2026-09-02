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


def test_an_uncovered_captains_blank_is_a_none_and_not_a_nan():
    """v12 W3 T8-T11 review, Important 1. A float64 column's blank is NaN, and
    NaN is a float — so it passes Jinja's ``is not none`` and formats as
    ``nan%``, and ``json.dumps`` writes it as a bare ``NaN``, which is not
    JSON. ``None`` is the only blank both surfaces already handle."""
    out = captain_table(_ep(), XI, EO, haul={1: 0.3, 2: 0.2}).set_index("code")
    assert out.loc[5, "p_haul_total"] is None


def test_the_partially_covered_table_renders_a_dash_not_nan_percent(tmp_path):
    """The frame the report actually gets, not a hand-built list of dicts: the
    NaN is created by the assignment, so a literal ``None`` in a fixture is a
    rail that cannot see this bug."""
    from gaffer.report.render import render_report

    from tests.test_report import _advice

    advice = _advice()
    advice.captain_options = captain_table(
        _ep(), XI, EO, haul={1: 0.3, 2: 0.2}).to_dict("records")
    html = render_report(advice, out_dir=tmp_path).read_text()
    assert "nan%" not in html.lower()
    assert "&mdash;" in html


def test_the_advice_artifact_round_trips_through_strict_json():
    """``advise`` writes the payload with ``json.dumps(..., default=str)``,
    which leaves a NaN as the bare token ``NaN`` — accepted by Python's own
    lenient reader and rejected by every other JSON parser, including the one
    the web app's fetch uses."""
    import json

    records = captain_table(_ep(), XI, EO,
                            haul={1: 0.3, 2: 0.2}).to_dict("records")
    text = json.dumps({"captain_options": records}, default=str)
    assert json.loads(text, parse_constant=_no_constants)


def _no_constants(token: str):
    raise AssertionError(f"non-JSON constant in the artifact: {token}")


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


def _components(gws=(3, 4)) -> pd.DataFrame:
    """A component *breakdown* frame, shaped like the one ``advise`` banks.

    One row per player-fixture, and — the whole point of this fixture —
    carrying ``ep``. ``comp``, the frame the model predicts into, does not:
    ``ep`` is what ``artifacts.components_frame`` computes *from* it via
    ``assemble_ep``. A banding step handed the wrong one of those two returns
    ``{}`` for every player in the pool.
    """
    rows = []
    for gw in gws:
        for code, ep in [(1, 9.0), (2, 8.0), (3, 7.0)]:
            rows.append({"code": code, "gw": gw, "ep": ep,
                         "p_play": 0.95, "p60": 0.9})
    # C plays twice in the first week: a double, so his two rows sum to one
    # band.
    rows.append({"code": 3, "gw": gws[0], "ep": 7.0,
                 "p_play": 0.95, "p60": 0.9})
    return pd.DataFrame(rows)


def test_the_advise_banding_step_bands_the_frame_it_is_given():
    """The step, driven rather than spelled.

    v12 W3 T8-T11 final review, Critical: the predecessor of this test
    asserted the *source text* ``bands_by_player_gw(comp)``, and ``comp`` is
    exactly the frame that has no ``ep`` column — so the rail passed by
    pinning the bug in place. Drive the step instead: given the frame that
    carries expected points, the map is non-empty and keyed on player code.
    """
    from gaffer.advise import captain_haul_by_code

    haul = captain_haul_by_code(_components(), 3)
    assert haul, "a frame with ep, p_play and p60 must produce bands"
    assert set(haul) == {1, 2, 3}
    assert all(0.0 <= v <= 1.0 for v in haul.values())


def test_the_step_keeps_the_advised_gameweek_and_drops_the_rest():
    """The horizon's other weeks are in the same frame and are not this
    week's ceiling."""
    from gaffer.advise import captain_haul_by_code

    frame = _components(gws=(3, 4))
    # GW4's rows alone, asked for GW3: the filter is a filter, and not an
    # accident of the frame only ever holding one week.
    assert captain_haul_by_code(frame[frame["gw"] == 4], 3) == {}
    assert set(captain_haul_by_code(frame, 4)) == {1, 2, 3}


def test_the_doubled_up_player_is_banded_on_both_fixtures():
    """C's two GW3 rows are 7.0 each; his band is the one over 14.0, not the
    one over 7.0 — which is the whole reason §4.6 exists."""
    from gaffer.advise import captain_haul_by_code

    both = captain_haul_by_code(_components(gws=(3,)), 3)
    single = captain_haul_by_code(
        _components(gws=(3,)).drop_duplicates(["code", "gw"]), 3)
    assert both[3] > single[3]
    assert both[1] == single[1]      # A plays once either way


def test_a_frame_with_no_expected_points_degrades_and_says_so(capsys):
    """The negative, and the half that was silent. A frame with no ``ep`` —
    ``comp`` itself, or a components file written before the column existed —
    yields no bands, and the table falls back to the attacking ceiling. The
    fallback is fine; doing it without a word is what let a wiring bug live
    through a whole cycle of green tests."""
    from gaffer.advise import captain_haul_by_code

    haul = captain_haul_by_code(_components().drop(columns=["ep"]), 3)
    assert haul == {}
    assert "no captain points bands for GW3" in capsys.readouterr().out

    out = captain_table(_ep(), XI, EO, haul=haul or None)
    assert "p_haul" in out.columns and "p_haul_total" not in out.columns


def test_advise_bands_the_components_frame_and_banks_the_same_one():
    """A rail on the call *shape*, kept alongside the behavioural tests above
    rather than instead of them: the step is only correct if it is handed the
    frame that carries ``ep``, and the one frame in ``run_advise`` that does
    is ``components_frame``'s. Built once and reused by ``save_components``,
    so the banded frame and the banked frame cannot drift apart."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    built = "components = components_frame(comp, scoring, cal, players, teams)"
    assert built in src
    assert src.count("components_frame(") == 1
    assert src.index("components = components_frame(") < \
        src.index("captain_haul_by_code(components, gw)")
    assert "save_components(components, gw)" in src
    assert "haul=haul_by_code or None" in src
