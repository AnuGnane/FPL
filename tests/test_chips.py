import pandas as pd
from gaffer.optimize.milp import SolveInput
from gaffer.optimize.chips import evaluate_chips, wildcard_now_assessment


def _pool():
    rows = []
    code = 1
    for pos, n in [("GKP", 2), ("DEF", 6), ("MID", 7), ("FWD", 5)]:
        for _ in range(n):
            rows.append({"code": code, "position": pos, "team_code": code % 8,
                         "cost": 50, "sell": 50,
                         "ep": {1: 3.0, 2: 3.0}})
            code += 1
    return pd.DataFrame(rows)


OWNED = [1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 16, 17, 18]  # legal 15

CFG = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
           itb_value=0.05, hit_cost=4)


def test_evaluate_chips_returns_delta_per_chip_gw():
    state = SolveInput(owned_codes=list(OWNED), bank=0,
                       free_transfers=1, gws=[1, 2])
    cfg = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
               itb_value=0.05, hit_cost=4)
    table = evaluate_chips(_pool(), state, chips_available=["bboost", "3xc"],
                           **cfg)
    assert {"chip", "gw", "gain"} <= set(table.columns)
    # bench boost on identical 3.0-EP players: gain ≈ 4 players * 3 EP * (1-0.1)
    bb = table[(table.chip == "bboost") & (table.gw == 1)]["gain"].iloc[0]
    assert bb > 8.0
    assert (table["gain"] > -1e-6).all()   # chips never forced to hurt


def _bad_squad_pool():
    """Same shape as _pool() but the five non-owned players are elite."""
    pool = _pool()
    elite = {8, 14, 15, 19, 20}          # DEF, MID, MID, FWD, FWD
    pool["ep"] = [
        {1: 8.0, 2: 8.0} if c in elite else {1: 2.0, 2: 2.0}
        for c in pool["code"]
    ]
    return pool


def test_wildcard_gain_is_large_when_squad_is_bad():
    state = SolveInput(owned_codes=list(OWNED), bank=0,
                       free_transfers=1, gws=[1, 2])
    table = evaluate_chips(_bad_squad_pool(), state,
                           chips_available=["wildcard", "bboost", "3xc"],
                           **CFG)
    wc = table[(table.chip == "wildcard") & (table.gw == 1)]["gain"].iloc[0]
    assert wc > 5.0
    # No chip may be forced to hurt, with one priced exception: a wildcard
    # forgoes that week's +1 free transfer (the count carries over unchanged,
    # the official rule), so in a week where it buys nothing its gain is
    # -ft_value and never lower.
    is_wc = table["chip"] == "wildcard"
    assert (table.loc[~is_wc, "gain"] > -1e-6).all()
    assert (table.loc[is_wc, "gain"] > -CFG["ft_value"] - 1e-6).all()


def test_wildcard_now_assessment_recommends_only_when_it_pays():
    state = SolveInput(owned_codes=list(OWNED), bank=0,
                       free_transfers=1, gws=[1, 2])
    bad = wildcard_now_assessment(_bad_squad_pool(), state, **CFG)
    assert bad["recommend"] is True
    assert bad["gain_over_horizon"] > 8.0
    assert len(bad["wc_squad"]) == 15

    ok = wildcard_now_assessment(_pool(), state, **CFG)
    assert ok["recommend"] is False


def test_passing_base_matches_re_solving_it():
    """run_advise scores several chips against one baseline; the helpers must
    accept a pre-solved one rather than re-solving the same MILP each time."""
    from gaffer.optimize.chips import chip_baseline

    pool, state = _pool(), SolveInput(owned_codes=list(OWNED), bank=0,
                                      free_transfers=1, gws=[1, 2])
    base = chip_baseline(pool, state, **CFG)

    chips = ["wildcard", "bboost", "3xc", "freehit"]
    a = evaluate_chips(pool, state, chips, **CFG)
    b = evaluate_chips(pool, state, chips, base=base, **CFG)
    pd.testing.assert_frame_equal(a, b)

    assert (wildcard_now_assessment(pool, state, **CFG)
            == wildcard_now_assessment(pool, state, base=base, **CFG))


def _pool_gws(gws):
    """_pool() with the EP dict spanning ``gws`` instead of [1, 2]."""
    pool = _pool()
    pool["ep"] = [dict.fromkeys(gws, 3.0) for _ in pool["code"]]
    return pool


# --- the "every chip's best week is this week" bias -----------------------
# The MILP objective discounts gameweek t by decay ** t, so an *identical*
# chip played a week later scores ~15% less for no footballing reason. Chips
# are counterfactuals, not plans: they must be scored in an undecayed frame.

FLAT_GWS = [1, 2, 3]
"""Horizon for the bias tests. Every EP is identical in every one of these
weeks, so the weeks are interchangeable and any difference between them is
an artefact of the scoring, not of the fixtures."""

# itb_value=0 drops the terminal in-the-bank term, which a wildcard shifts by
# a constant that would otherwise pollute the per-week figure; the punitive
# hit cost keeps the no-chip baseline still (see _out_of_reach_pool).
FLAT_CFG = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
                itb_value=0.0, hit_cost=1000)


def _flat_state():
    return SolveInput(owned_codes=list(OWNED), bank=0, free_transfers=0,
                      gws=list(FLAT_GWS))


# The wildcard case needs a *stationary* baseline: if the no-chip plan can
# drift towards the good players week by week, a later wildcard genuinely is
# worth less per week and there is no invariant left to test. So the elite
# players are priced out of reach one or two at a time — funding one costs
# six sales, which is nothing to a wildcard and impossible inside the free
# transfers a three-week horizon hands out.
ELITE = {10, 19, 20, 27, 28}
BIG_OWNED = [1, 2, 5, 6, 7, 8, 9, 14, 15, 16, 17, 18, 24, 25, 26]


def _out_of_reach_pool():
    rows = []
    for pos, lo, hi in [("GKP", 1, 4), ("DEF", 5, 13), ("MID", 14, 23),
                        ("FWD", 24, 30)]:
        for code in range(lo, hi + 1):
            rows.append({
                "code": code, "position": pos, "team_code": code % 12,
                "ep": dict.fromkeys(FLAT_GWS, 8.0 if code in ELITE else 2.0),
                "cost": 100 if code in ELITE else 40,
                "sell": 100 if code in ELITE
                        else (50 if code in BIG_OWNED else 40)})
    return pd.DataFrame(rows)


def test_one_week_chip_gains_do_not_decay_across_identical_weeks():
    """Same EPs every week ⇒ the same bench boost / triple captain gain every
    week. Any monotone decline is the objective's time discount leaking into
    a counterfactual it has no business shaping."""
    table = evaluate_chips(_pool_gws(FLAT_GWS), _flat_state(),
                           chips_available=["bboost", "3xc"], **FLAT_CFG)
    for chip in ("bboost", "3xc"):
        gains = table[table.chip == chip].sort_values("gw")["gain"].tolist()
        assert len(gains) == len(FLAT_GWS)
        assert max(gains) - min(gains) < 1e-6, f"{chip} decays: {gains}"


def test_wildcard_per_week_gain_is_flat_across_identical_weeks():
    """A wildcard played in GW t is credited with weeks t..end of the horizon,
    so its *total* gain shrinks as t moves later — that is honest truncation.
    Its per-week gain must not shrink: that would be the decay again."""
    state = SolveInput(owned_codes=list(BIG_OWNED), bank=0, free_transfers=0,
                       gws=list(FLAT_GWS))
    # ft_value off: the wildcard forgoes one +1 accrual (the count carries
    # over unchanged), a one-off cost that amortises over a shrinking number
    # of remaining weeks and would read as decay here. The guard is about
    # points, so price the transfers at zero and measure the points alone.
    table = evaluate_chips(_out_of_reach_pool(), state,
                           chips_available=["wildcard"],
                           **{**FLAT_CFG, "ft_value": 0.0})
    wc = table[table.chip == "wildcard"].sort_values("gw")
    assert wc["gain"].iloc[0] > 5.0            # the wildcard is worth playing
    per_week = wc["per_week"].tolist()
    assert len(per_week) == len(FLAT_GWS)
    # Both columns are rounded to 2dp for display, so "equal" is 2dp-equal
    # here; the decay it is guarding against moved these by 15% a week.
    assert max(per_week) - min(per_week) <= 0.01, \
        f"wildcard decays: {per_week}"
    # ...and the total really is the per-week figure times the weeks covered.
    for n, (gain, pw) in zip(range(len(FLAT_GWS), 0, -1),
                             zip(wc["gain"], per_week)):
        assert abs(gain - pw * n) <= 0.01 * n


def test_second_half_chips_offered_when_horizon_crosses_gw19():
    """A wildcard spent in GW5 is gone for the rest of the first half, but a
    fresh one arrives at GW20 — a horizon straddling the boundary must offer
    it there."""
    from gaffer.advise import chips_available_for

    gws = [18, 19, 20, 21]
    state = SolveInput(owned_codes=list(OWNED), bank=0,
                       free_transfers=1, gws=gws)
    chips_by_gw = {5: "wildcard"}
    avail_by_gw = {g: chips_available_for(chips_by_gw, g) for g in gws}
    table = evaluate_chips(_pool_gws(gws), state, avail_by_gw=avail_by_gw,
                           **CFG)
    wc_gws = sorted(table[table.chip == "wildcard"]["gw"].tolist())
    assert wc_gws == [20, 21]
    # never played, so available in both halves
    assert sorted(table[table.chip == "bboost"]["gw"].tolist()) == gws
    assert sorted(table[table.chip == "freehit"]["gw"].tolist()) == gws


def test_flat_chips_available_path_is_unchanged():
    """The flat list stays supported and equals the per-gw mapping that repeats
    it for every gameweek."""
    gws = [1, 2]
    pool = _pool()
    state = SolveInput(owned_codes=list(OWNED), bank=0,
                       free_transfers=1, gws=gws)
    chips = ["wildcard", "bboost", "3xc", "freehit"]
    flat = evaluate_chips(pool, state, chips, **CFG)
    mapped = evaluate_chips(pool, state,
                            avail_by_gw={g: list(chips) for g in gws}, **CFG)
    pd.testing.assert_frame_equal(flat, mapped)


def test_evaluate_chips_returns_an_empty_table_when_nothing_is_available():
    """A squad that has spent every chip is a normal late-season state, not an
    error — the caller gets an empty [chip, gw, gain] frame to fold.

    v12 W3 §4.5 added ``gw2`` — the second week of a chip *pair* — so the
    empty frame carries it too. A column that appears and disappears with the
    row count is worse than one that is always there and always None.
    """
    state = SolveInput(owned_codes=list(OWNED), bank=0,
                       free_transfers=1, gws=[1, 2])
    table = evaluate_chips(_pool(), state, chips_available=[], **CFG)
    assert table.empty
    assert list(table.columns) == ["chip", "gw", "gw2", "gain", "per_week"]


def test_chip_plan_highlights_the_best_week_and_the_cost_of_playing_now():
    import pandas as pd

    from gaffer.optimize.chips import chip_plan

    table = pd.DataFrame([
        {"chip": "bboost", "gw": 3, "gain": 4.0, "per_week": 4.0},
        {"chip": "bboost", "gw": 5, "gain": 9.5, "per_week": 9.5},
        {"chip": "3xc", "gw": 3, "gain": 6.0, "per_week": 6.0},
    ])
    plan = {row["chip"]: row for row in chip_plan(table, now_gw=3)}
    bb = plan["bboost"]
    assert bb["best_gw"] == 5 and bb["best_gain"] == 9.5
    assert bb["best_gain_per_week"] == 9.5   # one-week chip: same number
    assert bb["weeks_scored"] == 2
    assert bb["now_gain"] == 4.0
    assert bb["play_now_delta"] == -5.5      # playing now costs 5.5
    assert [w["gw"] for w in bb["weeks"]] == [3, 5]
    tc = plan["3xc"]
    assert tc["best_gw"] == 3 and tc["play_now_delta"] == 0.0


def test_chip_plan_picks_the_wildcard_week_on_points_per_week():
    """A wildcard is credited with every week from the one it is played, so
    the first week of the window always wins on totals. The week that is
    actually best is the best *per week*."""
    import pandas as pd

    from gaffer.optimize.chips import chip_plan

    table = pd.DataFrame([
        # GW3 covers three weeks at 4/wk; GW5 covers one at 9/wk.
        {"chip": "wildcard", "gw": 3, "gain": 12.0, "per_week": 4.0},
        {"chip": "wildcard", "gw": 4, "gain": 10.0, "per_week": 5.0},
        {"chip": "wildcard", "gw": 5, "gain": 9.0, "per_week": 9.0},
    ])
    row = chip_plan(table, now_gw=3)[0]
    assert row["best_gw"] == 5
    assert row["best_gain"] == 9.0 and row["best_gain_per_week"] == 9.0
    assert row["weeks_scored"] == 3
    assert row["now_gain"] == 12.0 and row["play_now_delta"] == 3.0


def test_chip_plan_handles_a_chip_with_no_week_in_the_window():
    import pandas as pd

    from gaffer.optimize.chips import chip_plan

    table = pd.DataFrame([{"chip": "wildcard", "gw": 7, "gain": 2.0,
                           "per_week": 2.0}])
    row = chip_plan(table, now_gw=3)[0]
    assert row["now_gain"] is None and row["play_now_delta"] is None
    assert row["weeks_scored"] == 1


# --- v4c: the wildcard destroys a bank of free transfers -------------------

from dataclasses import replace

from gaffer.optimize.ft_value import LambdaLookup
from tests.test_v4c_degradation import GOLDEN_KW, golden_pool
from tests.test_milp import _owned_state


def test_wildcard_assessment_without_a_lambda_table_is_unchanged():
    """The rail: no priors, no behaviour change."""
    pool = golden_pool()
    state = _owned_state(pool)
    a = wildcard_now_assessment(pool, state, **GOLDEN_KW)
    b = wildcard_now_assessment(pool, state, **GOLDEN_KW, ft_lambda=None)
    assert a == b


def test_an_empty_lambda_table_is_also_unchanged():
    pool = golden_pool()
    state = _owned_state(pool)
    a = wildcard_now_assessment(pool, state, **GOLDEN_KW)
    b = wildcard_now_assessment(pool, state, **GOLDEN_KW,
                                ft_lambda=LambdaLookup({}))
    assert a["gain_over_horizon"] == b["gain_over_horizon"]


def test_the_wildcard_does_not_charge_for_the_banked_transfers():
    """B2. The MILP models a wildcard week as ``ftv <= prev_ft`` — banked
    transfers *survive* the chip (the week itself accruing nothing), which is
    the rule since 2024-25. Deducting
    their lambda value on top of that was charging the manager twice for a
    bank he never loses, and the two halves of the codebase disagreed about
    what a wildcard costs."""
    from dataclasses import replace as dc_replace

    from gaffer.optimize.chips import CHIP_EVAL_DECAY
    from gaffer.optimize.milp import solve_plan

    pool = golden_pool()
    state = replace(_owned_state(pool), free_transfers=5)
    lam = LambdaLookup({(k, t): 1.0 for k in range(1, 6)
                        for t in range(1, 39)})
    cfg = {**GOLDEN_KW, "decay": CHIP_EVAL_DECAY, "ft_lambda": lam}
    base = solve_plan(pool, state, **cfg)
    wc = solve_plan(pool, dc_replace(state, wildcard_gw=state.gws[0]), **cfg)
    priced = wildcard_now_assessment(pool, state, **GOLDEN_KW, ft_lambda=lam)
    assert (priced["gain_over_horizon"]
            == round(wc.objective - base.objective, 2))


def test_a_huge_lambda_table_cannot_talk_the_wildcard_out_of_itself():
    """The old deduction was unbounded in the table, so a big enough lambda
    turned every wildcard off regardless of what the solver said."""
    pool = golden_pool()
    state = replace(_owned_state(pool), free_transfers=5)
    huge = LambdaLookup({(k, t): 100.0 for k in range(1, 6)
                         for t in range(1, 39)})
    plain = wildcard_now_assessment(pool, state, **GOLDEN_KW)
    priced = wildcard_now_assessment(pool, state, **GOLDEN_KW, ft_lambda=huge)
    # 5 banked transfers at lambda 100 was a 400-point deduction under the old
    # code, which turned every wildcard off. Whatever the solver now says, it
    # cannot be hundreds of points below the unpriced answer.
    assert priced["recommend"] == plain["recommend"]
    assert priced["gain_over_horizon"] > plain["gain_over_horizon"] - 10


def test_the_assessment_no_longer_reports_a_bank_deduction():
    """Nothing is deducted, so there is no number to report — a key pinned at
    0.0 would only invite the deduction back."""
    pool = golden_pool()
    state = replace(_owned_state(pool), free_transfers=3)
    lam = LambdaLookup({(k, t): 2.0 for k in range(1, 6)
                        for t in range(1, 39)})
    out = wildcard_now_assessment(pool, state, **GOLDEN_KW, ft_lambda=lam)
    assert "ft_bank_cost" not in out


# --- v4c: theta-aware chip planning ----------------------------------------

from gaffer.optimize.chips import chip_plan


def test_chip_plan_without_thresholds_is_unchanged():
    """Rail: the default argument reproduces today's output exactly."""
    table = pd.DataFrame([
        {"chip": "bboost", "gw": 7, "gain": 6.0, "per_week": 6.0},
        {"chip": "3xc", "gw": 8, "gain": 3.0, "per_week": 3.0}])
    assert chip_plan(table, 7) == chip_plan(table, 7, thresholds=None)


def test_chip_plan_reports_the_threshold_for_the_current_week():
    table = pd.DataFrame([
        {"chip": "bboost", "gw": 7, "gain": 6.0, "per_week": 6.0}])
    out = chip_plan(table, 7, thresholds=lambda chip, gw: 4.5)
    assert out[0]["threshold_now"] == 4.5


def test_chip_plan_says_play_when_the_surplus_clears_the_threshold():
    table = pd.DataFrame([
        {"chip": "bboost", "gw": 7, "gain": 6.0, "per_week": 6.0}])
    out = chip_plan(table, 7, thresholds=lambda chip, gw: 4.5)
    assert out[0]["play_now"] is True


def test_chip_plan_says_wait_when_a_better_week_is_expected():
    """The whole point: a six-point bench boost in GW7 is not enough when
    December is worth twelve."""
    table = pd.DataFrame([
        {"chip": "bboost", "gw": 7, "gain": 6.0, "per_week": 6.0}])
    out = chip_plan(table, 7, thresholds=lambda chip, gw: 12.0)
    assert out[0]["play_now"] is False


def test_chip_plan_at_expiry_plays_on_any_positive_surplus():
    """theta is zero at expiry by construction, so nothing is stranded."""
    table = pd.DataFrame([
        {"chip": "bboost", "gw": 19, "gain": 0.5, "per_week": 0.5}])
    out = chip_plan(table, 19, thresholds=lambda chip, gw: 0.0)
    assert out[0]["play_now"] is True


def test_chip_plan_with_no_row_for_this_week_reports_no_play_decision():
    table = pd.DataFrame([
        {"chip": "bboost", "gw": 9, "gain": 6.0, "per_week": 6.0}])
    out = chip_plan(table, 7, thresholds=lambda chip, gw: 4.0)
    assert out[0]["play_now"] is None
