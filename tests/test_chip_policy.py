import pytest

from gaffer.optimize.chip_policy import (FIRST_HALF_LAST_GW, chip_windows,
                                         flat_thresholds, stopping_thresholds)


def test_theta_at_the_last_week_of_the_window_is_zero():
    """Nothing beats nothing: at expiry, any positive surplus plays."""
    th = stopping_thresholds({t: [1.0, 5.0] for t in range(5, 20)},
                             last_gw=19)
    assert th[19] == 0.0


def test_theta_declines_monotonically_towards_expiry():
    """More weeks left is more chances at a big one, always."""
    th = stopping_thresholds({t: [0.0, 4.0, 12.0] for t in range(5, 20)},
                             last_gw=19)
    vals = [th[t] for t in range(5, 20)]
    assert vals == sorted(vals, reverse=True), vals


def test_theta_is_at_least_the_mean_of_the_next_weeks_surplus():
    """E[max(S, theta)] >= E[S]: waiting can never be worth less than one
    more draw."""
    samples = [0.0, 4.0, 8.0]
    th = stopping_thresholds({t: samples for t in range(5, 20)}, last_gw=19)
    assert th[18] >= sum(samples) / len(samples) - 1e-12


def test_theta_at_the_second_to_last_week_is_the_next_weeks_mean():
    """Hand-checkable: theta_19 = 0, so theta_18 = E[max(S_19, 0)]."""
    th = stopping_thresholds({19: [-2.0, 2.0, 6.0]}, last_gw=19,
                             first_gw=18)
    assert abs(th[18] - (0.0 + 2.0 + 6.0) / 3) < 1e-12


def test_a_fatter_tail_raises_every_threshold():
    """A chance of a huge double gameweek is exactly what makes waiting
    worth it."""
    lean = stopping_thresholds({t: [2.0, 3.0] for t in range(5, 20)},
                               last_gw=19)
    fat = stopping_thresholds({t: [2.0, 30.0] for t in range(5, 20)},
                              last_gw=19)
    for t in range(5, 19):
        assert fat[t] > lean[t]


def test_a_week_with_no_samples_contributes_nothing_but_does_not_break():
    """A gap in the calibration must not silently zero the whole tail."""
    dist = {t: [4.0] for t in range(5, 20)}
    del dist[12]
    th = stopping_thresholds(dist, last_gw=19)
    assert th[11] > 0.0 and th[19] == 0.0


def test_thresholds_cover_every_week_in_the_window():
    th = stopping_thresholds({t: [3.0] for t in range(20, 39)}, last_gw=38,
                             first_gw=20)
    assert set(th) == set(range(20, 39))


def test_thresholds_are_never_negative():
    th = stopping_thresholds({t: [-5.0, -1.0] for t in range(5, 20)},
                             last_gw=19)
    assert min(th.values()) >= 0.0


def test_an_empty_distribution_gives_a_zero_threshold_everywhere():
    """Degradation: no calibration means no opinion about waiting, which is
    'play it when it is any good', not 'never play it'."""
    th = stopping_thresholds({}, last_gw=19, first_gw=5)
    assert set(th.values()) == {0.0}


# --- chip windows ----------------------------------------------------------

def test_the_first_half_ends_at_gameweek_nineteen():
    assert FIRST_HALF_LAST_GW == 19


def test_a_first_half_chip_expires_at_gameweek_nineteen():
    assert chip_windows(7) == (7, 19)


def test_a_second_half_chip_expires_at_gameweek_thirty_eight():
    assert chip_windows(25) == (25, 38)


def test_the_window_boundary_belongs_to_the_first_half():
    assert chip_windows(19) == (19, 19)
    assert chip_windows(20) == (20, 38)


# --- the flat fallback -----------------------------------------------------

def test_flat_thresholds_reproduce_todays_constants():
    """The degradation rail: no priors asset means exactly the old bars."""
    from gaffer.optimize.chips import (CHIP_PLAY_THRESHOLD,
                                       WILDCARD_RECOMMEND_THRESHOLD)

    flat = flat_thresholds()
    assert flat("bboost", 7) == CHIP_PLAY_THRESHOLD
    assert flat("3xc", 30) == CHIP_PLAY_THRESHOLD
    assert flat("freehit", 12) == CHIP_PLAY_THRESHOLD
    assert flat("wildcard", 7) == WILDCARD_RECOMMEND_THRESHOLD


def test_flat_thresholds_ignore_the_gameweek_entirely():
    """That is the bug this cycle is fixing, stated as a test so the fallback
    is unmistakably the *old* behaviour."""
    flat = flat_thresholds()
    assert flat("bboost", 5) == flat("bboost", 19) == flat("bboost", 38)


# --- the DGW scenario hook -------------------------------------------------

from gaffer.optimize.chip_policy import (DGW_SURPLUS_MULTIPLIER,
                                         apply_dgw_scenarios,
                                         load_chip_scenarios,
                                         thresholds_from_priors)

# ``test_the_scenario_file_is_absent_this_cycle`` lived here and is gone,
# knowingly, on its own authority: *"If this starts failing because someone
# populated it, delete this test — but do it knowingly."* v10b §F2b populates
# it — from the published fixture list, inside refresh-data — so on the first
# machine that sees a scheduled double this would have failed on a Tuesday, in
# a file nobody was editing, for a reason nobody would connect to the job that
# ran. What it was really protecting is now pinned as the writer's own
# contract in tests/test_v10b_chip_scenarios.py: a fixture list with no
# doubles writes no file. That assertion does not depend on the state of the
# developer's data directory, which is the other thing wrong with the test it
# replaces.


def test_loading_an_absent_scenario_file_is_an_empty_dict_not_an_error():
    assert load_chip_scenarios("data/does-not-exist.toml") == {}


def test_loading_a_scenario_file_reads_the_dgw_table(tmp_path):
    p = tmp_path / "chip_scenarios.toml"
    p.write_text("[dgw]\n26 = 0.7\n29 = 0.4\n")
    assert load_chip_scenarios(p) == {26: 0.7, 29: 0.4}


def test_a_scenario_file_with_no_dgw_table_is_empty(tmp_path):
    p = tmp_path / "chip_scenarios.toml"
    p.write_text("[bgw]\n18 = 0.5\n")
    assert load_chip_scenarios(p) == {}


def test_applying_no_scenarios_leaves_the_distributions_alone():
    dist = {26: [4.0, 8.0], 27: [3.0]}
    assert apply_dgw_scenarios(dist, {}) == dist


def test_a_certain_dgw_scales_every_sample():
    out = apply_dgw_scenarios({26: [4.0]}, {26: 1.0})
    assert set(out[26]) == {4.0 * DGW_SURPLUS_MULTIPLIER}


def test_a_probable_dgw_mixes_scaled_and_plain_samples():
    out = apply_dgw_scenarios({26: [4.0]}, {26: 0.7})
    assert out[26].count(8.0) == 7
    assert out[26].count(4.0) == 3


def test_a_dgw_on_a_week_with_no_samples_is_ignored():
    assert apply_dgw_scenarios({26: [4.0]}, {30: 0.9}) == {26: [4.0]}


def test_a_dgw_belief_raises_the_thresholds_before_that_week():
    """The behavioural point of the hook: knowing a double is coming should
    make the tool refuse to burn the chip beforehand."""
    dist = {"bboost": {t: [4.0] for t in range(5, 20)}}
    plain = thresholds_from_priors(dist)
    informed = thresholds_from_priors(dist, {18: 1.0})
    assert informed("bboost", 10) > plain("bboost", 10)


def test_thresholds_from_priors_falls_back_flat_for_an_unknown_chip():
    from gaffer.optimize.chips import CHIP_PLAY_THRESHOLD

    lookup = thresholds_from_priors({"bboost": {10: [4.0]}})
    assert lookup("3xc", 10) == CHIP_PLAY_THRESHOLD


def test_thresholds_from_priors_is_zero_at_each_expiry():
    """No chip stranded — spec §9's D3 condition, expressed as a unit test so
    the replay only has to confirm it."""
    dist = {"bboost": {t: [4.0] for t in range(1, 39)}}
    lookup = thresholds_from_priors(dist)
    assert lookup("bboost", 19) == 0.0
    assert lookup("bboost", 38) == 0.0


def test_the_two_chip_halves_are_solved_independently():
    """A chip held in the first half cannot be saved for the second, so a
    fat GW30 tail must not raise the GW10 bar."""
    dist = {"bboost": {**{t: [1.0] for t in range(1, 20)},
                       **{t: [40.0] for t in range(20, 39)}}}
    lookup = thresholds_from_priors(dist)
    assert lookup("bboost", 10) < 5.0
    assert lookup("bboost", 25) > 5.0


def test_a_gameweek_the_table_does_not_cover_keeps_the_flat_bar():
    """n7. A missing gameweek returned 0.0 — the most permissive bar in the
    system — which would play the chip on any positive surplus at all."""
    from gaffer.optimize.chip_policy import (flat_thresholds,
                                             thresholds_from_priors)

    flat = flat_thresholds()
    lookup = thresholds_from_priors({"bboost": {10: [3.0, 5.0, 7.0]}})
    assert lookup("bboost", 99) == flat("bboost", 99)
    assert lookup("bboost", 0) == flat("bboost", 0)
    assert lookup("bboost", 99) > 0.0
