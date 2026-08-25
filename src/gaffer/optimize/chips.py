"""Chip scenario evaluation.

Every number here is an *objective delta*: re-solve the same horizon with one
chip switched on and subtract the no-chip plan's objective. That keeps chips
comparable with each other and with the plan they would replace, because the
baseline is the plan you would otherwise play, transfers and hits included.

Free hit is the exception: it does not change the plan for later gameweeks
(the squad reverts), so it is scored as a single-gameweek swap rather than by
re-solving the horizon. See :func:`free_hit_gain`.

Those deltas are taken in an *undecayed* frame (``CHIP_EVAL_DECAY``), unlike
the plan the advice actually recommends. The MILP objective discounts
gameweek t by ``decay ** t``, which is the right way to pick transfers you
might revise next week but the wrong way to answer "which week should I play
this chip in?": it made an identical chip played a week later score ~15%
less, and two weeks later ~28% less, for no footballing reason at all — so
every chip's best week was always the current one. Chips are counterfactuals
over a fixed horizon, so they are compared at face value. See
:func:`chip_baseline`.

Chip *eligibility* is the caller's job. In 2026/27 each chip comes in two
halves (the first set expires after GW19) and this module has no notion of
that -- pass only the chips that are actually playable. A horizon can straddle
the boundary, so availability is per gameweek: pass ``avail_by_gw`` when the
two halves differ, or the flat ``chips_available`` list when they do not.
"""

from __future__ import annotations

from dataclasses import replace

import pandas as pd

from gaffer.optimize.milp import (SEASON_LAST_GW, Plan, SolveInput,
                                  solve_plan)

CHIP_EVAL_DECAY = 1.0
"""Time discount used when *scoring* chips: none.

Evaluation-only. The plan ``run_advise`` actually recommends keeps its own
(decayed) solve; this frame exists so that "chip vs no chip over the horizon"
is answered in plain expected points.
"""

WILDCARD_RECOMMEND_THRESHOLD = 8.0
"""Objective points a wildcard must gain before we say "play it".

Deliberately conservative: a wildcard is a scarce, one-shot asset, so a
marginal gain is not a reason to burn it.

Unchanged from when chip gains were decayed, and so slightly more willing to
play the chip now that they are not: the same wildcard clears this bar a
little more often. That is the direction we want — v2 §9 recorded the
standing weakness as firing chips on unlock, and the fix for that is the
per-week comparison below, not a threshold that was only ever holding chips
back by accident.
"""

CHIP_PLAY_THRESHOLD = 4.0
"""Objective points a bench boost, triple captain or free hit must gain
before we play it.

Lower than the wildcard bar because these three are one-week chips: playing
one costs you nothing but the chip itself, whereas a wildcard also throws
away the plan you had.

Also unchanged, and binds against undecayed gains — see the note on
``WILDCARD_RECOMMEND_THRESHOLD``. These are one-week chips played in the
current gameweek, which the decay never discounted directly, so the shift is
small: it comes from the *baseline* now being an undecayed plan (on the
recorded GW2 state, bench boost 4.65 -> 4.98, triple captain unchanged).
"""


def chip_baseline(pool: pd.DataFrame, state: SolveInput, **cfg) -> Plan:
    """The no-chip plan every chip is scored against, solved undecayed.

    Callers that want both :func:`evaluate_chips` and
    :func:`wildcard_now_assessment` can solve this once and pass it as
    ``base`` to each. It is *not* the plan the advice recommends: that one is
    solved with the configured decay and lives in ``run_advise``.
    """
    return solve_plan(pool, state, **_eval_cfg(cfg))


def _eval_cfg(cfg: dict) -> dict:
    """``cfg`` with the time discount switched off (see the module note)."""
    return {**cfg, "decay": CHIP_EVAL_DECAY}


def _weeks_covered(chip: str, gw: int, gws: list[int]) -> int:
    """Horizon gameweeks a chip played in ``gw`` is credited with.

    A wildcard rebuilds the squad for the rest of the horizon, so a window of
    six weeks gives a GW1 wildcard six weeks of credit and a GW6 wildcard
    one. Comparing those totals is how "play it now" won by default; dividing
    by this makes the weeks comparable. The other three chips are one-week
    chips and score one week wherever they land.
    """
    if chip != "wildcard":
        return 1
    return sum(1 for g in gws if g >= gw)


def evaluate_chips(pool: pd.DataFrame, state: SolveInput,
                   chips_available: list[str] | None = None,
                   base: Plan | None = None,
                   avail_by_gw: dict[int, list[str]] | None = None,
                   **cfg) -> pd.DataFrame:
    """Objective delta of playing each available chip in each horizon GW vs the
    no-chip plan. Chips: wildcard, bboost, 3xc (freehit separately below).
    Returns [chip, gw, gain, per_week] sorted by gain desc.

    Every solve here is undecayed (see the module note), so ``gain`` is
    expected points over the horizon rather than a discounted objective.

    ``per_week`` is ``gain`` divided by the horizon weeks the chip is credited
    with — one for the one-week chips, and for a wildcard the weeks from
    ``gw`` to the end of the window. Compare wildcard weeks on ``per_week``:
    the totals are not comparable, because a later week simply has less
    horizon left to be credited with.

    ``base`` is the already-solved no-chip plan and must come from
    :func:`chip_baseline`, not from the caller's own decayed solve; pass it to
    skip re-solving.

    Availability comes either as a flat ``chips_available`` list applied to
    every gameweek, or -- when the horizon crosses the GW19/20 chip-set
    boundary and the two halves differ -- as ``avail_by_gw``, a gameweek ->
    chips mapping. ``avail_by_gw`` wins when both are given; a gameweek missing
    from it has no chips available.
    """
    cfg = _eval_cfg(cfg)
    if base is None:
        base = solve_plan(pool, state, **cfg)

    def available(gw: int) -> list[str]:
        if avail_by_gw is not None:
            return avail_by_gw.get(gw, [])
        return chips_available or []

    rows = []

    def add(chip: str, gw: int, gain: float) -> None:
        weeks = _weeks_covered(chip, gw, state.gws)
        rows.append({"chip": chip, "gw": gw, "gain": gain,
                     "per_week": gain / weeks})

    for gw in state.gws:
        chips = available(gw)
        if "wildcard" in chips:
            p = solve_plan(pool, replace(state, wildcard_gw=gw), **cfg)
            add("wildcard", gw, p.objective - base.objective)
        if "bboost" in chips:
            p = solve_plan(pool, replace(state, bench_boost_gw=gw), **cfg)
            add("bboost", gw, p.objective - base.objective)
        if "3xc" in chips:
            p = solve_plan(pool, replace(state, triple_captain_gw=gw), **cfg)
            add("3xc", gw, p.objective - base.objective)
    for gw in state.gws:
        if "freehit" in available(gw):
            add("freehit", gw,
                free_hit_gain(pool, state, gw, base=base, **cfg))
    if not rows:
        # Every chip spent is a normal late-season state; hand back the empty
        # frame rather than letting the column-less DataFrame blow up below.
        return pd.DataFrame(columns=["chip", "gw", "gain", "per_week"])
    return (pd.DataFrame(rows)
            .assign(gain=lambda d: d["gain"].round(2),
                    per_week=lambda d: d["per_week"].round(2))
            .sort_values("gain", ascending=False).reset_index(drop=True))


def free_hit_gain(pool: pd.DataFrame, state: SolveInput, gw: int,
                  base: Plan | None = None, **cfg) -> float:
    """FH ≈ (best unrestricted single-GW squad, budget = sell value of current
    squad + bank) minus the baseline plan's EP in that GW. Squad reverts after,
    so other GWs are unchanged — a documented approximation.

    ``base`` is the already-solved no-chip plan and must come from
    :func:`chip_baseline`; pass it to skip re-solving. Both solves are
    undecayed (see the module note) — the free hit is a one-week swap, so the
    discount only ever shrank a later week's chip against an earlier one.

    Two things this deliberately ignores, both of which make the number a
    *lower* bound on the chip's real value:

    * the hits the baseline paid to reach that gameweek's XI (``expected_pts``
      is gross of hit cost), so if the baseline bought its way to a good week,
      free hit looks worth nothing when it actually saved you the hits;
    * the fact that free hit leaves your transfers and bank untouched for the
      rest of the horizon.
    """
    cfg = _eval_cfg(cfg)
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

    Undecayed like the rest of this module (see the module note), so
    ``gain_over_horizon`` really is expected points over the whole window.

    ``base`` is the already-solved no-chip plan and must come from
    :func:`chip_baseline`; pass it to skip re-solving.
    """
    cfg = _eval_cfg(cfg)
    if base is None:
        base = solve_plan(pool, state, **cfg)
    wc = solve_plan(pool, replace(state, wildcard_gw=state.gws[0]), **cfg)
    # No deduction for the banked free transfers. A wildcard does not reset
    # the bank — it has not since 2024-25 — and ``milp`` models that directly
    # (``ftv[t] <= prev_ft + 1`` on a wildcard week), so the lambda value of
    # the bank is already inside ``wc.objective``. Subtracting it again here
    # charged the manager twice for transfers he keeps, and left the two
    # halves of the codebase disagreeing about what a wildcard costs.
    gain = wc.objective - base.objective
    return {"gain_over_horizon": round(gain, 2),
            "wc_squad": wc.gw_plans[0].squad,
            "recommend": gain > WILDCARD_RECOMMEND_THRESHOLD}


def chip_plan(table: pd.DataFrame, now_gw: int, thresholds=None) -> list[dict]:
    """Fold the chip x gameweek table into one row per chip (spec §3.7).

    ``evaluate_chips`` already enumerates every playable chip in every
    gameweek of the horizon, so nothing new is solved here — this only picks
    the best week out and prices the impatience of playing on unlock, which
    v2 §9 recorded as the standing weakness.

    The best week is the best ``per_week`` week, not the best total. For the
    one-week chips those agree. For a wildcard they do not: it is credited
    with every horizon week from the week it is played onwards, so the first
    week of the window is scored over more weeks than the last and wins on
    totals almost regardless of the fixtures. ``weeks_scored`` is how many
    weeks were looked at, so the UI can say how far ahead "best" reaches.

    ``now_gain`` and ``play_now_delta`` are ``None`` when the chip is not
    playable in ``now_gw`` at all; there is no "cost of playing now" for a
    chip you cannot play now. ``play_now_delta`` stays a total-vs-total
    comparison: it is the price of this decision, not a rate.
    """
    out = []
    for chip, rows in table.groupby("chip", sort=False):
        weeks = [{"gw": int(r.gw), "gain": float(r.gain),
                  "per_week": float(r.per_week)}
                 for r in rows.sort_values("gw").itertuples()]
        best = max(weeks, key=lambda w: w["per_week"])
        now = next((w["gain"] for w in weeks if w["gw"] == now_gw), None)
        now_gain = None if now is None else round(now, 2)
        entry = {
            "chip": str(chip), "weeks": weeks, "best_gw": best["gw"],
            "best_gain": round(best["gain"], 2),
            "best_gain_per_week": round(best["per_week"], 2),
            "weeks_scored": len(weeks),
            "now_gain": now_gain,
            "play_now_delta": None if now is None
            else round(now - best["gain"], 2)}
        # theta_t: the surplus the best remaining week is expected to offer.
        # Playing now is only right when this week beats waiting — a flat bar
        # cannot express that, which is why a five-point bench boost in
        # September used to get burned three months early.
        theta = None if thresholds is None else float(thresholds(chip, now_gw))
        play_now = None
        if theta is not None and now_gain is not None:
            play_now = bool(now_gain >= theta)
        entry["threshold_now"] = theta
        entry["play_now"] = play_now
        out.append(entry)
    return sorted(out, key=lambda row: -row["best_gain"])
