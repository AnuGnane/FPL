"""Chip scenario evaluation.

Every number here is an *objective delta*: re-solve the same horizon with one
chip switched on and subtract the no-chip plan's objective. That keeps chips
comparable with each other and with the plan they would replace, because the
baseline is the plan you would otherwise play, transfers and hits included.

Free hit is the exception: it does not change the plan for later gameweeks
(the squad reverts), so it is scored as a single-gameweek swap rather than by
re-solving the horizon. Since v12 that swap is priced from the *baseline's*
position in the week the chip is played — its squad, its bank, its saved hits
— rather than from today's. See :func:`free_hit_gain`.

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

from gaffer.optimize.chip_policy import threshold_with_source
from gaffer.optimize.milp import (SEASON_LAST_GW, Plan, SolveInput,
                                  solve_plan)

NO_THRESHOLDS = "flat: the caller passed no threshold lookup"
"""Why a bar is flat when the *caller* is the reason. Distinct from
``chip_policy.FLAT_SOURCE``, which is "there is no asset": a caller that never
offered θ and an asset that does not exist are different bugs."""

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

# v12 W3 §4.5 (specs/2026-09-01-gaffer-v12-program-design.md)
PAIR_CHIP = "wildcard+bboost"
"""The one chip *pair* this module evaluates: a wildcard in one week and a
bench boost in a later one, scored as a single option.

Named rather than composed, because everything downstream keys on the chip
string: the workbench row, the UI's label table, the ledger. A name with a
``+`` in it is deliberately not a two-letter code — there is no What-If code
for a pair, and ``ChipsTab``'s mapping already leaves an unknown row alone
rather than re-solving it as no chip at all.
"""

PAIR_DGW_MIN_PROB = 0.5
"""How likely a double gameweek must be before a pair is evaluated for it.

``data/chip_scenarios.toml`` carries probabilities, and today's writer only
ever writes ``1.0`` — a double in the published fixture list, not a guess. The
bar exists for the day the file carries projections: a bench boost planned
around a 30%-likely double is a plan around a rumour, and the extra solves it
costs are spent on every wildcard week in the horizon.
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

    v12 W3 §4.5: a pair carrying a wildcard is credited the wildcard's weeks —
    the bench boost inside it is still a one-week chip, but the squad rebuild
    that dominates the option's value runs to the end of the window exactly as
    a lone wildcard's does.
    """
    if not chip.startswith("wildcard"):
        return 1
    return sum(1 for g in gws if g >= gw)


def evaluate_chips(pool: pd.DataFrame, state: SolveInput,
                   chips_available: list[str] | None = None,
                   base: Plan | None = None,
                   avail_by_gw: dict[int, list[str]] | None = None,
                   dgw_gws: set[int] | None = None,
                   **cfg) -> pd.DataFrame:
    """Objective delta of playing each available chip in each horizon GW vs the
    no-chip plan. Chips: wildcard, bboost, 3xc (freehit separately below).
    Returns [chip, gw, gw2, gain, per_week] sorted by gain desc.

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

    ``dgw_gws`` (v12 W3 §4.5) are the horizon gameweeks believed to be doubles.
    Given a non-empty set, the table also carries the wildcard-plus-bench-boost
    *pair*: a wildcard in ``g`` and a bench boost in a later ``g2`` that is one
    of them, scored as one option against the same no-chip baseline, with
    ``gw`` the wildcard's week and ``gw2`` the boost's. Omitted — which is
    every caller but ``advise`` — the table is exactly the table it was, and
    that is not a convenience: ``backtest``'s chip executor has no branch for a
    pair, so a pair row reaching it would be recorded as played and applied to
    nothing.
    """
    cfg = _eval_cfg(cfg)
    if base is None:
        base = solve_plan(pool, state, **cfg)

    def available(gw: int) -> list[str]:
        if avail_by_gw is not None:
            return avail_by_gw.get(gw, [])
        return chips_available or []

    rows = []

    def add(chip: str, gw: int, gain: float, gw2: int | None = None) -> None:
        weeks = _weeks_covered(chip, gw, state.gws)
        rows.append({"chip": chip, "gw": gw, "gw2": gw2, "gain": gain,
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
    # v12 W3 §4.5 (specs/2026-09-01-gaffer-v12-program-design.md): the pair.
    # Only into a believed double, and only forward — a bench boost in the
    # wildcard's own week is not playable (one chip per gameweek), and a boost
    # before the rebuild is just a bench boost. Bounded by the doubles in the
    # horizon rather than by the horizon squared.
    for g in state.gws:
        if not dgw_gws or "wildcard" not in available(g):
            continue
        for g2 in state.gws:
            if g2 <= g or int(g2) not in dgw_gws:
                continue
            if "bboost" not in available(g2):
                continue
            p = solve_plan(pool, replace(state, wildcard_gw=g,
                                         bench_boost_gw=g2), **cfg)
            add(PAIR_CHIP, g, p.objective - base.objective, gw2=g2)
    if not rows:
        # Every chip spent is a normal late-season state; hand back the empty
        # frame rather than letting the column-less DataFrame blow up below.
        return pd.DataFrame(columns=["chip", "gw", "gw2", "gain", "per_week"])
    frame = pd.DataFrame(rows)
    # ``gw2`` is None on every ordinary row, and pandas turns a column of
    # None-and-int into float64 with NaN — which pydantic's ``int | None`` then
    # refuses, and which json.dumps writes as a bare NaN. Held as an object
    # column so a None stays a None.
    frame["gw2"] = frame["gw2"].astype("object").where(frame["gw2"].notna(),
                                                       None)
    return (frame
            .assign(gain=lambda d: d["gain"].round(2),
                    per_week=lambda d: d["per_week"].round(2))
            .sort_values("gain", ascending=False).reset_index(drop=True))


def free_hit_gain(pool: pd.DataFrame, state: SolveInput, gw: int,
                  base: Plan | None = None, **cfg) -> float:
    """The best unrestricted one-week squad in ``gw``, against the plan you
    would otherwise have played that week.

    ``base`` is the already-solved no-chip plan and must come from
    :func:`chip_baseline`; pass it to skip re-solving. Both solves are
    undecayed (see the module note) — the free hit is a one-week swap, so the
    discount only ever shrank a later week's chip against an earlier one.

    **v12 W3 §4.5 (specs/2026-09-01-gaffer-v12-program-design.md).** Two of the
    three understatements this function used to carry are gone:

    * the budget is the baseline's squad and bank *in that week*, not today's.
      Pricing a GW+3 free hit off a squad the plan has already sold out of was
      answering a question about a different team;
    * the baseline's hits in that week are credited back. A free hit suspends
      the week's transfers, so the points those transfers would have cost are
      saved by playing the chip — and ``expected_pts`` is gross of hit cost,
      so leaving them in made the chip look worth nothing exactly when it had
      just saved a -8.

    The third stays, and stays documented: a free hit also leaves your
    transfers and bank untouched for the rest of the horizon, which this
    number does not price. Doing so needs a two-branch horizon solve, and the
    spec asks for a true re-solve of the free hit *week*.

    A baseline whose week carries no readable bank — an older ``Plan``, a
    solver that returned no value — falls back to today's squad and bank,
    which is exactly the pre-v12 number, and says so on stdout rather than
    silently pricing a chip off a position nobody chose.
    """
    cfg = _eval_cfg(cfg)
    if base is None:
        base = solve_plan(pool, state, **cfg)
    base_week = next(g for g in base.gw_plans if g.gw == gw)
    hit_cost = int(cfg.get("hit_cost", 4))
    squad, bank = list(base_week.squad), base_week.bank
    if bank is None:
        print(f"free_hit_gain: the baseline plan carries no bank for GW{gw}; "
              f"pricing the chip off today's squad instead")
        squad, bank = list(state.owned_codes), float(state.bank)
    sell = dict(zip(pool["code"], pool["sell"]))
    budget = int(round(float(bank)
                       + sum(float(sell.get(c, 0.0)) for c in squad)))
    # free_transfers=15 just means "no transfer counts as a hit" when building
    # the squad from scratch; the FH squad is not bought, it is conjured.
    fh_state = SolveInput(owned_codes=[], bank=budget, free_transfers=15,
                          gws=[gw], locked_out=list(state.locked_out))
    fh = solve_plan(pool, fh_state, **cfg)
    baseline_week_net = base_week.expected_pts - hit_cost * base_week.hits
    return fh.gw_plans[0].expected_pts - baseline_week_net


def wildcard_now_assessment(pool: pd.DataFrame, state: SolveInput,
                            base: Plan | None = None,
                            thresholds=None, **cfg) -> dict:
    """The user's 'should I wildcard after bad GW1?' number.

    Undecayed like the rest of this module (see the module note), so
    ``gain_over_horizon`` really is expected points over the whole window.

    ``base`` is the already-solved no-chip plan and must come from
    :func:`chip_baseline`; pass it to skip re-solving.

    ``thresholds`` is the ``(chip, gw) -> theta`` lookup the caller already
    built (v12 W3 §4.2, specs/2026-09-01-gaffer-v12-program-design.md).
    Without it the bar is :data:`WILDCARD_RECOMMEND_THRESHOLD`, which is what
    this function used unconditionally until v12 — in the same advise run that
    computed θ for the wildcard and printed it on the chip row three lines
    earlier. Two answers to one question, on one page, from one run.

    The comparison is ``>=`` on the θ path and ``>`` on the flat one, and the
    asymmetry is deliberate: ``>=`` is the rule ``chip_plan`` and ``advise``
    already apply to every other chip against θ, and ``>`` is the shipped
    verdict of the flat path, which this cycle has no measurement to move.
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
    # v12 W3 §4.2 (specs/2026-09-01-gaffer-v12-program-design.md).
    if thresholds is None:
        bar, source = float(WILDCARD_RECOMMEND_THRESHOLD), NO_THRESHOLDS
        recommend = gain > bar
    else:
        bar, source = threshold_with_source(thresholds, "wildcard",
                                            int(state.gws[0]))
        recommend = gain >= bar
    return {"gain_over_horizon": round(gain, 2),
            "wc_squad": wc.gw_plans[0].squad,
            "recommend": recommend,
            "threshold": round(bar, 2),
            "threshold_source": source}


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
