"""Chip scenario evaluation.

Every number here is an *objective delta*: re-solve the same horizon with one
chip switched on and subtract the no-chip plan's objective. That keeps chips
comparable with each other and with the plan they would replace, because the
baseline is the plan you would otherwise play, transfers and hits included.

Free hit is the exception: it does not change the plan for later gameweeks
(the squad reverts), so it is scored as a single-gameweek swap rather than by
re-solving the horizon. See :func:`free_hit_gain`.

Chip *eligibility* is the caller's job. In 2026/27 each chip comes in two
halves (the first set expires after GW19) and this module has no notion of
that -- pass only the chips that are actually playable. A horizon can straddle
the boundary, so availability is per gameweek: pass ``avail_by_gw`` when the
two halves differ, or the flat ``chips_available`` list when they do not.
"""

from __future__ import annotations

from dataclasses import replace

import pandas as pd

from gaffer.optimize.milp import Plan, SolveInput, solve_plan

WILDCARD_RECOMMEND_THRESHOLD = 8.0
"""Objective points a wildcard must gain before we say "play it".

Deliberately conservative: a wildcard is a scarce, one-shot asset, so a
marginal gain is not a reason to burn it.
"""

CHIP_PLAY_THRESHOLD = 4.0
"""Objective points a bench boost, triple captain or free hit must gain
before we play it.

Lower than the wildcard bar because these three are one-week chips: playing
one costs you nothing but the chip itself, whereas a wildcard also throws
away the plan you had.
"""


def evaluate_chips(pool: pd.DataFrame, state: SolveInput,
                   chips_available: list[str] | None = None,
                   base: Plan | None = None,
                   avail_by_gw: dict[int, list[str]] | None = None,
                   **cfg) -> pd.DataFrame:
    """Objective delta of playing each available chip in each horizon GW vs the
    no-chip plan. Chips: wildcard, bboost, 3xc (freehit separately below).
    Returns [chip, gw, gain] sorted by gain desc.

    ``base`` is the already-solved no-chip plan; pass it to skip re-solving.

    Availability comes either as a flat ``chips_available`` list applied to
    every gameweek, or -- when the horizon crosses the GW19/20 chip-set
    boundary and the two halves differ -- as ``avail_by_gw``, a gameweek ->
    chips mapping. ``avail_by_gw`` wins when both are given; a gameweek missing
    from it has no chips available.
    """
    if base is None:
        base = solve_plan(pool, state, **cfg)

    def available(gw: int) -> list[str]:
        if avail_by_gw is not None:
            return avail_by_gw.get(gw, [])
        return chips_available or []

    rows = []
    for gw in state.gws:
        chips = available(gw)
        if "wildcard" in chips:
            p = solve_plan(pool, replace(state, wildcard_gw=gw), **cfg)
            rows.append({"chip": "wildcard", "gw": gw,
                         "gain": p.objective - base.objective})
        if "bboost" in chips:
            p = solve_plan(pool, replace(state, bench_boost_gw=gw), **cfg)
            rows.append({"chip": "bboost", "gw": gw,
                         "gain": p.objective - base.objective})
        if "3xc" in chips:
            p = solve_plan(pool, replace(state, triple_captain_gw=gw), **cfg)
            rows.append({"chip": "3xc", "gw": gw,
                         "gain": p.objective - base.objective})
    for gw in state.gws:
        if "freehit" in available(gw):
            rows.append({"chip": "freehit", "gw": gw,
                         "gain": free_hit_gain(pool, state, gw, base=base,
                                               **cfg)})
    return (pd.DataFrame(rows)
            .assign(gain=lambda d: d["gain"].round(2))
            .sort_values("gain", ascending=False).reset_index(drop=True))


def free_hit_gain(pool: pd.DataFrame, state: SolveInput, gw: int,
                  base: Plan | None = None, **cfg) -> float:
    """FH ≈ (best unrestricted single-GW squad, budget = sell value of current
    squad + bank) minus the baseline plan's EP in that GW. Squad reverts after,
    so other GWs are unchanged — a documented approximation.

    ``base`` is the already-solved no-chip plan; pass it to skip re-solving.

    Two things this deliberately ignores, both of which make the number a
    *lower* bound on the chip's real value:

    * the hits the baseline paid to reach that gameweek's XI (``expected_pts``
      is gross of hit cost), so if the baseline bought its way to a good week,
      free hit looks worth nothing when it actually saved you the hits;
    * the fact that free hit leaves your transfers and bank untouched for the
      rest of the horizon.
    """
    if base is None:
        base = solve_plan(pool, state, **cfg)
    base_gw_ep = next(g.expected_pts for g in base.gw_plans if g.gw == gw)
    budget = state.bank + int(
        pool[pool["code"].isin(state.owned_codes)]["sell"].sum())
    # free_transfers=15 just means "no transfer counts as a hit" when building
    # the squad from scratch; the FH squad is not bought, it is conjured.
    fh_state = SolveInput(owned_codes=[], bank=budget, free_transfers=15,
                          gws=[gw], locked_out=list(state.locked_out))
    fh = solve_plan(pool, fh_state, **cfg)
    return fh.gw_plans[0].expected_pts - base_gw_ep


def wildcard_now_assessment(pool: pd.DataFrame, state: SolveInput,
                            base: Plan | None = None, **cfg) -> dict:
    """The user's 'should I wildcard after bad GW1?' number.

    ``base`` is the already-solved no-chip plan; pass it to skip re-solving.
    """
    if base is None:
        base = solve_plan(pool, state, **cfg)
    wc = solve_plan(pool, replace(state, wildcard_gw=state.gws[0]), **cfg)
    gain = wc.objective - base.objective
    return {"gain_over_horizon": round(gain, 2),
            "wc_squad": wc.gw_plans[0].squad,
            "recommend": gain > WILDCARD_RECOMMEND_THRESHOLD}
