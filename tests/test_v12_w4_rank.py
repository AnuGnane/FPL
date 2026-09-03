"""v12 W4 §5.3: the synthetic field and what it can honestly report."""

from __future__ import annotations

import numpy as np

from gaffer.league_sim import (Entry, FIELD_POP_N, SimInputs, field_population,
                               simulate_field_rank)


def _eo(elements, value=0.5) -> dict[int, float]:
    return {int(e): float(value) for e in elements}


def test_the_population_is_one_row_per_manager_per_element():
    masks = field_population(_eo(range(30)), n_managers=50, seed=1)
    assert masks.shape == (50, 30)
    assert set(np.unique(masks)) <= {0.0, 1.0}


def test_an_eo_of_one_is_owned_by_everybody():
    masks = field_population(_eo(range(10), 1.0), n_managers=20, seed=1)
    assert masks.sum() == 200


def test_an_eo_of_zero_is_owned_by_nobody():
    masks = field_population(_eo(range(10), 0.0), n_managers=20, seed=1)
    assert masks.sum() == 0


def test_an_eo_above_one_is_clamped_rather_than_raising():
    """Effective ownership exceeds 1 for a heavily captained player."""
    masks = field_population(_eo(range(5), 1.7), n_managers=10, seed=1)
    assert masks.sum() == 50


def test_the_population_is_deterministic_per_seed():
    a = field_population(_eo(range(40)), n_managers=30, seed=7)
    b = field_population(_eo(range(40)), n_managers=30, seed=7)
    c = field_population(_eo(range(40)), n_managers=30, seed=8)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_an_empty_eo_table_is_an_empty_population_not_a_crash():
    assert field_population({}, n_managers=50, seed=1).shape == (50, 0)


def test_the_default_population_matches_the_scrapes_sample_size():
    assert FIELD_POP_N == 300


# --- the headline --------------------------------------------------------

def _inputs(picks_elements, ep=4.0, sigma=3.0, elements=range(30)):
    """A squad of ``picks_elements``, every one of them scoring.

    The picks carry **no** ``position`` key, which is deliberate and is what
    makes the exchangeability test below mean what it says.
    :func:`gaffer.league_sim.effective_picks` normalises a snapshot that has
    ``position`` down to its eleven starters; a synthetic field manager drawn
    from EO has no bench at all — he owns whatever the Bernoulli draw gave him
    — so comparing an eleven-man XI against a fifteen-holding field manager
    would be comparing two different-sized portfolios and would answer 0, not
    a half. Dropping ``position`` takes ``effective_picks``' documented
    no-position branch, which returns every pick at its stored multiplier of
    one, so a fifteen-element squad is fifteen holdings and is exchangeable
    with the field's typical manager.
    """
    picks = [{"element": int(e), "multiplier": 1,
              "is_captain": False, "is_vice_captain": False}
             for e in picks_elements]
    return SimInputs(
        entries=[Entry(entry=1, name="me", total=0, picks=picks, is_me=True)],
        ep_by_element={int(e): ep for e in elements},
        sigma_by_element={int(e): sigma for e in elements},
        weeks_left=10)


def test_a_squad_exchangeable_with_the_field_is_a_coin_flip():
    """Spec §5.3's sanity test. Thirty identical players at eo 0.5; the
    field's typical manager holds fifteen of them and so do I, so my week and
    his are the same random variable and P(green) must be a half.

    Fifteen, not eleven: at eo 0.5 over thirty elements a synthetic manager's
    expected holding is exactly fifteen, and an eleven-man XI against him is a
    smaller portfolio rather than an exchangeable one — it loses nearly every
    week for a reason that has nothing to do with the model being wrong. The
    band 0.45-0.55 is pre-registered here rather than fitted after the run.
    """
    out = simulate_field_rank(_inputs(range(15)), _eo(range(30)),
                              n=4000, seed=20260902, gw=6)
    assert 0.45 <= out["p_green"] <= 0.55


def test_owning_only_players_nobody_else_owns_still_answers():
    out = simulate_field_rank(_inputs(range(11)),
                              {int(e): 0.0 for e in range(30)},
                              n=1000, seed=1, gw=6)
    # Nobody in the field owns anything, so every rival scores zero and I do
    # not: a differential squad against an empty field wins every week.
    assert out["p_green"] == 1.0


def test_a_better_squad_is_greener():
    strong = _inputs(range(11))
    strong.ep_by_element = {int(e): (9.0 if e < 11 else 4.0)
                            for e in range(30)}
    out = simulate_field_rank(strong, _eo(range(30)), n=2000, seed=3, gw=6)
    assert out["p_green"] > 0.9


def test_the_run_is_deterministic_per_seed():
    a = simulate_field_rank(_inputs(range(11)), _eo(range(30)), n=500,
                            seed=11, gw=6)
    b = simulate_field_rank(_inputs(range(11)), _eo(range(30)), n=500,
                            seed=11, gw=6)
    assert a == b


def test_no_eo_table_is_an_empty_state_and_not_a_probability():
    out = simulate_field_rank(_inputs(range(11)), {}, n=500, seed=1, gw=6)
    assert out["p_green"] is None
    assert "field-scrape" in out["waiting_for"]


def test_a_squad_of_players_the_frame_does_not_carry_is_an_empty_state():
    out = simulate_field_rank(_inputs([900, 901]), _eo(range(30)), n=500,
                              seed=1, gw=6)
    assert out["p_green"] is None
    assert "no player in your squad" in out["waiting_for"]


def test_no_entry_flagged_as_mine_is_an_empty_state():
    ins = _inputs(range(11))
    ins.entries[0].is_me = False
    out = simulate_field_rank(ins, _eo(range(30)), n=500, seed=1, gw=6)
    assert out["p_green"] is None


def test_p_top10k_is_always_none_and_says_what_it_waits_for():
    """No top-10k weekly score series exists anywhere in this tree (plan A4).
    An honest null beats a number nobody can source."""
    out = simulate_field_rank(_inputs(range(11)), _eo(range(30)), n=500,
                              seed=1, gw=6)
    assert out["p_top10k"] is None
    assert "top-10k weekly score" in out["top10k_waiting_for"]


def test_the_payload_carries_its_provenance():
    out = simulate_field_rank(_inputs(range(11)), _eo(range(30)), n=500,
                              seed=1, gw=6)
    assert out["n"] == 500 and out["seed"] == 1 and out["gw"] == 6
    assert out["managers"] == FIELD_POP_N


# --- Task 13: the rank slope --------------------------------------------

from gaffer.league_sim import RANK_SLOPE_MIN_ROWS, rank_slope  # noqa: E402


def test_five_rows_are_the_bar():
    assert RANK_SLOPE_MIN_ROWS == 5


def test_too_few_graded_gameweeks_is_a_named_empty_state():
    out = rank_slope([{"gw": 1, "my_points": 60, "overall_rank": 900000},
                      {"gw": 2, "my_points": 70, "overall_rank": 700000}])
    assert out["slope"] is None
    assert out["rows"] == 2
    assert "2 of 5 graded gameweeks" in out["waiting_for"]


def test_an_empty_ledger_is_a_named_empty_state():
    out = rank_slope([])
    assert out["slope"] is None
    assert "0 of 5 graded gameweeks" in out["waiting_for"]


def test_rows_missing_either_half_do_not_count():
    rows = [{"gw": g, "my_points": 60, "overall_rank": None}
            for g in range(1, 9)]
    assert rank_slope(rows)["rows"] == 0


def test_enough_rows_give_a_negative_slope_because_scoring_more_ranks_you_better():
    rows = [{"gw": g, "my_points": 40 + 10 * g,
             "overall_rank": 1_000_000 - 50_000 * g} for g in range(1, 7)]
    out = rank_slope(rows)
    assert out["slope"] is not None
    assert out["slope"] < 0
    assert out["waiting_for"] is None
    assert out["rows"] == 6


def test_a_ledger_with_no_variation_in_points_is_an_empty_state():
    """A slope through a vertical line is not a slope."""
    rows = [{"gw": g, "my_points": 60, "overall_rank": 900000 - g}
            for g in range(1, 8)]
    out = rank_slope(rows)
    assert out["slope"] is None
    assert "no variation" in out["waiting_for"]


# --- Task 14: the payload ------------------------------------------------

import pytest  # noqa: E402

from gaffer.data import store  # noqa: E402
from gaffer.data.field import append_field_eo, field_eo_rows  # noqa: E402
from gaffer.web.schemas import FieldRank, LeagueSimData  # noqa: E402


def test_the_schema_carries_nullable_headlines_and_their_reasons():
    fields = FieldRank.model_fields
    for name in ("p_green", "p_top10k", "rank_slope"):
        assert fields[name].is_required() is False
    payload = FieldRank(gw=6, n=2000, seed=1, managers=300,
                        eo_source="last-sample")
    assert payload.p_green is None
    assert payload.p_top10k is None


def test_league_sim_data_gained_one_optional_field():
    assert "field" in LeagueSimData.model_fields
    assert LeagueSimData.model_fields["field"].is_required() is False


def test_the_field_panel_added_no_route(tmp_path, monkeypatch):
    """By absence, not by total. v11 owns the one absolute route count and
    v12 W1's rail asserts it stays the only one; what W4 has to say is that it
    served its panel on the endpoint that already existed."""
    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    paths = create_app().openapi()["paths"]
    assert "/api/league/sim" in paths
    assert not [p for p in paths if p.startswith("/api/field")]


def test_the_router_helper_prefers_the_trend_and_says_so(monkeypatch):
    from gaffer.web.routers import league_sim as router

    monkeypatch.setattr(router, "_trend_eo",
                        lambda *_a, **_k: ({7: 0.6}, "deadline-trend"))
    table, source = router.deadline_eo_table("2026-27", 6)
    assert table == {7: 0.6} and source == "deadline-trend"


def test_the_router_helper_falls_back_to_the_last_sample(monkeypatch):
    """The log speaks percent and the simulation speaks fractions, so the
    fallback divides: ``eo`` 40.0 in the log is four managers in ten."""
    from gaffer.web.routers import league_sim as router

    monkeypatch.setattr(router, "_trend_eo", lambda *_a, **_k: ({}, ""))
    monkeypatch.setattr(router, "latest_field_eo",
                        lambda gw=None, *, season=None: {
                            9: {"eo": 40.0, "se": 0.0, "n": 300, "gw": 6}})
    table, source = router.deadline_eo_table("2026-27", 6)
    assert table == {9: 0.4} and source == "last-sample"


def test_the_router_helper_on_a_cold_clone_is_empty_and_named(monkeypatch):
    from gaffer.web.routers import league_sim as router

    monkeypatch.setattr(router, "_trend_eo", lambda *_a, **_k: ({}, ""))
    monkeypatch.setattr(router, "latest_field_eo",
                        lambda gw=None, *, season=None: {})
    assert router.deadline_eo_table("2026-27", 6) == ({}, "none")


# --- and the same three sources over a real banked log, unmonkeypatched ---

@pytest.fixture()
def eo_store(tmp_path, monkeypatch):
    """A field EO log in a temporary store, and nothing else."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    return tmp_path


def test_two_banked_gameweeks_read_as_the_deadline_trend(eo_store):
    """Not monkeypatched: the trend reader really runs, over a log with two
    gameweeks in it, which is the only state in which §3.3 extrapolates."""
    from gaffer.web.routers import league_sim as router

    append_field_eo(field_eo_rows({7: {"eo": 40.0, "se": 2.0, "n": 300}},
                                  5, "2026-27", day="2026-09-12"))
    append_field_eo(field_eo_rows({7: {"eo": 50.0, "se": 2.0, "n": 300}},
                                  6, "2026-27", day="2026-09-19"))
    table, source = router.deadline_eo_table("2026-27", 6)
    assert source == "deadline-trend"
    # 50 last, +10 over one gameweek, so 60 projected — and the router hands
    # the simulation a fraction, never the log's percent.
    assert table == {7: 0.6}


def test_one_banked_gameweek_reads_as_the_last_sample(eo_store):
    """The Saturday state: one sample banked, no drift to project, so §3.3
    reports ``trend_available=False`` and the router says ``last-sample``
    rather than passing an unextrapolated number off as a trend."""
    from gaffer.web.routers import league_sim as router

    append_field_eo(field_eo_rows({7: {"eo": 50.0, "se": 2.0, "n": 300}},
                                  6, "2026-27", day="2026-09-19"))
    table, source = router.deadline_eo_table("2026-27", 6)
    assert source == "last-sample"
    assert table == {7: 0.5}


def test_a_log_that_was_never_written_reads_as_none(eo_store):
    from gaffer.web.routers import league_sim as router

    assert router.deadline_eo_table("2026-27", 6) == ({}, "none")
