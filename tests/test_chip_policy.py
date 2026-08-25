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
