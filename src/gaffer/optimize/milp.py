"""Multi-period MILP for FPL squad planning.

Decides, jointly over a horizon of gameweeks: the 15-man squad, the starting
XI, captain/vice, and the transfers (with free-transfer banking and points
hits) that link one gameweek's squad to the next.

Two modelling caveats callers should know about:

* ``hits`` and ``ftv`` are bounded rather than pinned to an exact min/max,
  which is only equivalent to the FPL rules while a hit costs more than a
  banked free transfer is worth, i.e. while
  ``ft_value < hit_cost * decay ** (len(gws) - 1)``. The defaults
  (1.5 < 4 * 0.85**5 = 1.775) satisfy this with room to spare.
* ``locked_out`` removes players from the pool outright, so it is meant for
  players you do *not* own. Locking out an owned player makes them vanish
  from the squad without generating sale proceeds.
* ``force_out`` is the other half of that: the player stays in the pool, so
  squad continuity turns his ownership into a sale in the first horizon
  gameweek and the bank receives his sell price. "I am selling him" and "he
  may not be bought" are different instructions and this module now has both.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import pulp

from gaffer.errors import GafferError
from gaffer.optimize.ft_value import LambdaLookup

SQUAD_COMPOSITION = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
XI_BOUNDS = {"GKP": (1, 1), "DEF": (3, 5), "MID": (2, 5), "FWD": (1, 3)}
MAX_PER_CLUB = 3
MAX_FREE_TRANSFERS = 5

SEASON_LAST_GW = 38
"""Last gameweek of a season.

Needed here rather than imported from ``advise`` so the objective can price a
banked transfer by how many weeks are left to spend it in. A duplicate of
``advise.LAST_GW`` on purpose: ``milp`` must not import ``advise``.
"""

DEFAULT_BENCH_CURVE = [0.21, 0.06, 0.002]
"""Autosub-weighted bench values for the 1st, 2nd and 3rd outfield sub.

Uniform 0.10 says the third substitute is as likely to earn you points as the
first, which is not close to true: the first bench outfielder comes on
regularly, the third essentially never. The bench goalkeeper rides on the
first weight — he plays exactly when your starting keeper does not, which is
about as often as the first outfield sub appears.

Not the default in ``config.toml``: Gate D2 measures it first.
"""

BENCH_SLOTS = 3
"""Outfield bench slots. The fourth bench player is the reserve keeper, who is
priced by the first curve weight rather than by a slot of his own."""

# v10 §F1a (specs/2026-09-01-gaffer-v10-minutes-design.md): the three
# constants the autosub weighting is expressed in.
POPULATION_DNP = 0.0617
"""Mean ``1 - p_play`` over a typical starting XI, on the 2024-25 benchmark.

§F1a's denominator, and the reason its weighting is a *modulation* of
:data:`DEFAULT_BENCH_CURVE` rather than a replacement for it: an XI as fragile
as the league's average produces a frailty of exactly 1.0 and therefore today's
curve, unchanged. The curve stays the calibrated population base; ``p_play``
only says how far this week's XI sits from the population it was fitted on.

Measured by ``scripts/v10_dnp.py`` (plan A3): per gameweek of the benchmark
test season, the positionally-legal eleven with the highest EP out of the
:data:`DEFAULT_TOP_N` pool, ``mean(1 - p_play)`` over those slots, averaged
over 38 gameweeks. Per-gameweek range: 0.0389-0.2045, the maximum being GW1,
where the model has no current-season form to read and is uncertain about
everyone.

The same run measured the keeper-only rate: :data:`KEEPER_DNP`, 0.0486. It is
its own constant rather than a rounding of this one. The two differ by 1.3
points of probability, which sounds small and is not: they are *divisors*. A
population-typical keeper divided by this constant instead of his own gives
0.0486 / 0.0617 = 0.79 — the bench keeper's whole weight, 21% low, every week,
in one direction. "A fifth of a point of probability" was the wrong reading of
the same two numbers and is what this paragraph replaces.
"""

KEEPER_DNP = 0.0486
"""Mean ``1 - p_play`` for the *starting keeper*, on the same benchmark run.

:data:`POPULATION_DNP`'s divisor is the XI's mean, and the reserve keeper does
not cover the XI: he plays exactly when one man does not. His weight therefore
reads that one man's frailty (``_decision_scales``), and a frailty is only 1.0
at the population it was measured on — so the population here is keepers.

Keepers are the most nailed-on position on the pitch, which is why the rate is
lower than the eleven's. Over the same 38 gameweeks and the same
``scripts/v10_dnp.py`` run: 0.0486.
"""

FRAILTY_CLAMP = (0.25, 2.0)
"""Bounds on every ``/ POPULATION_DNP`` ratio in §F1 (plan A4).

The floor defends against a nailed-on XI. Eleven players at 0.98 give a
frailty near zero, and a bench worth nothing is a bench the solver fills with
the cheapest legal bodies to free money for the XI — a real strategy, and not
the one §F1a is asking for. 0.25 keeps the curve's shape alive while still
saying this XI barely needs cover.

The ceiling defends against the opposite: a doubt-riddled XI at frailty 4
would price the bench like a permanent bench boost. 2.0 — twice as fragile as
the league — is already an aggressive claim.

On the measured data neither bound binds in an ordinary week: the benchmark's
per-gameweek range gives frailties of 0.63 to 3.31, so only GW1's cold start
reaches the ceiling. A clamp that bound every week would be a clamp doing the
deciding, and this one is not.
"""

P_PLAY_MIN_SPREAD = 1e-9
"""Below this spread *within a gameweek*, §F1 does not run.

Per gameweek, and not pooled over the horizon: see ``_p_play_lookup``. One
constant per week is still one constant, and pooling would read the gap
between two of them as information.

The whole of §F1 is *relative*: which of two benched players comes on first,
how this XI compares to the population, how likely the captain is to leave the
armband unused. A column with no variance in it answers none of those and, fed
through the arithmetic anyway, would shift the bench block against the XI block
by a constant nobody chose. So an absent ``p_play`` and a uniform ``p_play``
take the same path — the pre-v10 one, byte for byte (plan A2).
"""

DEFAULT_TOP_N = {"GKP": 8, "DEF": 22, "MID": 26, "FWD": 14}


@dataclass
class SolveInput:
    owned_codes: list[int]
    bank: int                    # 0.1m units
    free_transfers: int
    gws: list[int]               # planning horizon, e.g. [3,4,5,6,7,8]
    wildcard_gw: int | None = None
    bench_boost_gw: int | None = None
    triple_captain_gw: int | None = None
    locked_out: list[int] = field(default_factory=list)   # codes banned
    # What-if constraints (spec §3.2). All three default to "no constraint",
    # so an unconstrained solve is bit-identical to the pre-v3 one.
    locked_in: list[int] = field(default_factory=list)
    """Codes that must be in the squad in every gameweek of the horizon."""
    force_in_gw: list[int] = field(default_factory=list)
    """Codes that must be transferred in during the *first* gameweek."""
    max_hits: int | None = None
    """Upper bound on hits per gameweek. ``None`` leaves it to the objective.

    Never applied to a wildcard week, where hits are free by the rules.
    """
    # v12 W3 §4.1 (specs/2026-09-01-gaffer-v12-program-design.md)
    force_out: list[int] = field(default_factory=list)
    """Codes that must not be in the squad in any gameweek of the horizon.

    Distinct from :attr:`locked_out`, which deletes the player from the pool
    and so makes an owned player disappear without sale proceeds (module
    note). A forced-out player stays in the pool, so the continuity
    constraint spends his ownership as a transfer out in the first gameweek
    and the budget row receives his ``sell`` price.

    Appended last, and defaulted, so every positional construction of this
    dataclass in the tree still builds — and so an empty list adds not one
    constraint to the model. ``tests/data/v12_w3_milp_golden.lp`` pins that.
    """


@dataclass
class GwPlan:
    gw: int
    squad: list[int]
    xi: list[int]
    xi_rows: list[dict]
    bench: list[int]
    captain: int
    vice: int
    buys: list[int]
    sells: list[int]
    hits: int
    expected_pts: float
    # v12 W3 §4.5 (specs/2026-09-01-gaffer-v12-program-design.md)
    bank: float | None = None
    """Money left after this gameweek's transfers, in 0.1m units.

    The MILP has always solved for it and always thrown it away, which is why
    a chip priced three weeks out had to be priced off *today's* bank. ``None``
    when the solver returned no value for the variable — a state believed
    unreachable on an optimal solve, kept because a caller that reads 0.0 as
    "no money" would price a free hit off nothing at all.
    """


@dataclass
class Plan:
    objective: float
    gw_plans: list[GwPlan]
    # v12 W3 §4.3 (specs/2026-09-01-gaffer-v12-program-design.md). Both
    # defaulted, so every construction in the tree — and every ``Plan`` a
    # scenario sweep builds — is the object it was.
    gap: float | None = None
    """Objective points this plan sits behind the one it is an alternative to.

    **Signed, and the sign matters.** The recommended plan is
    ``policy.coherent_plan``'s, which carries the sweep's moves as
    ``FixedMoves``; an alternative is solved without them and can therefore
    score *above* it, giving a negative gap. That is the price of the
    coherence constraint, and it is the number a reader deciding whether to
    override the sweep wants to see.

    An **objective** gap, not an EP one: ``objective`` is decayed by week,
    carries the bench curve and the vice hedge, and prices banked transfers
    and the bank itself. Re-scoring the alternatives in raw EP would compare
    two plans on a quantity neither was chosen by. ``None`` on any plan that
    is not somebody's alternative.
    """
    alternatives: list["Plan"] = field(default_factory=list)
    """Distinct plans behind this one, best first. Each carries its own
    ``gap``; this list is always empty on them (one level, not a tree)."""


ALT_PLAN_MAX = 3
"""Plans in the set, counting the incumbent (spec §4.3's "top-3").

A constant rather than a config key because the cost is a solve each and the
knob the spec exposes is the gap, which is the one that answers "is this
alternative worth reading". Three is also as many tabs as a board column can
carry without becoming a menu.
"""


def move_set(plan: "Plan") -> list[tuple[str, int, int]]:
    """The transfers a plan makes, as ``(direction, code, gameweek)``.

    Sorted, so a cut built from it is stable across runs and two identical
    plans produce identical cuts. Buys and sells are listed separately rather
    than paired: the MILP never pairs them — a week's ``buys`` and ``sells``
    are two lists whose only relationship is the budget row — so pairing them
    here would be inventing a structure to exclude.

    v12 W3 §4.3 (specs/2026-09-01-gaffer-v12-program-design.md).
    """
    return sorted(
        [("in", int(c), int(gp.gw)) for gp in plan.gw_plans for c in gp.buys]
        + [("out", int(c), int(gp.gw)) for gp in plan.gw_plans
           for c in gp.sells])


@dataclass
class FixedMoves:
    """Transfers the caller has already decided on.

    The scenario policy (``optimize/policy.py``) picks a set of moves by how
    often they survive noise, then needs a *coherent* plan built around
    exactly those moves — a recommended buy with no recommended sell is not a
    plan anyone can execute. Rather than assembling one by hand and hoping it
    is legal, it hands the moves back to the MILP as constraints and lets the
    solver fill in the XI, the captain and the bank.

    ``gw`` defaults to the first horizon week, which is the only week the
    policy ever gates. ``no_transfer`` is the "hold and roll the FT" branch:
    it pins *this* week shut and leaves the rest of the horizon free, because
    holding this week says nothing about next week.
    """
    buys: list[int] = field(default_factory=list)
    sells: list[int] = field(default_factory=list)
    gw: int | None = None
    no_transfer: bool = False


# v10 §F1a (specs/2026-09-01-gaffer-v10-minutes-design.md): the arithmetic the
# two-pass solve is built out of. All three are private and none is reachable
# from a caller that passes no p_play.
def _frailty(dnp_rate: float, population: float = POPULATION_DNP) -> float:
    """A did-not-play rate -> a clamped multiplier on a population weight.

    ``population`` is the rate the multiplier is 1.0 at. It is the XI's for
    every slot the XI covers and :data:`KEEPER_DNP` for the reserve keeper,
    who covers one man and must be typical against the population that man
    belongs to.
    """
    lo, hi = FRAILTY_CLAMP
    return min(max(dnp_rate / population, lo), hi)


def _is_blank(ep: object, gw: int) -> bool:
    """Does this player's ``ep`` mapping price him in this gameweek at all?

    Two spellings of the same fact, because there are two: ``ep_matrix``
    leaves a blank gameweek out of the mapping, and :func:`build_pool` then
    materialises the hole as ``0.0`` when it fills the horizon. A pair worth
    nothing carries no weight into either pass of §F1a — the bench key is
    ``ep × p_play`` and the frailty is an average over the XI — so both
    spellings are treated as "no fixture" and neither is coverage.
    """
    if not isinstance(ep, dict):
        return False        # an unrecognised pool: judge nothing a blank
    v = ep.get(gw)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return True
    return not float(v) > 0.0


def _p_play_lookup(pool: pd.DataFrame, state: SolveInput,
                   p_play: dict | None) -> dict[int, dict[int, float]] | None:
    """The §F1 gate: a usable ``{code: {gw: p}}``, or ``None`` for "don't".

    ``None`` — and therefore the pre-v10 solve, exactly — in three cases, and
    plan A2 is why each of them is a case:

    * nothing was passed, which is every caller in the tree today;
    * **coverage is incomplete** — some ``(code, gw)`` the pool *prices* is
      missing from ``p_play``, or is not a finite number in ``[0, 1]``.
      All-or-nothing on purpose: a pool where half the players have a
      probability and the other half are silently treated as nailed-on is the
      one failure that actively misleads, so a partially-wired caller fails
      closed;
    * the values have **no spread** *within any one gameweek*. Uniform is not
      information, and taking the fast exit here is what makes "identical
      ``p_play`` across the pool is decision-identical to main" true at *any*
      value rather than at one.

    The spread is measured per gameweek and the gate passes if one gameweek
    has any, because everything §F1 asks is asked inside a week: which of
    *this* week's benched players comes on first, how fragile *this* week's XI
    is, how likely *this* week's captain is to leave the armband unused. A
    pooled min/max over the whole horizon calls 0.9-for-everyone in GW1 and
    0.4-for-everyone in GW2 a spread of 0.5, and then re-prices both benches
    off what is really one fixture-difficulty constant per week.

    The denominator is the pairs the pool prices, not ``codes × horizon``: a
    **blank gameweek** is a week a club has no fixture in, ``ep_matrix`` drops
    it from the mapping entirely (``models/assemble.py``), and the same source
    that had no expected points for it has no appearance probability for it
    either. Counting that pair as absent would fail the gate closed on every
    real blank in the horizon — a correctly wired caller degraded to the
    pre-v10 solve by the fixture list. So a pair the pool does not price and
    ``p_play`` does not carry is skipped by both; a pair the pool *does* price
    and ``p_play`` does not is the partially-wired caller, and still absence.

    A rejection prints one line naming the reason. Failing closed is right;
    failing closed *silently* is how a caller that believes it wired the
    feature gets the pre-v10 solve with nothing in the advice to say so.
    """
    if not p_play:
        return None
    live = pool.loc[~pool["code"].isin(state.locked_out), ["code", "ep"]]
    ep_by_code = {int(c): e for c, e in zip(live["code"], live["ep"])}
    codes = list(ep_by_code)
    out: dict[int, dict[int, float]] = {}
    span: dict[int, tuple[float, float]] = {}   # per gameweek: (min, max)
    absent = unusable = priced = 0
    for c in codes:
        per_gw = p_play.get(c) or {}
        row: dict[int, float] = {}
        for g in state.gws:
            v = per_gw.get(g)
            if v is None and _is_blank(ep_by_code[c], g):
                # Neither side has this week. Not a hole — a blank.
                continue
            priced += 1
            # A number, and not a bool, and not a string that happens to
            # parse. A caller that built this dict out of strings built it
            # wrong, and coercing would hide that rather than fail closed.
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                absent += 1
                continue
            v = float(v)
            # NaN fails this comparison too, which is the point.
            if not 0.0 <= v <= 1.0:
                unusable += 1
                continue
            row[g] = v
            lo, hi = span.get(g, (v, v))
            span[g] = (min(lo, v), max(hi, v))
        out[c] = row
    if absent or unusable:
        # Counted rather than short-circuited: the whole scan is a dict lookup
        # per pair and the difference between one missing player and half the
        # pool is the difference between a wiring typo and a wiring decision.
        print(f"optimize: p_play ignored, incomplete coverage — {absent} of "
              f"{priced} priced (code, gw) pairs absent, {unusable} not a "
              "probability in [0, 1]; the likeliest cause is a blanked "
              "gameweek in the horizon that the pool still prices and the "
              "minutes source does not, and the next is a partially-wired "
              "caller; solving unweighted")
        return None
    if not any(hi - lo >= P_PLAY_MIN_SPREAD for lo, hi in span.values()):
        print("optimize: p_play ignored, no spread within any gameweek of the "
              "horizon; solving unweighted")
        return None
    return out


def _decision_scales(plan: "Plan", pool: pd.DataFrame,
                     pp: dict[int, dict[int, float]]) -> dict:
    """Pass one's answer -> pass two's weights and pins (plan A1).

    Three ratios per gameweek, all through the same clamp: the XI's mean
    frailty for the outfield bench slots, the *XI keeper's own* for the reserve
    keeper — he plays exactly when that one man does not, which is why the
    outfield mean would be the wrong number — and the captain's for the vice
    hedge.

    The keeper's ratio is also over its own denominator, :data:`KEEPER_DNP`:
    a frailty is 1.0 only at the population it was measured on, and a
    population-typical keeper has to reproduce ``bench_curve[0]`` exactly or
    the "modulation of a calibrated curve" story is not true for that slot.

    The XI and the captain are pinned. The vice scale is the captain's
    frailty, so leaving the armband free in pass two would let the solver
    re-elect a captain under a weight computed from a different one; §F1
    changes no captaincy term, so pinning costs nothing it wanted.
    """
    pos = dict(zip(pool["code"], pool["position"]))
    bench_scale: dict[int, tuple[float, float]] = {}
    vice_scale: dict[int, float] = {}
    fixed_xi: dict[int, list[int]] = {}
    fixed_captain: dict[int, int] = {}
    for gp in plan.gw_plans:
        t, xi = gp.gw, list(gp.xi)
        dnp = [1.0 - pp[c][t] for c in xi if c in pp and t in pp[c]]
        if not dnp:
            continue
        out_f = _frailty(sum(dnp) / len(dnp))
        keeper = next((c for c in xi if pos.get(c) == "GKP"), None)
        gk_f = (_frailty(1.0 - pp[keeper][t], KEEPER_DNP)
                if keeper is not None and keeper in pp else out_f)
        cap = gp.captain
        bench_scale[t] = (out_f, gk_f)
        vice_scale[t] = (_frailty(1.0 - pp[cap][t])
                         if cap in pp and t in pp[cap] else 1.0)
        fixed_xi[t] = xi
        fixed_captain[t] = int(cap)
    return {"bench_scale": bench_scale, "vice_scale": vice_scale,
            "fixed_xi": fixed_xi, "fixed_captain": fixed_captain}


def solve_plan(pool: pd.DataFrame, state: SolveInput, *, decay: float,
               bench_weight: float, vice_weight: float, ft_value: float,
               itb_value: float, hit_cost: int,
               fixed_moves: FixedMoves | None = None,
               ft_lambda: "LambdaLookup | None" = None,
               ft_use_penalty: float = 0.0,
               bench_curve: list[float] | None = None,
               p_play: dict[int, dict[int, float]] | None = None,
               no_good: list[list[tuple[str, int, int]]] | None = None
               ) -> Plan:
    """Solve the multi-period plan; see :func:`_solve_once` for the model.

    ``p_play`` is ``{code: {gw: probability of appearing}}`` and is the only
    thing this wrapper adds. Omitted — every caller in the tree at the time of
    writing — this function is a single call to ``_solve_once`` with today's
    arguments and today's answer, character for character.

    Supplied and *informative* (plan A2: full coverage, some spread), the solve
    becomes two passes, v10 §F1a:

    1. today's solve, which decides the XI and the captain;
    2. the same problem with the bench weights and the vice term rescaled by
       how fragile *that* XI is, the XI and captain pinned, and the four
       non-XI squad places free to be re-chosen for the cover they give.

    The pin is on **every** gameweek of the horizon, not just the first: pass
    one's XI and captain for week t are fixed in week t. So the only transfers
    pass two can make are bench-for-bench — it may not sell a starter, because
    the starter is pinned into the XI that owns him. That is the intended
    scope. §F1a re-prices *cover*, and letting the second pass re-pick the
    eleven under weights derived from the first pass's eleven would be a
    different and circular thing to be doing.

    The MILP stays linear because the frailty is a number by the time it is
    used, not an expression over the XI variables — which is the whole reason
    for two passes rather than one quadratic objective.

    Pass two is a refinement and never a gate: if it is infeasible, fails, or
    the solver dies, pass one's answer is what is returned. That fallback is
    believed unreachable — pass two is pass one plus pins taken from pass
    one's own answer, so pass one's solution is feasible for pass two, and the
    objective differs only in coefficients. It is kept because "believed" is
    the operative word and a solver dying under a deadline must not cost the
    week its advice.
    """
    # v12 W2 §3.4 (specs/2026-09-01-gaffer-v12-program-design.md). Read here
    # rather than carried on SolveInput: seven call sites construct one and
    # two of them are protected files. Empty dict when the switch is off, the
    # log is missing, corrupt, or stale — and an empty dict makes every
    # expression below arithmetically today's.
    from gaffer.price_timing import owned_price_falls

    kw = dict(decay=decay, bench_weight=bench_weight,
              vice_weight=vice_weight, ft_value=ft_value,
              itb_value=itb_value, hit_cost=hit_cost,
              fixed_moves=fixed_moves, ft_lambda=ft_lambda,
              ft_use_penalty=ft_use_penalty, bench_curve=bench_curve,
              price_fall=owned_price_falls(state.owned_codes),
              # v12 W3 §4.3: in ``kw`` and not passed separately, so the
              # re-weighted second pass excludes the same plans the first did.
              # A cut that lived only in pass one would let pass two hand back
              # the incumbent as its own alternative.
              no_good=no_good)
    pp = _p_play_lookup(pool, state, p_play)
    first = _solve_once(pool, state, **kw, p_play=pp)
    if pp is None:
        return first
    try:
        return _solve_once(pool, state, **kw, p_play=pp,
                           **_decision_scales(first, pool, pp))
    except Exception as exc:  # noqa: BLE001 — pass two never gates advice
        # v10 §F1a: an infeasible re-weighted solve means the pinned XI cannot
        # be built under the transfer constraints this horizon carries. That
        # is a refinement failing, not a plan failing, and pass one is a legal
        # optimum that was already computed.
        print(f"optimize: autosub-weighted second pass failed ({exc}); "
              f"serving the unweighted plan")
        return first


def alternative_plans(pool: pd.DataFrame, state: SolveInput,
                      incumbent: Plan, *, max_gap: float,
                      max_plans: int = ALT_PLAN_MAX,
                      **solve_cfg) -> list[Plan]:
    """Up to ``max_plans - 1`` distinct plans behind ``incumbent``, best first.

    Each is the best plan that does not make some move of every plan already
    found — one no-good cut per plan, accumulated — and each carries its
    ``gap`` against the incumbent's objective. The search stops at
    ``max_plans``, at a gap wider than ``max_gap``, or when the cuts leave
    nothing legal to find.

    ``max_gap <= 0`` returns immediately **without solving**, which is the off
    switch: a knob that still spent two MILPs to discard their answers would
    be a preference rather than a switch.

    ``solve_cfg`` is the caller's ordinary ``solve_plan`` bundle and must
    **not** carry ``fixed_moves``. An alternative constrained to make the
    incumbent's moves is not an alternative — which is also why a gap can come
    back negative when the incumbent itself was solved under a coherence
    constraint (plan A5).

    Each call re-enters ``solve_plan``, which re-reads
    ``price_timing.owned_price_falls`` — cached on ``(snap_date, owned)``, so
    the incumbent and every alternative are priced off one price table and
    ``gap`` is apples-to-apples.

    A failed solve ends the search rather than raising: two plans are a
    better answer than none, and the caller is an advice run under a deadline.

    v12 W3 §4.3 (specs/2026-09-01-gaffer-v12-program-design.md).
    """
    if max_gap <= 0 or max_plans <= 1:
        return []
    cuts = [move_set(incumbent)]
    out: list[Plan] = []
    while len(out) < max_plans - 1:
        try:
            alt = solve_plan(pool, state, **solve_cfg, no_good=list(cuts))
        except Exception as exc:  # noqa: BLE001 — see docstring
            print(f"optimize: no further distinct plan ({exc})")
            break
        alt.gap = round(incumbent.objective - alt.objective, 3)
        if alt.gap > max_gap:
            break
        out.append(alt)
        cuts.append(move_set(alt))
    return out


def _solve_once(pool: pd.DataFrame, state: SolveInput, *, decay: float,
                bench_weight: float, vice_weight: float, ft_value: float,
                itb_value: float, hit_cost: int,
                fixed_moves: FixedMoves | None = None,
                ft_lambda: "LambdaLookup | None" = None,
                ft_use_penalty: float = 0.0,
                bench_curve: list[float] | None = None,
                p_play: dict[int, dict[int, float]] | None = None,
                price_fall: dict[int, float] | None = None,
                no_good: list[list[tuple[str, int, int]]] | None = None,
                bench_scale: dict[int, tuple[float, float]] | None = None,
                vice_scale: dict[int, float] | None = None,
                fixed_xi: dict[int, list[int]] | None = None,
                fixed_captain: dict[int, int] | None = None) -> Plan:
    """Solve the multi-period plan.

    pool: [code, position, team_code, cost, sell, ep] where ep is a dict
    {gw: expected_points} (missing gw -> 0, e.g. blank GWs).
    Prices are static over the horizon (documented approximation).
    """
    pool = pool[~pool["code"].isin(state.locked_out)].reset_index(drop=True)
    codes = pool["code"].tolist()
    known = set(codes)
    for label, wanted in (("lock", state.locked_in),
                          ("force_in", state.force_in_gw),
                          # v12 W3 §4.1 (specs/2026-09-01-gaffer-v12-program-design.md):
                          # a code that is not in the pool cannot be
                          # constrained, and silently not selling a player the
                          # caller said to sell is the failure worth refusing.
                          ("force_out", state.force_out)):
        missing = [c for c in wanted if c not in known]
        if missing:
            raise GafferError(
                f"{label}: player code {missing[0]} is not in the candidate "
                f"pool (it may also be banned)")
    # v12 W3 §4.1: caught here rather than left to the solver, which would
    # report "MILP not optimal: Infeasible" and name nothing.
    contradiction = sorted(set(state.locked_in) & set(state.force_out))
    if contradiction:
        raise GafferError(
            f"force_out: player code {contradiction[0]} is also locked in — "
            f"a squad cannot both keep and sell him")
    if bench_curve is not None and len(bench_curve) != BENCH_SLOTS:
        raise GafferError(
            f"bench_curve needs exactly three weights (1st/2nd/3rd outfield "
            f"substitute), got {len(bench_curve)}")
    pos = dict(zip(pool["code"], pool["position"]))
    club = dict(zip(pool["code"], pool["team_code"]))
    cost = dict(zip(pool["code"], pool["cost"]))
    sell = dict(zip(pool["code"], pool["sell"]))
    ep_col = dict(zip(pool["code"], pool["ep"]))
    ep = {c: {g: float(ep_col[c].get(g, 0.0)) for g in state.gws}
          for c in codes}
    owned0 = {c: int(c in set(state.owned_codes)) for c in codes}
    T = state.gws

    prob = pulp.LpProblem("gaffer", pulp.LpMaximize)
    V = pulp.LpVariable.dicts
    sq = V("sq", (codes, T), cat="Binary")
    xi = V("xi", (codes, T), cat="Binary")
    cap = V("cap", (codes, T), cat="Binary")
    vice = V("vc", (codes, T), cat="Binary")
    tin = V("in", (codes, T), cat="Binary")
    tout = V("out", (codes, T), cat="Binary")
    hits = V("hit", T, lowBound=0, cat="Integer")
    ftv = V("ft", T, lowBound=0, upBound=MAX_FREE_TRANSFERS, cat="Integer")
    bank = V("bank", T, lowBound=0)
    # Bench-slot indicators, declared only when a curve is in play so the
    # default problem is byte-identical to the pre-v4c one.
    slot = (V("slot", (codes, T, list(range(BENCH_SLOTS))), cat="Binary")
            if bench_curve is not None else None)

    for t_i, t in enumerate(T):
        wc = (state.wildcard_gw == t)
        nt = pulp.lpSum(tin[c][t] for c in codes)
        # squad continuity
        for c in codes:
            prev = owned0[c] if t_i == 0 else sq[c][T[t_i - 1]]
            prob += sq[c][t] == prev + tin[c][t] - tout[c][t]
            prob += tin[c][t] + tout[c][t] <= 1
            prob += xi[c][t] <= sq[c][t]
            prob += cap[c][t] <= xi[c][t]
            prob += vice[c][t] <= xi[c][t]
            prob += cap[c][t] + vice[c][t] <= 1
        if slot is not None:
            benched = {c: sq[c][t] - xi[c][t] for c in codes}
            outfield = [c for c in codes if pos[c] != "GKP"]
            for s in range(BENCH_SLOTS):
                # Exactly one player fills each outfield bench slot.
                prob += pulp.lpSum(slot[c][t][s] for c in outfield) == 1
            for c in outfield:
                # A player can fill at most one slot, and only if benched.
                prob += pulp.lpSum(slot[c][t][s]
                                   for s in range(BENCH_SLOTS)) <= benched[c]
            for c in codes:
                if pos[c] == "GKP":
                    for s in range(BENCH_SLOTS):
                        prob += slot[c][t][s] == 0
        # v10 §F1a (specs/2026-09-01-gaffer-v10-minutes-design.md): pass two's
        # pins. The bench slots are being priced by how fragile *this* XI is,
        # so the XI has to still be this XI when the solver is done; and the
        # vice term is being priced by *this* captain's frailty, so the armband
        # has to stay on him. What is left free is exactly what §F1a is about:
        # the four non-XI places and which of them comes on first.
        #
        # Never entered on pass one, and never entered by any call that passes
        # no p_play — which is the pre-v10 problem, unchanged.
        if fixed_xi is not None and t in fixed_xi:
            keep = set(fixed_xi[t])
            for c in codes:
                prob += xi[c][t] == (1 if c in keep else 0)
            if fixed_captain is not None and t in fixed_captain:
                prob += cap[fixed_captain[t]][t] == 1
        # composition
        for p, n in SQUAD_COMPOSITION.items():
            prob += pulp.lpSum(sq[c][t] for c in codes if pos[c] == p) == n
        prob += pulp.lpSum(xi[c][t] for c in codes) == 11
        for p, (lo, hi) in XI_BOUNDS.items():
            n_p = pulp.lpSum(xi[c][t] for c in codes if pos[c] == p)
            prob += n_p >= lo
            prob += n_p <= hi
        prob += pulp.lpSum(cap[c][t] for c in codes) == 1
        prob += pulp.lpSum(vice[c][t] for c in codes) == 1
        for tc in set(club.values()):
            prob += pulp.lpSum(
                sq[c][t] for c in codes if club[c] == tc) <= MAX_PER_CLUB
        # budget: bank rolls forward, sales fund purchases, never negative
        inflow = pulp.lpSum(sell[c] * tout[c][t] for c in codes)
        outflow = pulp.lpSum(cost[c] * tin[c][t] for c in codes)
        prev_bank = state.bank if t_i == 0 else bank[T[t_i - 1]]
        prob += bank[t] == prev_bank + inflow - outflow
        # free transfers & hits
        prev_ft = state.free_transfers if t_i == 0 else ftv[T[t_i - 1]]
        if wc:
            prob += hits[t] == 0                 # unlimited free transfers
            prob += ftv[t] <= prev_ft + 1        # banked FTs survive the WC
        else:
            # hits is penalised in the objective so the >= bound is tight;
            # ftv is rewarded so its <= bound is tight. The <= nt cut stops
            # the solver from buying FTs with phantom hits (see module note).
            prob += hits[t] >= nt - prev_ft
            prob += hits[t] <= nt
            prob += ftv[t] <= prev_ft - nt + hits[t] + 1
        prob += ftv[t] <= MAX_FREE_TRANSFERS
        for c in state.locked_in:
            prob += sq[c][t] == 1
        # v12 W3 §4.1 (specs/2026-09-01-gaffer-v12-program-design.md): squad
        # membership 0 from the first horizon gameweek onward. Continuity
        # (``sq == prev + tin - tout``) turns an owned player's zero into a
        # ``tout`` in the first week, which is what pays the bank.
        for c in state.force_out:
            prob += sq[c][t] == 0
        if state.max_hits is not None and not wc:
            prob += hits[t] <= state.max_hits
    for c in state.force_in_gw:
        prob += tin[c][T[0]] == 1

    # --- forced moves from the decision policy ---------------------------
    # Deliberately after force_in_gw so the two cannot be confused: this one
    # names both sides of the trade and can also pin the week shut entirely.
    if fixed_moves is not None:
        fm_gw = fixed_moves.gw if fixed_moves.gw is not None else T[0]
        if fm_gw not in T:
            raise GafferError(
                f"fixed_moves: gameweek {fm_gw} is not in the horizon {T}")
        if fixed_moves.no_transfer and (fixed_moves.buys
                                        or fixed_moves.sells):
            raise GafferError(
                "fixed_moves: no_transfer cannot be combined with buys or "
                "sells — the policy must choose one or the other")
        missing = [c for c in list(fixed_moves.buys) + list(fixed_moves.sells)
                   if c not in known]
        if missing:
            raise GafferError(
                f"fixed_moves: player code {missing[0]} is not in the "
                "candidate pool (it may also be banned)")
        for c in fixed_moves.buys:
            prob += tin[c][fm_gw] == 1
        for c in fixed_moves.sells:
            prob += tout[c][fm_gw] == 1
        if fixed_moves.no_transfer:
            prob += pulp.lpSum(tin[c][fm_gw] for c in codes) == 0

    # --- no-good cuts (v12 W3 §4.3) --------------------------------------
    # (specs/2026-09-01-gaffer-v12-program-design.md). Each cut is a plan's
    # complete move set; the constraint forbids making *all* of them at once,
    # which is the standard no-good cut over binaries that are all 1 in the
    # solution being excluded. A plan making those moves and one more is
    # excluded too, deliberately: it is not a distinct decision, it is the
    # same one with a passenger.
    #
    # The empty cut is the hold plan, and it is a real case rather than a
    # corner: ``sum(nothing) <= -1`` is infeasible, so "differ from a plan
    # that made no transfers" has to be spelled as "make at least one".
    for cut in (no_good or []):
        terms = []
        for kind, c, t in cut:
            if c not in known or t not in T:
                raise GafferError(
                    f"no_good: ({kind}, {c}, gw{t}) is not expressible on "
                    f"this board — the cut was built from a different pool "
                    f"or a different horizon")
            terms.append(tin[c][t] if kind == "in" else tout[c][t])
        if terms:
            prob += pulp.lpSum(terms) <= len(terms) - 1
        else:
            prob += pulp.lpSum(tin[c][t] for c in codes for t in T) >= 1

    obj = []
    for t_i, t in enumerate(T):
        d = decay ** t_i
        wc = (state.wildcard_gw == t)
        nt = pulp.lpSum(tin[c][t] for c in codes)
        cap_mult = 2.0 if state.triple_captain_gw == t else 1.0
        bw = 1.0 if state.bench_boost_gw == t else bench_weight
        # v10 §F1a/§F1c (specs/2026-09-01-gaffer-v10-minutes-design.md): the
        # two population weights this gameweek is priced with. Both default to
        # 1.0 — no p_play, or a p_play with no spread in it — and at 1.0 every
        # expression below is arithmetically today's.
        out_f, gk_f = (bench_scale or {}).get(t, (1.0, 1.0))
        vw = vice_weight * (vice_scale or {}).get(t, 1.0)
        for c in codes:
            e = ep[c][t]
            obj.append(d * e * (xi[c][t] + cap_mult * cap[c][t]
                                + vw * vice[c][t]))
            if bench_curve is None or state.bench_boost_gw == t:
                # No curve, or a bench boost — under a boost every bench
                # player scores in full, so slot weights would understate the
                # chip. A boosted bench is not an autosub either, which is why
                # §F1a deliberately leaves this branch alone.
                obj.append(d * e * bw * (sq[c][t] - xi[c][t]))
            elif pos[c] == "GKP":
                # The reserve keeper is priced by the first curve weight: he
                # plays exactly when the starter does not — which is also why
                # his weight reads the XI keeper's own frailty and not the
                # outfield mean (v10 §F1a).
                obj.append(d * e * bench_curve[0] * gk_f
                           * (sq[c][t] - xi[c][t]))
            else:
                for s in range(BENCH_SLOTS):
                    obj.append(d * e * bench_curve[s] * out_f
                               * slot[c][t][s])
        obj.append(-hit_cost * d * hits[t])
        # v12 W2 §3.4 (specs/2026-09-01-gaffer-v12-program-design.md). Selling
        # a falling player next week instead of this week loses 0.1m of his
        # sale, which the objective already prices at itb_value per million
        # (see the bank term below). So a deferred sale is charged exactly
        # that, weighted by tonight's fall probability. No term for a rise:
        # spec §8 and the ROADMAP both name price chasing as rejected.
        #
        # Undecayed, deliberately, like the bank term it is denominated
        # against: the money is lost at the moment of the sale and the
        # horizon's decay is about the value of *points* later, not of pounds.
        #
        # It is a tie-breaker and not a driver, and the magnitude says so:
        # 0.008 points at the shipped itb_value of 0.08, against a solver
        # whose default relative gap on a real horizon is around 0.02. It
        # decides exactly-equal sell timings, which is where the question
        # actually arises, and it will not move a plan that has any real EP
        # difference in it (plan A6).
        if price_fall and t != T[0]:
            for c in codes:
                p = price_fall.get(c)
                if p:
                    obj.append(-p * 0.1 * itb_value * tout[c][t])
        # A tiny friction per transfer made. EP-neutral churn is what the
        # scenario noise flips week to week, and a fraction of a point of
        # resistance settles it without ever outweighing a real gain. Waived
        # on a wildcard: fifteen transfers there are the chip working as
        # designed.
        if ft_use_penalty:
            if not wc:
                obj.append(-ft_use_penalty * d * nt)
    # Terminal value of the banked free transfers.
    #
    # Flat ft_value says the fifth banked transfer is worth as much as the
    # first, which is the assumption that makes the solver hoard. With a
    # lambda table the value is concave: ftge[j] is "the terminal count is at
    # least j", each priced by its own shadow price, and their sum is the
    # count. Lambda is decreasing in j, so maximization fills the low indices
    # first without being told to; the ordering constraints are insurance
    # against a degenerate table, not the mechanism.
    if ft_lambda is None or ft_lambda.empty:
        obj.append(ft_value * ftv[T[-1]])
    else:
        weeks_left = max(1, SEASON_LAST_GW - T[-1])
        ftge = V("ftge", list(range(1, MAX_FREE_TRANSFERS + 1)),
                 cat="Binary")
        prob += ftv[T[-1]] == pulp.lpSum(
            ftge[j] for j in range(1, MAX_FREE_TRANSFERS + 1))
        for j in range(2, MAX_FREE_TRANSFERS + 1):
            prob += ftge[j] <= ftge[j - 1]
        for j in range(1, MAX_FREE_TRANSFERS + 1):
            obj.append(ft_lambda(j, weeks_left) * ftge[j])
    obj.append((itb_value / 10.0) * bank[T[-1]])
    prob += pulp.lpSum(obj)

    _solve(prob)
    if pulp.LpStatus[prob.status] != "Optimal":
        raise RuntimeError(f"MILP not optimal: {pulp.LpStatus[prob.status]}")

    def val(v):
        return v.varValue is not None and v.varValue > 0.5

    gw_plans = []
    for t in T:
        squad = [c for c in codes if val(sq[c][t])]
        xi_l = [c for c in codes if val(xi[c][t])]
        # v10 §F1b (specs/2026-09-01-gaffer-v10-minutes-design.md): bench order
        # is autosub *value*, not raw EP. The first sub is the one most likely
        # to actually come on and score, and a 6.0-EP starter at p_play 0.5 is
        # worth less on the bench than a 5.0-EP starter at 0.9 — the ordering
        # this replaces could not see the difference. GK still last, which is
        # the bench-GK convention and not a value judgement. ``-ep[c][t]`` is
        # kept as the final tiebreak so a tie in autosub value resolves exactly
        # as it did before v10, and so an absent p_play is the pre-v10 key.
        #
        # In a double gameweek the two factors are built on different rules and
        # the product is deliberate rather than dimensional: ``ep[c][t]`` is the
        # week's *summed* EP over both fixtures, while ``p_play`` is the *mean*
        # over them, because "did he turn out at all" is one outcome (the rule
        # news_shadow.shadow_rows applies, for its reason). The key is a
        # comparable ranking number and not an expectation: a doubled-up player
        # keeps the whole of his two fixtures' EP, discounted by how likely he
        # is to appear at all, which is the ordering question the bench asks.
        bench = sorted(
            (c for c in squad if c not in xi_l),
            key=lambda c: (pos[c] == "GKP",
                           -(ep[c][t] * (1.0 if p_play is None
                                         else p_play.get(c, {}).get(t, 1.0))),
                           -ep[c][t]))
        gw_plans.append(GwPlan(
            gw=t, squad=squad, xi=xi_l,
            xi_rows=[{"code": c, "position": pos[c], "ep": ep[c][t]}
                     for c in xi_l],
            bench=bench,
            captain=next(c for c in codes if val(cap[c][t])),
            vice=next(c for c in codes if val(vice[c][t])),
            buys=[c for c in codes if val(tin[c][t])],
            sells=[c for c in codes if val(tout[c][t])],
            hits=int(round(hits[t].varValue or 0)),
            expected_pts=sum(ep[c][t] for c in xi_l)
                         + max((ep[c][t] for c in xi_l), default=0.0),
            # v12 W3 §4.5: not ``or None`` — a bank of exactly zero is a real
            # and common state (fully invested), and reading it as unknown
            # would send ``free_hit_gain`` back to today's figures on the very
            # weeks the plan spends everything.
            bank=(None if bank[t].varValue is None
                  else round(float(bank[t].varValue), 4)),
        ))
    return Plan(objective=pulp.value(prob.objective), gw_plans=gw_plans)


def _solve(prob: pulp.LpProblem) -> None:
    """Solve with HiGHS, falling back to bundled CBC on any failure.

    HiGHS can construct fine and still blow up at solve time (missing shared
    library, unsupported build), so the fallback wraps the solve itself.
    """
    try:
        prob.solve(pulp.HiGHS(msg=False))
        return
    except Exception:
        pass
    prob.solve(pulp.PULP_CBC_CMD(msg=False))


def build_pool(players: pd.DataFrame, ep_by_code_gw: dict,
               my_picks: pd.DataFrame, gws: list[int],
               top_n: dict | None = None) -> pd.DataFrame:
    """Candidate pool: owned players + top-N per position by horizon EP.

    Keeps the MILP small (fast) without losing realistic candidates.
    """
    if top_n is None:
        # v12 W1 §2.6 (specs/2026-09-01-gaffer-v12-program-design.md). These
        # four numbers decide which players the solver is allowed to consider
        # at all, and until now they existed only here — so a plan that never
        # mentioned an owned player could not be distinguished from a plan
        # that had considered and rejected him. `[optimizer] top_n` in config
        # is the same four numbers where a user can see them, and
        # `optimizer_top_n()` falls back to DEFAULT_TOP_N on anything
        # unreadable: a typo in a TOML file must not silently shrink the pool.
        from gaffer.config import optimizer_top_n

        top_n = optimizer_top_n()
    players = players.copy()
    players["ep"] = players["code"].map(
        lambda c: {g: ep_by_code_gw.get((c, g), 0.0) for g in gws})
    players["h_ep"] = players["ep"].map(lambda d: sum(d.values()))
    owned = set(my_picks["code"])
    keep = [players[players["position"] == p].nlargest(n, "h_ep")
            for p, n in top_n.items()]
    pool = pd.concat(keep).drop_duplicates("code")
    pool = pd.concat([pool, players[players["code"].isin(owned)]]) \
             .drop_duplicates("code")
    sell_map = dict(zip(my_picks["code"], my_picks["sell"]))
    pool["cost"] = pool["now_cost"]
    pool["sell"] = pool.apply(
        lambda r: sell_map.get(r["code"], r["now_cost"]), axis=1)
    return pool[["code", "position", "team_code", "cost", "sell", "ep"]]
