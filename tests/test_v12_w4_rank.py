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


def test_an_eo_above_one_is_an_armband_rather_than_a_clamp():
    """Effective ownership exceeds 1 for a heavily captained player, and
    clamping it to 1 threw the armband away: the synthetic field captained
    nobody. The draw is two Bernoullis so the mean is preserved."""
    masks = field_population(_eo(range(5), 1.8), n_managers=4000, seed=1)
    assert set(np.unique(masks)) <= {0.0, 1.0, 2.0}
    assert abs(float(masks.mean()) - 1.8) < 0.03


def test_an_eo_above_two_is_clamped_at_two_shares():
    """A triple-captain week can push a single sample past 200% (the live log's
    maximum is 214.7). Two shares is what an ordinary week can produce."""
    masks = field_population(_eo(range(5), 2.6), n_managers=100, seed=1)
    assert masks.sum() == 1000


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
    week for a reason that has nothing to do with the model being wrong.

    The band is 0.46-0.54, and it is set from what the estimator supports
    rather than from what the model intends. One population draw per call put
    ``p_green`` over 0.454-0.576 across twenty seeds and 0.427-0.585 across
    sixty — 12 of those 60 outside a 0.45-0.55 band — so the old test passed
    on the seed it was written under and would have failed on one seed in
    five. Averaging over :data:`FIELD_DRAWS` populations gives 0.475-0.530
    over the same twenty seeds and 0.471-0.538 over sixty, so 0.46-0.54 is a
    band the instrument earns.
    """
    out = simulate_field_rank(_inputs(range(15)), _eo(range(30)),
                              n=4000, seed=20260902, gw=6)
    assert 0.46 <= out["p_green"] <= 0.54


def test_the_headline_averages_over_several_field_populations():
    """Which three hundred managers were drawn is noise in its own right, and
    it was the larger term (:data:`FIELD_DRAWS`)."""
    from gaffer.league_sim import FIELD_DRAWS

    assert FIELD_DRAWS == 8
    out = simulate_field_rank(_inputs(range(11)), _eo(range(30)), n=500,
                              seed=1, gw=6)
    assert out["draws"] == FIELD_DRAWS
    one = simulate_field_rank(_inputs(range(11)), _eo(range(30)), n=500,
                              seed=1, gw=6, draws=1)
    assert one["draws"] == 1
    assert one["p_green"] != out["p_green"]


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
    """Only an *empty* intersection is an empty state — see
    :func:`test_a_pick_the_sample_never_saw_is_still_my_player`."""
    out = simulate_field_rank(_inputs([900, 901]), _eo(range(30)), n=500,
                              seed=1, gw=6)
    assert out["p_green"] is None
    assert "no player in your squad" in out["waiting_for"]


def test_a_pick_the_sample_never_saw_is_still_my_player():
    """The element axis is the union of the EO table and my squad.

    ``eo_from_picks`` omits anyone no sampled entry started, so a genuine
    differential is simply absent from the table — and filtering my picks to
    ``element in deadline_eo`` deleted him from *my* week while the field kept
    its whole one. On this fixture the deleted player is a 12-EP differential:
    the intersection-only reading scored my week without him and answered
    0.333 where the union answers 0.914.
    """
    elements = list(range(30)) + [900]

    def run(eo):
        ins = _inputs(list(range(14)) + [900], elements=elements)
        ins.ep_by_element[900] = 16.0
        return simulate_field_rank(ins, eo, n=2000, seed=4, gw=6)

    absent = run(_eo(range(30)))
    present = run({**_eo(range(30)), 900: 0.0})
    assert absent["p_green"] == present["p_green"]
    assert absent["p_green"] > 0.6
    assert absent["unsampled_picks"] == 1
    assert present["unsampled_picks"] == 0


def test_a_template_captain_lifts_the_fields_week():
    """The clamp cost the field its armband. On the live GW2 log the clamped
    ownership mass was 12.34 against a measured 13.48 — 8.5% of the field's
    week, all of it captaincy, handed to me for free."""
    flat = simulate_field_rank(_inputs(range(15)),
                               {**_eo(range(30)), 0: 1.0},
                               n=2000, seed=5, gw=6)
    armband = simulate_field_rank(_inputs(range(15)),
                                  {**_eo(range(30)), 0: 1.8},
                                  n=2000, seed=5, gw=6)
    assert armband["field_median_ep"] > flat["field_median_ep"] + 1.0


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


# --- the router's panel assembly ----------------------------------------

from types import SimpleNamespace  # noqa: E402


def _cfg(season="2026-27", sim_n=200):
    return SimpleNamespace(current_season=season, sim_n=sim_n)


def test_the_panel_reads_the_sample_banked_under_the_gameweek_before(eo_store):
    """The field sample for plan gameweek N is banked under N-1.

    ``build_inputs`` reads squads from ``max(1, plan_gw - 1)`` — picks 404
    before a deadline — and ``_cache_key`` keys the cached run on that same
    file. The panel asked for the plan gameweek's EO instead and got nothing:
    on the live log, plan gw 3 answered source ``none`` and 0 elements while
    gw 2 answered ``last-sample`` and 123. §3.3's ``deadline_eo`` is already
    the one-ahead projection, so N-1's sample *is* the number for N.
    """
    from gaffer.web.routers import league_sim as router

    append_field_eo(field_eo_rows({7: {"eo": 50.0, "se": 2.0, "n": 300}},
                                  2, "2026-27", day="2026-09-05"))
    out = router._field_rank(_cfg(), _inputs([7], elements=[7]), 3)
    assert out.eo_gw == 2
    assert out.eo_source == "last-sample"
    assert out.p_green is not None


def test_the_panel_sees_the_deadline_trend_from_the_two_weeks_before(eo_store):
    from gaffer.web.routers import league_sim as router

    append_field_eo(field_eo_rows({7: {"eo": 40.0, "se": 2.0, "n": 300}},
                                  1, "2026-27", day="2026-08-29"))
    append_field_eo(field_eo_rows({7: {"eo": 50.0, "se": 2.0, "n": 300}},
                                  2, "2026-27", day="2026-09-05"))
    out = router._field_rank(_cfg(), _inputs([7], elements=[7]), 3)
    assert out.eo_gw == 2 and out.eo_source == "deadline-trend"


def test_a_sample_banked_under_the_plan_gameweek_itself_is_not_read(eo_store):
    """Deliberately not a fallback. Trying the plan gameweek first would make
    the panel's answer depend on whether a scrape had happened *since* the
    deadline, and would silently read a post-deadline sample as a
    pre-deadline projection."""
    from gaffer.web.routers import league_sim as router

    append_field_eo(field_eo_rows({7: {"eo": 50.0, "se": 2.0, "n": 300}},
                                  3, "2026-27", day="2026-09-12"))
    out = router._field_rank(_cfg(), _inputs([7], elements=[7]), 3)
    assert out.eo_source == "none"
    assert out.eo_gw is None
    assert out.p_green is None
    assert "field-scrape" in out.waiting_for


def test_gameweek_one_reads_gameweek_one(eo_store):
    """``max(1, gw - 1)``: there is no gameweek zero to look in."""
    from gaffer.web.routers import league_sim as router

    append_field_eo(field_eo_rows({7: {"eo": 50.0, "se": 2.0, "n": 300}},
                                  1, "2026-27", day="2026-08-29"))
    out = router._field_rank(_cfg(), _inputs([7], elements=[7]), 1)
    assert out.eo_gw == 1 and out.p_green is not None


def test_the_panel_counts_picks_the_sample_never_saw(eo_store):
    from gaffer.web.routers import league_sim as router

    append_field_eo(field_eo_rows({7: {"eo": 50.0, "se": 2.0, "n": 300}},
                                  2, "2026-27", day="2026-09-05"))
    out = router._field_rank(_cfg(), _inputs([7, 8, 9], elements=[7, 8, 9]), 3)
    assert out.unsampled_picks == 2
    assert out.field_draws == 8


def test_the_rank_slope_ignores_ledger_rows_after_the_plan_gameweek(
        eo_store, monkeypatch):
    """A ledger row carries no season, so after a rollover last season's
    gameweek 30 sits in the same file as this season's gameweek 3 and reads
    as the future. Filtering to ``gw <= plan gw`` is correct within a season
    and self-limiting at the rollover."""
    from gaffer.web.routers import league_sim as router

    this_season = [{"gw": g, "my_points": 40 + 10 * g,
                    "overall_rank": 1_000_000 - 50_000 * g}
                   for g in range(1, 8)]
    last_season = [{"gw": g, "my_points": 100 - g,
                    "overall_rank": 200_000 + 1_000 * g}
                   for g in range(20, 39)]
    monkeypatch.setattr("gaffer.review.load_ledger",
                        lambda *a, **k: last_season + this_season)
    out = router._field_rank(_cfg(), _inputs([7], elements=[7]), 8)
    assert out.rank_slope_rows == 7
    assert out.rank_slope == rank_slope(this_season)["slope"]
    assert out.rank_slope != rank_slope(last_season + this_season)["slope"]


def test_a_ledger_row_with_no_gameweek_is_dropped_rather_than_crashing(
        eo_store, monkeypatch):
    from gaffer.web.routers import league_sim as router

    rows = ([{"my_points": 50, "overall_rank": 500_000}]
            + [{"gw": g, "my_points": 40 + 10 * g,
                "overall_rank": 1_000_000 - 50_000 * g} for g in range(1, 8)])
    monkeypatch.setattr("gaffer.review.load_ledger", lambda *a, **k: rows)
    assert router._field_rank(_cfg(), _inputs([7], elements=[7]),
                              8).rank_slope_rows == 7


def test_the_panel_never_takes_the_page_down(eo_store, monkeypatch):
    """"Never raises" was a docstring, not a guard: the panel is one of four
    answers on a page and a display read must not 500 the other three."""
    from gaffer.web.routers import league_sim as router

    def boom(*_a, **_k):
        raise RuntimeError("the EO log is a directory")

    monkeypatch.setattr(router, "deadline_eo_table", boom)
    out = router._field_rank(_cfg(), _inputs([7], elements=[7]), 3)
    assert out.p_green is None
    assert out.eo_source == "none" and out.eo_gw is None
    assert "the EO log is a directory" in out.waiting_for
    assert out.rank_slope is None and out.rank_waiting_for
