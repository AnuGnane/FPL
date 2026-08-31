"""The mini-league Monte Carlo: its arithmetic, its seed, and its floor.

Every number this module produces is published in the UI, so CONVENTIONS.md
applies: the router serves one fixed seed and the CLI reports a spread. What
is pinned here is that the seed *works* — same seed, same answer — and that
the degenerate cases are exactly what they claim to be.
"""

from __future__ import annotations

import pytest

from gaffer.league_sim import (Entry, Pins, SimInputs, WEEKLY_SIGMA_FLOOR,
                               entry_rate, entry_sigma, multi_seed,
                               simulate_league)

EP = {7: 6.0, 8: 4.0, 9: 1.0, 10: 8.0}
SIGMA = {7: 3.0, 8: 2.0, 9: 1.0, 10: 3.0}


def _me(total=200, picks=None):
    return Entry(entry=1, name="You FC", total=total, is_me=True,
                 picks=picks or [{"element": 7, "multiplier": 2},
                                 {"element": 8, "multiplier": 1}])


def _rival(entry=2, total=200, picks=None):
    """A rival on a squad worth what mine is worth, out of players I do not
    own. The default race has to be a *race*: a rival whose squad is worth a
    point a week beside a captained six is not one a pin can move, and every
    directional assertion below would read 1.0 either side of the change."""
    return Entry(entry=entry, name=f"Rival {entry}", total=total,
                 picks=picks or [{"element": 10, "multiplier": 2}])


def _inputs(entries=None, weeks_left=10, field_rate=None):
    return SimInputs(entries=entries or [_me(), _rival()],
                     ep_by_element=EP, sigma_by_element=SIGMA,
                     weeks_left=weeks_left, field_rate=field_rate)


def test_an_entrys_rate_counts_the_captain_twice():
    assert entry_rate(_me(), EP) == pytest.approx(6.0 * 2 + 4.0)


def test_a_benched_pick_contributes_nothing():
    entry = _me(picks=[{"element": 7, "multiplier": 1},
                       {"element": 8, "multiplier": 0}])
    assert entry_rate(entry, EP) == pytest.approx(6.0)


def test_an_unknown_element_contributes_nothing_rather_than_raising():
    """A rival owning a player who is not in this week's component frame — a
    new signing, a player removed from the game — must not take the league
    card down."""
    entry = _rival(picks=[{"element": 999, "multiplier": 1}])
    assert entry_rate(entry, EP) == 0.0


def test_the_sigma_adds_in_quadrature_and_doubles_with_the_armband():
    """Variances add; a captain's *variance* is four times his own, because
    his points are doubled before they are added."""
    expected = (4 * 3.0 ** 2 + 2.0 ** 2) ** 0.5
    assert entry_sigma(_me(), SIGMA) == pytest.approx(
        max(expected, WEEKLY_SIGMA_FLOOR))


def test_an_entry_of_unknown_players_still_has_the_floor():
    """Zero variance would make a squad's season a certainty. Nothing in FPL
    is, and a league where one entry cannot vary is a league whose win
    probabilities are all 0 or 1."""
    entry = _rival(picks=[{"element": 999, "multiplier": 1}])
    assert entry_sigma(entry, SIGMA) == pytest.approx(WEEKLY_SIGMA_FLOOR)


def test_the_same_seed_gives_the_identical_answer():
    a = simulate_league(_inputs(), n=500, seed=7)
    b = simulate_league(_inputs(), n=500, seed=7)
    assert a.p_win == b.p_win
    assert a.per_rival == b.per_rival
    assert a.margin_quantiles == b.margin_quantiles


def test_a_different_seed_gives_a_different_draw():
    a = simulate_league(_inputs(), n=500, seed=7)
    b = simulate_league(_inputs(), n=500, seed=8)
    assert (a.p_win, a.exp_finish) != (b.p_win, b.exp_finish)


def test_a_dominant_leader_wins_almost_every_time():
    """The ``rival_drift=0`` sanity case: a rival with a strictly dominated
    squad and a huge deficit cannot catch up, and the number has to say so."""
    out = simulate_league(_inputs(entries=[_me(total=400), _rival(total=100)]),
                          n=2000, seed=11, rival_drift=0.0)
    assert out.p_win > 0.99
    assert out.per_rival[0]["p_beat"] > 0.99


def test_a_dominated_manager_wins_almost_never():
    out = simulate_league(_inputs(entries=[_me(total=100), _rival(total=400)]),
                          n=2000, seed=11, rival_drift=0.0)
    assert out.p_win < 0.01


def test_with_no_weeks_left_the_table_is_the_table():
    """Nothing is left to play: the standings *are* the result, and a Monte
    Carlo over them must be unanimous rather than merely confident."""
    out = simulate_league(_inputs(entries=[_me(total=300), _rival(total=200)],
                                  weeks_left=0), n=100, seed=3)
    assert out.p_win == 1.0
    assert out.exp_finish == 1.0
    assert out.margin_quantiles["p50"] == 100.0


def test_drift_zero_leaves_every_rival_on_his_own_squad():
    """The degenerate case has to be exact, not approximate: at drift 0 the
    field template is not consulted at all, so passing one changes nothing."""
    frozen = simulate_league(_inputs(field_rate=999.0), n=500, seed=5,
                             rival_drift=0.0)
    none = simulate_league(_inputs(field_rate=None), n=500, seed=5,
                           rival_drift=0.0)
    assert frozen.p_win == none.p_win


def test_drift_moves_a_weak_rival_toward_the_field_and_costs_me_odds():
    """A rival on a 1-point-a-week squad who is allowed to transfer toward a
    50-point-a-week field is a bigger threat than one who is not."""
    entries = [_me(total=300),
               _rival(total=280, picks=[{"element": 9, "multiplier": 1}])]
    frozen = simulate_league(SimInputs(entries=entries, ep_by_element=EP,
                                       sigma_by_element=SIGMA, weeks_left=20,
                                       field_rate=60.0),
                             n=2000, seed=5, rival_drift=0.0)
    drifting = simulate_league(SimInputs(entries=entries, ep_by_element=EP,
                                         sigma_by_element=SIGMA,
                                         weeks_left=20, field_rate=60.0),
                               n=2000, seed=5, rival_drift=1.0)
    assert drifting.p_win < frozen.p_win


def test_my_own_squad_never_drifts():
    """The field template is a model of what *rivals* do. Drifting my own
    squad toward it would be modelling gaffer as an average manager, which is
    the one thing the whole project disputes."""
    entries = [_me(total=300), _rival(total=300)]
    ins = SimInputs(entries=entries, ep_by_element=EP, sigma_by_element=SIGMA,
                    weeks_left=20, field_rate=0.0)
    # A field rate of zero drags every drifting entry toward nothing. If mine
    # drifted too, both would fall together and p_win would not move.
    frozen = simulate_league(ins, n=2000, seed=5, rival_drift=0.0)
    drifting = simulate_league(ins, n=2000, seed=5, rival_drift=1.0)
    assert drifting.p_win > frozen.p_win


def test_the_top_three_probability_is_never_below_the_win_probability():
    entries = [_me()] + [_rival(entry=i, total=190 + i) for i in range(2, 8)]
    out = simulate_league(_inputs(entries=entries), n=1000, seed=4)
    assert out.p_top3 >= out.p_win
    assert 1.0 <= out.exp_finish <= len(entries)


def test_a_small_league_reports_top_three_as_a_certainty():
    """Three entries: everybody is in the top three, and the headline must
    not imply otherwise."""
    out = simulate_league(_inputs(entries=[_me(), _rival(2), _rival(3)]),
                          n=200, seed=4)
    assert out.p_top3 == 1.0


def test_every_rival_gets_a_row_in_league_order():
    entries = [_me(), _rival(2, total=300), _rival(3, total=100)]
    out = simulate_league(_inputs(entries=entries), n=200, seed=4)
    assert [r["entry"] for r in out.per_rival] == [2, 3]
    assert out.per_rival[0]["p_beat"] < out.per_rival[1]["p_beat"]


def test_the_margin_fan_is_ordered_and_named():
    out = simulate_league(_inputs(), n=1000, seed=4)
    keys = ["p05", "p25", "p50", "p75", "p95"]
    assert list(out.margin_quantiles) == keys
    values = [out.margin_quantiles[k] for k in keys]
    assert values == sorted(values)


def test_the_result_records_how_it_was_produced():
    """A published probability with no seed and no n beside it is a number
    nobody can reproduce — CONVENTIONS.md §1's whole complaint."""
    out = simulate_league(_inputs(), n=250, seed=9, rival_drift=0.25)
    assert (out.n, out.seed, out.rival_drift, out.weeks_left) \
        == (250, 9, 0.25, 10)


def test_a_league_of_one_is_a_win(monkeypatch):
    out = simulate_league(_inputs(entries=[_me()]), n=50, seed=1)
    assert out.p_win == 1.0
    assert out.per_rival == []
    assert out.margin_quantiles["p50"] == 0.0


# --- pins ------------------------------------------------------------------


def test_a_blank_pin_removes_that_players_week_from_every_owner():
    """The what-if primitive: pinning element 7 to a blank costs me twelve
    points of week-one mean (he is my captain) and costs the rival nothing,
    because the rival does not own him."""
    plain = simulate_league(_inputs(), n=2000, seed=6)
    blanked = simulate_league(_inputs(), n=2000, seed=6,
                              pins=Pins(scores={7: 0.0}))
    assert blanked.p_win < plain.p_win


def test_a_haul_pin_moves_the_other_way():
    plain = simulate_league(_inputs(), n=2000, seed=6)
    hauled = simulate_league(_inputs(), n=2000, seed=6,
                             pins=Pins(scores={7: 20.0}))
    assert hauled.p_win > plain.p_win


def test_pinning_a_player_nobody_owns_changes_nothing():
    plain = simulate_league(_inputs(), n=500, seed=6)
    pinned = simulate_league(_inputs(), n=500, seed=6,
                             pins=Pins(scores={999: 20.0}))
    assert pinned.p_win == plain.p_win


def test_no_pins_at_all_is_the_unpinned_run():
    """G3's rail, asserted at the engine rather than only at the router."""
    assert simulate_league(_inputs(), n=500, seed=6, pins=Pins()) \
        == simulate_league(_inputs(), n=500, seed=6)


def test_a_captain_override_re_points_my_armband_for_the_week():
    """Element 8 captained instead of 7 costs me (6 - 4) points of week-one
    mean, so the odds fall."""
    plain = simulate_league(_inputs(), n=2000, seed=6)
    swapped = simulate_league(_inputs(), n=2000, seed=6,
                              pins=Pins(captain_override=8))
    assert swapped.p_win < plain.p_win


def test_overriding_to_the_incumbent_captain_changes_nothing():
    assert simulate_league(_inputs(), n=500, seed=6,
                           pins=Pins(captain_override=7)) \
        == simulate_league(_inputs(), n=500, seed=6)


def test_a_captain_override_on_a_player_i_do_not_own_is_ignored():
    """The panel offers my own XI, but a stale tab could send anything, and a
    router that armbanded a player I do not own would be answering a
    different question than the one on screen."""
    assert simulate_league(_inputs(), n=500, seed=6,
                           pins=Pins(captain_override=999)) \
        == simulate_league(_inputs(), n=500, seed=6)


def test_a_rival_captain_blank_helps_me():
    rival = _rival(picks=[{"element": 9, "multiplier": 2}])
    ins = _inputs(entries=[_me(total=250), rival])
    plain = simulate_league(ins, n=2000, seed=6)
    blanked = simulate_league(ins, n=2000, seed=6,
                              pins=Pins(rival_captain_blanks=2))
    assert blanked.p_win >= plain.p_win


def test_pins_only_touch_the_first_week():
    """A pin is an event in the gameweek being played, not a season-long
    change of ability. With one week left it is the whole run; with twenty it
    is a twentieth of it, and the effect has to shrink accordingly."""
    short = _inputs(weeks_left=1)
    long = _inputs(weeks_left=20)
    d_short = (simulate_league(short, n=3000, seed=6).p_win
               - simulate_league(short, n=3000, seed=6,
                                 pins=Pins(scores={7: 0.0})).p_win)
    d_long = (simulate_league(long, n=3000, seed=6).p_win
              - simulate_league(long, n=3000, seed=6,
                                pins=Pins(scores={7: 0.0})).p_win)
    assert d_short > d_long


def test_pins_with_no_weeks_left_are_inert():
    out = simulate_league(_inputs(weeks_left=0), n=100, seed=6,
                          pins=Pins(scores={7: 0.0}))
    assert out.p_win == 1.0


# --- multi-seed ------------------------------------------------------------


def test_the_multi_seed_report_carries_a_mean_and_a_spread():
    """CONVENTIONS.md §1: a published claim reads mean +/- spread, never one
    draw. The CLI prints this and the spec's G2 records it."""
    out = multi_seed(_inputs(), seeds=[1, 2, 3], n=400)
    assert out["seeds"] == [1, 2, 3]
    assert len(out["p_win"]) == 3
    assert out["p_win_mean"] == pytest.approx(sum(out["p_win"]) / 3)
    assert out["p_win_spread"] == pytest.approx(max(out["p_win"])
                                                - min(out["p_win"]))


def test_a_single_seed_reports_a_spread_of_zero_rather_than_hiding_it():
    out = multi_seed(_inputs(), seeds=[1], n=100)
    assert out["p_win_spread"] == 0.0


# --- the printed report ----------------------------------------------------

from gaffer.league_sim import format_multi_seed  # noqa: E402


def test_the_report_names_every_seed_and_the_spread():
    text = format_multi_seed(multi_seed(_inputs(), seeds=[1, 2, 3], n=200),
                             league_id=5)
    assert "league 5" in text
    assert "seed 1" in text and "seed 3" in text
    assert "spread" in text


def test_the_report_says_out_loud_that_a_spread_is_not_a_verdict():
    """A number printed without its caveat is a number that ends up in a
    commit message as a finding. CONVENTIONS.md §5."""
    text = format_multi_seed(multi_seed(_inputs(), seeds=[1, 2], n=100),
                             league_id=5)
    assert "instrument" in text.lower()
