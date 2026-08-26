"""Frequencies decide.

The scenario sweep produces a distribution over plans; this module turns that
distribution into one recommendation. The rule is deliberately blunt: a move is
recommended when enough of the noised worlds wanted it, and otherwise it is
not made at all.

Two bars rather than one, because the moves are not symmetric in what they cost
when they are wrong. A transfer you regret costs you a transfer — you take it
back next week and you are one FT down. A hit you regret costs four points that
are simply gone, and a chip you regret is gone for half a season. So reversible
moves clear at 60% and irreversible ones at 75%.

The captain is the exception and gets no bar at all: somebody wears the armband
every week, so the question is never "should we captain" but "who", and the
plurality winner is the answer. Ties break towards the raw optimum, which keeps
the advice stable across re-runs instead of coin-flipping.

Nothing here solves anything — :func:`coherent_plan` does that. This module
answers "what do we want", and the MILP answers "what is the best legal plan
that does it".
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from gaffer.optimize.milp import FixedMoves, Plan, SolveInput, solve_plan

NEAR_MISS_BAND = 0.20
"""How far below its bar a move can sit and still be worth printing.

A move at 55% against a 60% bar is a genuinely close call the reader should
see. One at 5% is noise, and listing it would bury the near misses that matter
in a wall of players the model never seriously wanted.
"""


@dataclass
class Thresholds:
    """The two bars, defaulted to spec §4's numbers."""
    transfer: float = 0.60
    irreversible: float = 0.75


@dataclass
class Decision:
    """What the frequencies say to do, before it is made legal.

    ``buys`` and ``sells`` are what *cleared their bar*, which is not the same
    as what is executable — a passing buy with no passing sell is a real and
    informative state, and flattening it here would hide it from the coherence
    re-solve that has to resolve it.
    """
    buys: list[int] = field(default_factory=list)
    sells: list[int] = field(default_factory=list)
    captain: int = 0
    captain_frequency: float = 0.0
    hit: bool = False
    chip: str | None = None
    chip_gw: int | None = None
    hold: bool = False
    raw_optimum_agrees: bool = False
    near_misses: list[dict] = field(default_factory=list)
    frequencies: pd.DataFrame = field(default_factory=pd.DataFrame)


def _rows(freq: pd.DataFrame, kind: str) -> pd.DataFrame:
    if freq.empty:
        return freq
    return freq[freq["kind"] == kind]


def decide(frequencies: pd.DataFrame, raw_plan: Plan,
           thresholds: Thresholds | None = None) -> Decision:
    """Gate a scenario sweep's move frequencies into one recommendation.

    ``raw_plan`` is the deterministic, un-noised solve. It is used for exactly
    two things: breaking captain ties, and answering "did the single-solve
    optimum agree with the gated advice" — the one line the raw optimum is
    demoted to in the report.
    """
    th = thresholds or Thresholds()
    first = raw_plan.gw_plans[0]

    buy_rows = _rows(frequencies, "buy")
    sell_rows = _rows(frequencies, "sell")
    passing_buys = buy_rows[buy_rows["frequency"] >= th.transfer] \
        if not buy_rows.empty else buy_rows
    passing_sells = sell_rows[sell_rows["frequency"] >= th.transfer] \
        if not sell_rows.empty else sell_rows
    buys = [int(c) for c in passing_buys.sort_values(
        "frequency", ascending=False)["code"]] if not buy_rows.empty else []
    sells = [int(c) for c in passing_sells.sort_values(
        "frequency", ascending=False)["code"]] if not sell_rows.empty else []

    hit_rows = _rows(frequencies, "hit")
    hit = bool(not hit_rows.empty
               and (hit_rows["frequency"] >= th.irreversible).any())

    chip, chip_gw = None, None
    chip_rows = _rows(frequencies, "chip")
    if not chip_rows.empty:
        passing = chip_rows[chip_rows["frequency"] >= th.irreversible]
        if not passing.empty:
            best = passing.sort_values("frequency", ascending=False).iloc[0]
            chip, chip_gw = str(best["label"]), int(best["gw"])

    cap_rows = _rows(frequencies, "captain")
    if cap_rows.empty:
        captain, captain_frequency = int(first.captain), 0.0
    else:
        top = cap_rows["frequency"].max()
        tied = [int(c) for c in cap_rows[cap_rows["frequency"] == top]["code"]]
        # Stability beats arbitrariness: when the sweep cannot separate two
        # candidates, defer to the un-noised solve rather than to whichever
        # order the groupby happened to produce.
        captain = (int(first.captain) if int(first.captain) in tied
                   else min(tied))
        captain_frequency = float(top)

    hold = not buys and not sells and chip is None

    near_misses = []
    if not frequencies.empty:
        for r in frequencies.itertuples():
            bar = (th.irreversible if r.kind in ("hit", "chip")
                   else th.transfer)
            if r.kind == "captain":
                continue
            if bar - NEAR_MISS_BAND <= r.frequency < bar:
                near_misses.append({"kind": r.kind, "code": int(r.code),
                                    "gw": int(r.gw), "label": str(r.label),
                                    "frequency": float(r.frequency)})
        near_misses.sort(key=lambda m: -m["frequency"])

    raw_agrees = (sorted(buys) == sorted(int(c) for c in first.buys)
                  and sorted(sells) == sorted(int(c) for c in first.sells)
                  and captain == int(first.captain)
                  and hit == bool(first.hits))

    return Decision(buys=buys, sells=sells, captain=captain,
                    captain_frequency=captain_frequency, hit=hit, chip=chip,
                    chip_gw=chip_gw, hold=hold, raw_optimum_agrees=raw_agrees,
                    near_misses=near_misses, frequencies=frequencies)


def captain_frequency_of(frequencies: pd.DataFrame,
                         code: int) -> float | None:
    """How often the sweep captained ``code``, or ``None`` if it never did.

    :func:`coherent_plan` drops the plurality winner when the re-solved squad
    does not contain him, so ``Decision.captain_frequency`` is the frequency
    of a player who may not be wearing the armband. Printing it next to the
    captain who is would be a fabricated number; ``None`` is the honest one.
    """
    if frequencies.empty or "kind" not in frequencies.columns:
        return None
    rows = frequencies[(frequencies["kind"] == "captain")
                       & (frequencies["code"] == int(code))]
    if rows.empty:
        return None
    return float(rows["frequency"].iloc[0])


def coherent_plan(pool: pd.DataFrame, state: SolveInput, decision: Decision,
                  **solve_cfg) -> Plan:
    """The best legal plan that does what the frequencies decided.

    Threshold-passing moves are not a plan. Two buys can pass at 80% each in
    scenarios that never contained both; a buy can pass with no sell behind
    it; a hold can pass while a chip also does. Rather than reconciling those
    by hand, the passing moves go back to the MILP as
    :class:`~gaffer.optimize.milp.FixedMoves` and the solver does what it is
    for: finds the best legal completion.

    The captain is then overridden to the plurality winner, because the
    re-solve optimizes EP and the armband was decided on robustness. If he is
    not in the re-solved XI he is promoted into it, swapping out the lowest-EP
    XI player who shares his position — an armband on a benched player is not
    a legal team sheet.

    An infeasible forced set degrades to the unconstrained solve. Deadlines do
    not wait for a policy bug, and a slightly-less-robust plan beats no advice.
    """
    if decision.hold:
        fixed = FixedMoves(no_transfer=True)
    else:
        fixed = FixedMoves(buys=list(decision.buys),
                           sells=list(decision.sells))
    try:
        plan = solve_plan(pool, state, **solve_cfg, fixed_moves=fixed)
    except Exception as exc:  # noqa: BLE001 — see docstring
        print(f"coherence re-solve infeasible, using the raw optimum: {exc}")
        return solve_plan(pool, state, **solve_cfg)

    first = plan.gw_plans[0]
    wanted = int(decision.captain)
    if wanted and wanted in first.squad and first.captain != wanted:
        pos = dict(zip(pool["code"], pool["position"]))
        if wanted not in first.xi:
            same = [c for c in first.xi if pos.get(c) == pos.get(wanted)]
            if same:
                ep_of = {int(r.code): float(r.ep.get(first.gw, 0.0))
                         for r in pool.itertuples()}
                drop = min(same, key=lambda c: ep_of.get(c, 0.0))
                first.xi = [c for c in first.xi if c != drop] + [wanted]
                first.bench = [c for c in first.bench if c != wanted] + [drop]
        if wanted in first.xi:
            if first.vice == wanted:
                first.vice = first.captain
            first.captain = wanted
    return plan
