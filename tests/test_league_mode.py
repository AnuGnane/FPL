import pandas as pd
import pytest
from gaffer.league_mode import (SIGMA, LAMBDA_CAP, Strategy,
                                compute_strategy, tilt_ep, win_probability)
from gaffer.optimize.milp import solve_plan
from tests.test_milp import _pool, _state

RIVALS = pd.DataFrame({"entry_name": ["Leader", "Mid", "Tail"],
                       "total": [500, 460, 400]})


def test_a_gap_inside_the_deadband_leaves_the_dial_at_exactly_zero():
    """Reverses the earlier "a small gap is a small chase" pin. The review
    found the consequence: tanh is never zero off zero, so on a live league
    lam was *always* non-zero and the production path could never reach the
    lam = 0 rails every degradation test is written against. A deadband on z
    makes neutral reachable — five points behind at GW10 is z ~ 0.05, noise.
    """
    s = compute_strategy(my_total=495, rivals=RIVALS, current_gw=10)
    assert s.z == 0.0            # 5 / (18 * sqrt(29)) ~ 0.05, inside the band
    assert s.lam == 0.0
    assert s.stance == "neutral"
    assert s.gap == 5            # the gap itself is still reported honestly


def test_a_gap_just_outside_the_deadband_still_chases_smoothly():
    """The band is a floor on noise, not a step change: past it the dial is
    the same smooth tanh it always was."""
    import math

    s = compute_strategy(my_total=440, rivals=RIVALS, current_gw=10)
    z = 60 / (18.0 * math.sqrt(29))
    assert z > 0.25
    assert s.stance == "chase"
    assert s.lam == pytest.approx(0.5 * math.tanh(z / 1.5))


def test_big_gap_chases_with_positive_lambda():
    import math

    s = compute_strategy(my_total=380, rivals=RIVALS, current_gw=30)
    z = 120 / (18.0 * math.sqrt(9))
    assert s.stance == "chase"
    assert s.lam == pytest.approx(0.5 * math.tanh(z / 1.5))
    assert s.z == pytest.approx(z)
    assert s.sigma_m == 18.0
    assert s.rival_name == "Leader"
    assert s.gap == 120


def test_leading_big_defends_with_negative_lambda():
    s = compute_strategy(my_total=560, rivals=RIVALS, current_gw=36)
    assert s.stance == "defend" and s.lam < 0
    assert s.rival_name == "Leader"          # nearest chaser


def test_win_probability_symmetric_and_bounded():
    assert win_probability(500, 500, 10) == pytest.approx(0.5)
    assert 0.5 < win_probability(520, 500, 10) < 1.0


def test_empty_rivals_is_neutral():
    s = compute_strategy(500, pd.DataFrame(columns=["entry_name", "total"]),
                         10)
    assert s.stance == "neutral" and s.lam == 0.0


def test_tied_with_leader_is_neutral():
    """Dead level: gap 0 must land on neutral, not flip into a stance."""
    s = compute_strategy(my_total=500, rivals=RIVALS, current_gw=36)
    assert s.stance == "neutral"
    assert s.lam == 0.0
    assert s.gap == 0
    assert isinstance(s, Strategy)
    assert (SIGMA, LAMBDA_CAP) == (18.0, 0.5)


def test_tilt_zero_lambda_is_identity():
    ep_by = {(1, 5): 4.0, (2, 5): 4.0}
    assert tilt_ep(ep_by, {1: 0.9}, 0.0) == ep_by


def test_tilt_chasing_discounts_the_covered_and_leaves_the_rest_raw():
    """Chasing is re-anchored on the *uncovered* player: he keeps his real
    expected points and the template is marked down, rather than the whole
    board being multiplied up past the point-priced hit_cost / ft_value /
    itb_value constants the objective is scored against."""
    ep_by = {(1, 5): 4.0, (2, 5): 4.0}
    out = tilt_ep(ep_by, {1: 1.0, 2: 0.0}, 0.4)
    assert out[(1, 5)] == pytest.approx(4.0 / 1.4)    # fully covered
    assert out[(2, 5)] == pytest.approx(4.0)          # uncovered: raw ep


def test_tilt_never_inflates_the_board_above_raw_ep():
    """The defect this pins: a chasing lam scaled every value up, so a 4-point
    hit was quietly worth 4 / (1 + lam) tilted points and the optimizer took
    transfers it would not have taken at the same real prices."""
    ep_by = {(1, 5): 4.0, (2, 5): 6.0, (3, 5): 5.0}
    cover = {1: 1.0, 2: 0.5, 3: 0.0}
    for lam in (0.1, 0.25, 0.5):
        out = tilt_ep(ep_by, cover, lam)
        assert max(out[k] / ep_by[k] for k in ep_by) == pytest.approx(1.0)


def test_tilt_defending_penalizes_differentials():
    out = tilt_ep({(1, 5): 4.0, (2, 5): 4.0}, {1: 1.0, 2: 0.0}, -0.3)
    assert out[(1, 5)] == pytest.approx(4.0)
    assert out[(2, 5)] == pytest.approx(4.0 * 0.7)


def test_tilt_cover_above_one_is_clamped():
    """cover_table clamps already; tilt_ep clamps again so a hand-built or
    stale table can never invert the sign of the tilt."""
    out = tilt_ep({(1, 5): 4.0}, {1: 1.8}, 0.4)
    assert out[(1, 5)] == pytest.approx(4.0 / 1.4)


def test_tilt_v2_reduces_to_the_old_league_eo_formula_re_anchored():
    """The generalization is strict up to the anchor: cover_from_eo(EO%)
    through the new tilt is the number the v1 tilt produced from the same EO,
    divided by (1 + lam). The old formula shared the inflation defect — it
    multiplied the whole board up — so the shapes agree and only the level
    moves, which is the only part of it the objective's point-priced
    constants ever cared about."""
    from gaffer.league_mode import cover_from_eo

    ep_by = {(1, 5): 4.0, (2, 5): 6.0}
    eo = {1: 90.0, 2: 10.0}
    out = tilt_ep(ep_by, cover_from_eo(eo), 0.4)
    assert out[(1, 5)] == pytest.approx(4.0 * (1 + 0.4 * (1 - 0.9)) / 1.4)
    assert out[(2, 5)] == pytest.approx(6.0 * (1 + 0.4 * (1 - 0.1)) / 1.4)


def test_zero_lambda_reproduces_v1_solution():
    """lam=0 must leave the v1 points-max MILP solution bit-identical."""
    pool = _pool(star_ep=9.0)
    gws = [1, 2]
    ep_by = {(int(r["code"]), g): float(r["ep"][g])
             for _, r in pool.iterrows() for g in gws}
    # nonzero, non-uniform cover: an identity bug would perturb the pool.
    eo = {int(c): ((i * 37) % 150) / 100.0 for i, c in enumerate(pool["code"])}

    tilted = tilt_ep(ep_by, eo, 0.0)
    pool_tilted = pool.copy()
    pool_tilted["ep"] = [{g: tilted[(int(c), g)] for g in gws}
                         for c in pool_tilted["code"]]

    kw = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1,
              ft_value=1.5, itb_value=0.05, hit_cost=4)
    base = solve_plan(pool, _state(ft=1), **kw).gw_plans[0]
    same = solve_plan(pool_tilted, _state(ft=1), **kw).gw_plans[0]

    assert sorted(same.squad) == sorted(base.squad)
    assert sorted(same.xi) == sorted(base.xi)
    assert same.captain == base.captain
    assert sorted(same.buys) == sorted(base.buys)
    assert sorted(same.sells) == sorted(base.sells)


def test_explain_lam_puts_the_tilt_in_words():
    from gaffer.league_mode import Strategy, explain_lam

    chase = explain_lam(Strategy(0.4, 84, 30, "chase", "Ten Hag Hive"))
    assert "84 points behind Ten Hag Hive" in chase
    assert "differentials" in chase

    defend = explain_lam(Strategy(-0.3, 40, 12, "defend", "Ten Hag Hive"))
    assert "40 points ahead of Ten Hag Hive" in defend
    assert "mirror" in defend

    level = explain_lam(Strategy(0.0, 0, 30, "neutral", "Ten Hag Hive"))
    assert "exactly level with Ten Hag Hive" in level
    assert "points-max" in level


def test_explain_lam_tells_a_dead_heat_from_a_deadbanded_gap():
    """Neutral has two causes since the deadband: a level scoreline, and a
    gap the dial is treating as noise. Saying "exactly level" on the second
    would be a lie the standings table sitting next to it disproves."""
    from gaffer.league_mode import Strategy, explain_lam

    dead_heat = explain_lam(Strategy(0.0, 0, 30, "neutral", "Ten Hag Hive"))
    assert dead_heat.startswith("λ 0.00: ")
    assert "exactly level with Ten Hag Hive" in dead_heat
    assert "deadband" not in dead_heat

    # The gap compute_strategy reports is the real one even inside the band.
    banded = explain_lam(Strategy(0.0, 5, 30, "neutral", "Ten Hag Hive"))
    assert banded.startswith("λ 0.00: ")
    assert "the gap to Ten Hag Hive is inside the deadband" in banded
    assert "exactly level" not in banded
    assert "points-max" in banded


def test_the_deadband_sentence_is_what_a_small_gap_actually_renders():
    """End to end: the strategy the dial builds five points behind is the one
    the panel explains, so the two cannot drift apart."""
    from gaffer.league_mode import explain_lam

    s = compute_strategy(my_total=495, rivals=RIVALS, current_gw=10)
    assert s.stance == "neutral" and s.gap == 5
    assert "inside the deadband" in explain_lam(s)


# --- v4d: the dial's parameters --------------------------------------------


def test_league_params_default_to_the_module_constants():
    from gaffer.league_mode import (LAMBDA_CAP, SIGMA_CAP, SIGMA_FLOOR,
                                    SIGMA_MIN_WEEKS, Z_SCALE, LeagueParams)

    from gaffer.league_mode import Z_DEADBAND

    p = LeagueParams()
    assert (p.z_scale, p.lambda_cap) == (Z_SCALE, LAMBDA_CAP)
    assert (p.sigma_floor, p.sigma_cap) == (SIGMA_FLOOR, SIGMA_CAP)
    assert p.sigma_min_weeks == SIGMA_MIN_WEEKS
    assert p.z_deadband == Z_DEADBAND == 0.25


def test_league_params_read_a_config_without_importing_it():
    """Duck-typed on the attributes: league_mode must not import config."""
    from types import SimpleNamespace

    from gaffer.league_mode import LeagueParams

    cfg = SimpleNamespace(z_scale=2.0, lambda_cap=0.25, sigma_floor=5.0,
                          sigma_cap=40.0, sigma_min_weeks=3, z_deadband=0.4)
    p = LeagueParams.from_config(cfg)
    assert (p.z_scale, p.lambda_cap, p.sigma_floor) == (2.0, 0.25, 5.0)
    assert (p.sigma_cap, p.sigma_min_weeks) == (40.0, 3)
    assert p.z_deadband == 0.4


def test_league_params_reject_a_non_positive_divisor():
    """Both are divisors. A zero does not read as 'off': it is a
    ZeroDivisionError inside compute_strategy, and a negative one silently
    inverts every z. Caught where it is configured."""
    from types import SimpleNamespace

    from gaffer.league_mode import LeagueParams

    with pytest.raises(ValueError, match="z_scale"):
        LeagueParams.from_config(SimpleNamespace(z_scale=0.0))
    with pytest.raises(ValueError, match="z_scale"):
        LeagueParams.from_config(SimpleNamespace(z_scale=-1.5))
    with pytest.raises(ValueError, match="sigma_floor"):
        LeagueParams.from_config(SimpleNamespace(sigma_floor=0.0))
    with pytest.raises(ValueError, match="sigma_floor"):
        LeagueParams.from_config(SimpleNamespace(sigma_floor=-8.0))


def test_the_old_sigma_pin_is_still_importable_under_both_names():
    """SIGMA is asserted by an existing test and imported elsewhere; the
    renamed SIGMA_FALLBACK is the same number, not a second policy."""
    from gaffer.league_mode import SIGMA, SIGMA_FALLBACK

    assert SIGMA == SIGMA_FALLBACK == 18.0


# --- v4d: sigma from league history ----------------------------------------


def _history(series: dict[int, list[int]]) -> pd.DataFrame:
    """{entry: [gw1 points, gw2 points, ...]} -> the fetcher's frame shape."""
    rows = [{"entry": entry, "gw": i + 1, "points": p}
            for entry, points in series.items()
            for i, p in enumerate(points)]
    return pd.DataFrame(rows, columns=["entry", "gw", "points"])


def test_margin_sigma_is_the_stdev_of_the_margin_series():
    from gaffer.league_mode import margin_sigma

    # Margins: +10, -10, +10, -10, +10, -10 -> stdev ~ 10.95, inside bounds.
    hist = _history({1: [60, 40, 60, 40, 60, 40],
                     2: [50, 50, 50, 50, 50, 50]})
    out = margin_sigma(hist, my_entry=1)
    assert out[2] == pytest.approx(10.954, abs=1e-3)


def test_margin_sigma_floors_a_mirrored_squad():
    """Identical squads produce near-zero margins; without the floor z would
    explode and lam would saturate on noise."""
    from gaffer.league_mode import SIGMA_FLOOR, margin_sigma

    hist = _history({1: [50, 51, 50, 51, 50, 51],
                     2: [50, 51, 50, 51, 50, 50]})
    assert margin_sigma(hist, my_entry=1)[2] == SIGMA_FLOOR


def test_margin_sigma_caps_a_wild_series():
    from gaffer.league_mode import SIGMA_CAP, margin_sigma

    hist = _history({1: [120, 20, 120, 20, 120, 20],
                     2: [20, 120, 20, 120, 20, 120]})
    assert margin_sigma(hist, my_entry=1)[2] == SIGMA_CAP


def test_margin_sigma_falls_back_to_the_pooled_league_sigma():
    """A rival with three weeks of history borrows the league's pooled
    margin spread rather than trusting three points."""
    from gaffer.league_mode import margin_sigma

    hist = pd.concat([
        _history({1: [60, 40, 60, 40, 60, 40],
                  2: [50, 50, 50, 50, 50, 50]}),
        _history({3: [49, 51, 49]}),
    ], ignore_index=True)
    out = margin_sigma(hist, my_entry=1)
    pooled_borrower, established = out[3], out[2]
    assert pooled_borrower != pytest.approx(established, abs=1e-9)
    assert 8.0 <= pooled_borrower <= 30.0


def test_margin_sigma_pools_only_when_the_pool_spans_enough_gameweeks():
    """A ten-rival league one week into the season has ten pooled margins and
    no weeks. Gating on the count made that a 'pooled sigma' — a purely
    cross-sectional spread of how good the rivals are, which is not the
    week-to-week volatility the z-dial divides by."""
    from gaffer.league_mode import SIGMA_FALLBACK, margin_sigma

    hist = pd.DataFrame(
        [{"entry": 1, "gw": 1, "points": 60}]
        + [{"entry": e, "gw": 1, "points": 30 + 5 * e} for e in range(2, 12)])
    out = margin_sigma(hist, my_entry=1)
    assert len(out) == 10
    assert set(out.values()) == {SIGMA_FALLBACK}


def test_margin_sigma_falls_back_to_the_pin_with_no_history_at_all():
    from gaffer.league_mode import SIGMA_FALLBACK, margin_sigma

    hist = _history({1: [50], 2: [40]})     # one week: nothing poolable
    assert margin_sigma(hist, my_entry=1)[2] == SIGMA_FALLBACK


def test_margin_sigma_of_an_empty_frame_is_empty():
    from gaffer.league_mode import margin_sigma

    assert margin_sigma(pd.DataFrame(columns=["entry", "gw", "points"]),
                        my_entry=1) == {}
    assert margin_sigma(None, my_entry=1) == {}


def test_margin_sigma_only_pairs_gameweeks_we_both_played():
    """A rival who joined at GW3 has no GW1-2 margin; pairing on index
    instead of gameweek would invent two."""
    from gaffer.league_mode import margin_sigma

    hist = pd.concat([_history({1: [50, 60, 70, 80, 90, 100, 55]}),
                      pd.DataFrame([{"entry": 2, "gw": g, "points": p}
                                    for g, p in [(3, 70), (4, 80)]])],
                     ignore_index=True)
    out = margin_sigma(hist, my_entry=1)
    assert out[2] == pytest.approx(18.0)    # 2 shared weeks -> the pin


# --- v4d: the z-dial -------------------------------------------------------


def test_a_runaway_leader_saturates_below_the_cap():
    """tanh is asymptotic: no gap, however silly, can exceed lambda_cap."""
    s = compute_strategy(my_total=0, rivals=RIVALS, current_gw=37)
    assert 0.49 < s.lam < 0.5


def test_leading_defends_against_the_nearest_threat_in_sigma_units():
    """The threat is the rival most likely to catch me, not the one with the
    largest raw total: a tight rival 30 behind at sigma 8 is further away in
    normalized units than a volatile one 40 behind at sigma 30."""
    from gaffer.league_mode import compute_strategy

    rivals = pd.DataFrame({"entry": [11, 12], "entry_name": ["Volatile",
                                                             "Tight"],
                           "total": [460, 470]})
    history = pd.concat([
        _history({1: [80] * 6, 11: [20, 140, 20, 140, 20, 140],
                  12: [78, 82, 78, 82, 78, 82]}),
    ], ignore_index=True)
    s = compute_strategy(my_total=500, rivals=rivals, current_gw=38,
                         history=history, my_entry=1)
    assert s.stance == "defend" and s.lam < 0
    assert s.rival_name == "Volatile"        # 40 / 30 = 1.33 < 30 / 8 = 3.75
    assert s.sigma_m == 30.0
    assert s.gap == 40


def test_the_dead_heat_z_is_exactly_zero_and_not_negative_zero():
    """-0.0 renders as a typo in the report and would flip the stance test."""
    s = compute_strategy(my_total=500, rivals=RIVALS, current_gw=36)
    assert s.z == 0.0
    assert str(s.z) == "0.0"
    assert s.lam == 0.0 and s.stance == "neutral"


def test_strategy_carries_the_new_fields_with_defaults():
    """Appended last and defaulted: the positional constructions in this file
    and in the report path keep working."""
    from gaffer.league_mode import SIGMA_FALLBACK, Strategy

    s = Strategy(0.4, 84, 30, "chase", "Ten Hag Hive")
    assert s.z == 0.0
    assert s.sigma_m == SIGMA_FALLBACK
    assert s.cover_weights == {}


# --- v4d: threat weights and covering --------------------------------------


def test_threat_weights_behind_are_all_on_the_leader():
    """Behind, the win condition is one entry: the leader. Nobody else is
    between me and the title, so nobody else gets weight."""
    from gaffer.league_mode import threat_weights

    rivals = pd.DataFrame({"entry": [11, 12, 13],
                           "entry_name": ["Leader", "Mid", "Tail"],
                           "total": [500, 460, 400]})
    w = threat_weights(my_total=450, rivals=rivals, sigmas={}, weeks_left=9)
    assert w == {11: 1.0}


def test_threat_weights_ahead_favour_the_nearest_and_sum_to_one():
    from gaffer.league_mode import threat_weights

    rivals = pd.DataFrame({"entry": [11, 12],
                           "entry_name": ["Close", "Far"],
                           "total": [495, 460]})
    w = threat_weights(my_total=500, rivals=rivals, sigmas={11: 18.0,
                                                            12: 18.0},
                       weeks_left=9)
    assert sum(w.values()) == pytest.approx(1.0)
    assert w[11] > w[12]


def test_threat_weights_ahead_ignore_a_rival_two_hundred_adrift():
    """A rival beyond 3 sigma-root-W back contributes ~nothing, so covering
    his squad must not shape my pool at all."""
    from gaffer.league_mode import threat_weights

    rivals = pd.DataFrame({"entry": [11, 12],
                           "entry_name": ["Close", "Gone"],
                           "total": [495, 300]})
    w = threat_weights(my_total=500, rivals=rivals,
                       sigmas={11: 18.0, 12: 18.0}, weeks_left=9)
    assert set(w) == {11}
    assert w[11] == pytest.approx(1.0)


def test_threat_weights_with_nobody_in_range_fall_back_to_the_nearest():
    """An empty weight table would make every cover zero, which reads as
    'nobody owns anybody' — the nearest rival is the honest answer."""
    from gaffer.league_mode import threat_weights

    rivals = pd.DataFrame({"entry": [11, 12], "entry_name": ["A", "B"],
                           "total": [100, 50]})
    w = threat_weights(my_total=500, rivals=rivals,
                       sigmas={11: 8.0, 12: 8.0}, weeks_left=1)
    assert w == {11: 1.0}


def test_threat_weights_without_entry_ids_are_empty():
    """The report-only rivals frame in the tests has no entry column; an
    exception there would take the whole advice down."""
    from gaffer.league_mode import threat_weights

    assert threat_weights(500, RIVALS, {}, 9) == {}


PICKS = {11: [{"element": 1, "multiplier": 2},      # captained
              {"element": 2, "multiplier": 1},
              {"element": 3, "multiplier": 0}],     # benched
         12: [{"element": 2, "multiplier": 1},
              {"element": 4, "multiplier": 1}]}


def test_cover_counts_captaincy_double_and_the_bench_zero():
    from gaffer.league_mode import cover_table

    cover = cover_table(PICKS, {11: 0.5, 12: 0.5})
    assert cover[1] == pytest.approx(1.0)      # 0.5 * 2, clamped at 1
    assert cover[2] == pytest.approx(1.0)      # 0.5 + 0.5
    assert cover[4] == pytest.approx(0.5)
    assert 3 not in cover                      # benched: owned by nobody


def test_cover_clamps_after_weighting_not_before():
    """0.6 * 2 = 1.2 must become 1.0 at the end, not 0.6 * min(2, 1)."""
    from gaffer.league_mode import cover_table

    cover = cover_table({11: [{"element": 1, "multiplier": 2}]}, {11: 0.6})
    assert cover[1] == 1.0


def test_cover_ignores_a_rival_with_no_weight():
    from gaffer.league_mode import cover_table

    assert cover_table(PICKS, {11: 1.0}) == {1: 1.0, 2: 1.0}


def test_cover_with_equal_weights_reduces_to_league_eo():
    """The generalization is strict: equal weights and no captaincy give
    exactly effective_ownership / 100."""
    from gaffer.data.league import effective_ownership
    from gaffer.league_mode import cover_from_eo, cover_table

    picks = {11: [{"element": 1, "multiplier": 1},
                  {"element": 2, "multiplier": 1}],
             12: [{"element": 1, "multiplier": 1}],
             13: [{"element": 3, "multiplier": 1}]}
    equal = {e: 1 / 3 for e in picks}
    # effective_ownership rounds to one decimal place of a percent, so the
    # comparison is to that precision — 0.667 against 0.6666..., not exact.
    assert cover_table(picks, equal) == pytest.approx(
        cover_from_eo(effective_ownership(picks)), abs=0.01)


def test_captain_cover_counts_only_armbands():
    from gaffer.league_mode import captain_cover

    caps = captain_cover(PICKS, {11: 0.7, 12: 0.3})
    assert caps == {1: pytest.approx(0.7)}


def test_cover_from_eo_clamps_the_over_hundred_case():
    from gaffer.league_mode import cover_from_eo

    assert cover_from_eo({1: 180.0, 2: 40.0}) == {1: 1.0, 2: 0.4}


# --- v4d: EO-aware captaincy -----------------------------------------------

EP_OF = {1: 9.0, 2: 8.6, 3: 7.0}


def test_tilted_captaincy_at_zero_lambda_is_argmax_raw_ep():
    """The rail: with no tilt the armband is exactly where v4c put it."""
    from gaffer.league_mode import tilted_captaincy

    assert tilted_captaincy([3, 1, 2], EP_OF, {1: 1.0}, 0.0) == (1, 2)


def test_tilted_captaincy_chasing_prefers_the_uncaptained_ceiling():
    """Behind: a captain nobody relevant is captaining scores higher — the
    variance-seeking split the rank payoff implies."""
    from gaffer.league_mode import tilted_captaincy

    captain, vice = tilted_captaincy([1, 2, 3], EP_OF, {1: 1.0, 2: 0.0}, 0.4)
    assert captain == 2          # 8.6 * 1.4 = 12.04 beats 9.0 * 1.0
    # The vice keeps the same rule on the same tilted score (spec §6), so the
    # uncovered 7.0 (7.0 * 1.4 = 9.8) outranks the fully covered 9.0.
    assert vice == 3


def test_tilted_captaincy_defending_mirrors_the_threats_armband():
    from gaffer.league_mode import tilted_captaincy

    captain, _ = tilted_captaincy([1, 2, 3], EP_OF, {1: 1.0, 2: 0.0}, -0.3)
    assert captain == 1          # 9.0 * 1.0 beats 8.6 * 0.7


def test_tilted_captaincy_breaks_ties_on_raw_ep_then_code():
    """Determinism matters: two equal tilted scores must not depend on the
    order the XI came out of the MILP."""
    from gaffer.league_mode import tilted_captaincy

    ep = {5: 6.0, 6: 6.0}
    assert tilted_captaincy([6, 5], ep, {}, 0.4) == (5, 6)


def test_tilted_captaincy_of_a_one_man_xi_names_him_twice():
    from gaffer.league_mode import tilted_captaincy

    assert tilted_captaincy([1], EP_OF, {}, 0.4) == (1, 1)


def test_captaincy_override_needs_a_real_margin_not_a_hairline():
    """The seam swapped the armband on any tilted win at all, so a 0.01xPts
    edge — well inside the model's own error — moved the captain."""
    from gaffer.league_mode import CAPTAIN_OVERRIDE_MARGIN, captaincy_override

    assert CAPTAIN_OVERRIDE_MARGIN == 0.15
    # 8.95 * 1.4 = 12.53 against 9.0 * 1.4 = 12.6: the challenger loses.
    ep = {1: 9.0, 2: 8.95}
    assert captaincy_override([1, 2], ep, {}, 0.4, incumbent=1) is None


def test_captaincy_override_returns_none_inside_the_margin():
    from gaffer.league_mode import captaincy_override

    # Fully covered incumbent 9.0 -> 9.0; uncovered 6.5 -> 6.5 * 1.4 = 9.1.
    # A 0.1 tilted edge is inside the 0.15 margin: leave the armband alone.
    ep = {1: 9.0, 2: 6.5}
    assert captaincy_override([1, 2], ep, {1: 1.0}, 0.4, incumbent=1) is None


def test_captaincy_override_fires_once_the_margin_is_cleared():
    from gaffer.league_mode import captaincy_override

    # uncovered 6.7 -> 9.38 against a covered 9.0: a 0.38 edge, cleared.
    ep = {1: 9.0, 2: 6.7, 3: 5.0}
    assert captaincy_override([1, 2, 3], ep, {1: 1.0}, 0.4,
                              incumbent=1) == (2, 1)


def test_captaincy_override_at_zero_lambda_is_always_none():
    """The rail: with no tilt the v4c armband stands, whatever the covers."""
    from gaffer.league_mode import captaincy_override

    ep = {1: 9.0, 2: 8.6, 3: 7.0}
    for cover in ({}, {1: 1.0}, {2: 1.0, 3: 0.5}):
        assert captaincy_override([1, 2, 3], ep, cover, 0.0, incumbent=1) \
            is None
        # even when the incumbent is not the raw argmax
        assert captaincy_override([1, 2, 3], ep, cover, 0.0, incumbent=3) \
            is None


def test_captaincy_note_names_the_threat_being_covered():
    from gaffer.league_mode import captaincy_note

    note = captaincy_note(-0.3, chosen=1, demoted=2,
                          rival_captains={11: 1, 12: 3},
                          weights={11: 0.8, 12: 0.2},
                          names={11: "Ten Hag Hive", 12: "Tail"})
    assert note == "covering Ten Hag Hive's last armband"


def test_captaincy_note_names_the_threat_being_differed_from():
    from gaffer.league_mode import captaincy_note

    note = captaincy_note(0.4, chosen=2, demoted=1,
                          rival_captains={11: 1, 12: 1},
                          weights={11: 0.9, 12: 0.1},
                          names={11: "Ten Hag Hive", 12: "Tail"})
    assert note == "differential vs Ten Hag Hive's last armband"


def test_captaincy_note_is_empty_when_nothing_changed():
    from gaffer.league_mode import captaincy_note

    assert captaincy_note(0.0, 1, 1, {}, {}, {}) == ""
    assert captaincy_note(0.4, 1, 1, {11: 1}, {11: 1.0}, {11: "A"}) == ""


def test_captaincy_note_degrades_when_no_rival_captains_either_player():
    from gaffer.league_mode import captaincy_note

    assert captaincy_note(0.4, 2, 1, {}, {}, {}) == "differential vs the field"
    assert captaincy_note(-0.3, 2, 1, {}, {}, {}) == \
        "covering the field's last armband"
