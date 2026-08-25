"""Scenario re-solving: N noised optima instead of one certain one.

The MILP is an estimation-error maximizer. Handed a forecast, it finds the
squad whose EP is highest — which, when every EP carries error, means it
systematically finds the players whose error happens to be most positive this
week. v4a measured the cost of that: a planning ceiling ~175 points above what
the tool actually scores, most of it thrown away on transfers that were never
robust to the forecast being slightly wrong.

The fix is not a better forecast; it is refusing to bet the week on one draw
from it. Perturb every EP cell by its own plausible error, re-solve, and count
how often each move survives. A transfer that shows up in 38 of 40 noised
worlds is a real edge; one that shows up in 12 is the optimizer reading tea
leaves.

The error scale is minutes-driven, which is the community-standard choice and
the right one: almost all of FPL's forecast error is *did he play*, not *how
well did he play*. A nailed-on 90-minute starter has very little error left in
his EP; a 60/40 rotation risk has an enormous amount.

Nothing here does I/O and nothing here is random unless a generator says so —
the caller owns the seed, and the seed goes in the report.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from gaffer.optimize.milp import Plan, SolveInput, solve_plan

NOISE_FLOOR_XMINS = 92.0
"""xMins at which the noise scale reaches zero.

92 rather than 90 because the community formula this follows uses the full
match including stoppage time as the "certain" anchor, which leaves a genuine
90-minute nailed-on starter with a small but non-zero wobble instead of a
mathematically impossible zero.
"""

NOISE_DENOM = 134.0
"""Divisor turning (92 - xmins) into a relative standard deviation.

At xmins = 0 the scale is 92/134 = 0.687, i.e. a player with no expected
minutes has a ~69% relative standard deviation on his EP. At xmins = 90 it is
0.015. Both are about right against observed weekly FPL residuals.
"""


def xmins_by_player_gw(comp: pd.DataFrame) -> dict[tuple[int, int], float]:
    """``{(code, gw): expected minutes}`` from the component frame.

    ``90 * p_play * p60 + 45 * p_play * (1 - p60)``: he plays the whole match
    if he starts and lasts, and half of one if he plays but does not reach 60.

    ``comp`` is one row per player-*fixture*, so a double gameweek contributes
    two rows for the same ``(code, gw)``. They are **averaged**. xMins here is
    a nailedness score feeding a *relative* noise scale, and a nailed-on
    starter with two fixtures is exactly as nailed on as one with a single
    fixture — his EP is already doubled, so his absolute noise doubles without
    any help from this function.

    A frame with no ``p_play``/``p60`` (no minutes model) returns ``{}``, which
    :func:`noise_ep` treats as "leave every cell alone".
    """
    if not {"p_play", "p60", "code", "gw"}.issubset(comp.columns):
        return {}
    p_play = pd.to_numeric(comp["p_play"], errors="coerce").fillna(0.0)
    p60 = pd.to_numeric(comp["p60"], errors="coerce").fillna(0.0)
    xm = 90.0 * p_play * p60 + 45.0 * p_play * (1.0 - p60)
    frame = pd.DataFrame({"code": comp["code"].astype(int),
                          "gw": comp["gw"].astype(int),
                          "xmins": xm.clip(0.0, NOISE_FLOOR_XMINS)})
    grouped = frame.groupby(["code", "gw"], as_index=False)["xmins"].mean()
    return {(int(r.code), int(r.gw)): float(r.xmins)
            for r in grouped.itertuples()}


def noise_ep(ep: dict[tuple[int, int], float],
             xmins: dict[tuple[int, int], float],
             rng: np.random.Generator) -> dict[tuple[int, int], float]:
    """One noised copy of an EP table.

    ``ep_noised = max(0, ep + ep * (92 - xmins) / 134 * N(0, 1))``, one
    independent draw per player-gameweek. No cross-gameweek correlation: spec
    §10 lists it as YAGNI until the simple version proves insufficient, and
    the honest reading is that a player's *minutes* risk really is close to
    independent week to week once the fixture is known.

    Clipped at zero because a negative EP is not a worse player, it is an
    incoherent one — the MILP would want to leave a squad slot empty, which it
    cannot do, so it would distort the whole board instead.

    Cells with no xMins entry pass through untouched: "we have no minutes
    prediction for this player" is not the same claim as "his minutes are
    certain", and inventing a scale for him would be the worse error.
    """
    out: dict[tuple[int, int], float] = {}
    for key, value in ep.items():
        xm = xmins.get(key)
        if xm is None:
            out[key] = value
            continue
        scale = (NOISE_FLOOR_XMINS - xm) / NOISE_DENOM
        out[key] = max(0.0, value + value * scale
                       * float(rng.standard_normal()))
    return out


def noised_pool(pool: pd.DataFrame, xmins: dict[tuple[int, int], float],
                rng: np.random.Generator) -> pd.DataFrame:
    """A copy of the candidate pool with every ``ep`` dict noised.

    The *pool* is noised rather than rebuilt from noised EP, and that is a
    deliberate choice rather than a shortcut: ``build_pool`` applies a top-N
    filter per position, so rebuilding it per scenario would change which
    players are even candidates from one scenario to the next, and a move
    frequency computed across scenarios with different candidate sets is
    counting incomparable things. Fixing the board and varying only the values
    on it is what makes the frequencies mean something.
    """
    out = pool.copy()
    cells = []
    for code, cell in zip(pool["code"], pool["ep"]):
        keyed = {(int(code), int(gw)): float(v) for gw, v in cell.items()}
        noised = noise_ep(keyed, xmins, rng)
        cells.append({gw: noised[(int(code), int(gw))] for gw in cell})
    out["ep"] = cells
    return out


@dataclass
class ScenarioRun:
    """The outcome of a scenario sweep.

    ``attempted`` and ``completed`` differ when a noised board defeated the
    solver. That difference is printed, not raised: the frequencies are still
    meaningful over the scenarios that did finish, and refusing to give advice
    because 1 solve in 40 went sideways would be the worse failure.
    """
    plans: list[Plan]
    attempted: int
    completed: int
    failures: int
    seed: int


def run_scenarios(pool: pd.DataFrame, state: SolveInput,
                  xmins: dict[tuple[int, int], float], *, n: int, seed: int,
                  **solve_cfg) -> ScenarioRun:
    """``n`` solves of the same board under ``n`` independent EP draws.

    ``solve_cfg`` is the ordinary :func:`~gaffer.optimize.milp.solve_plan`
    keyword bundle — the same ``opt_kw`` the deterministic solve uses, so a
    scenario differs from the raw optimum in the EP values and in nothing
    else.

    Sequential on purpose. At ~7s a solve, 40 scenarios is under five minutes,
    which spec §3 budgets for; a process pool would buy maybe 4x for the cost
    of pickling a PuLP problem per worker and a class of bugs that only ever
    appear on someone else's machine.

    ``n = 0`` returns an empty run without touching the solver at all — that is
    the degradation rail, and it has to be free.
    """
    if n <= 0:
        return ScenarioRun(plans=[], attempted=0, completed=0, failures=0,
                           seed=seed)
    rng = np.random.default_rng(seed)
    plans: list[Plan] = []
    failures = 0
    for _ in range(n):
        board = noised_pool(pool, xmins, rng)
        try:
            plans.append(solve_plan(board, state, **solve_cfg))
        except Exception as exc:  # noqa: BLE001 — one bad draw is not fatal
            failures += 1
            print(f"scenario solve failed, dropping it: {exc}")
    return ScenarioRun(plans=plans, attempted=n, completed=len(plans),
                       failures=failures, seed=seed)


FREQ_COLUMNS = ("kind", "code", "gw", "label", "count", "frequency")
"""Move-frequency table schema.

``code`` is the player code for ``buy``/``sell``/``captain`` and ``0`` for the
kinds that are not about a player (``hit``, ``chip``, ``no_transfer``);
``label`` carries the human-readable name (the chip name, or the kind itself),
so the report and the UI never have to reconstruct one.
"""

MOVE_KINDS = ("buy", "sell", "hit", "chip", "captain", "no_transfer")


def move_frequencies(plans: list[Plan]) -> pd.DataFrame:
    """Per candidate move, the share of scenarios containing it.

    Buys and sells are read from the **first** horizon week only: weeks two
    and three are re-planned from scratch next Tuesday, so gating them would
    put a threshold on a decision nobody is taking. Hits and chips are read
    from every week, because "this squad needs a hit in three weeks" is real
    information about *this* week's transfer.

    Within one scenario a move is counted once no matter how many times it
    appears, and a buy counts the same whether it arrived alone or as half of
    a double move — the key is the player, not the plan shape.

    Chips are read off ``plan.chip`` / ``plan.chip_gw`` when the caller has
    attached them (the chip sweep does); a plan without them contributes no
    chip rows rather than an implicit "no chip", because chip *availability*
    is not a per-scenario fact.
    """
    n = len(plans)
    empty = pd.DataFrame(columns=list(FREQ_COLUMNS))
    if n == 0:
        return empty

    counts: dict[tuple[str, int, int, str], int] = {}

    def bump(kind: str, code: int, gw: int, label: str) -> None:
        counts[(kind, code, gw, label)] = counts.get(
            (kind, code, gw, label), 0) + 1

    for plan in plans:
        seen: set[tuple[str, int, int, str]] = set()

        def once(kind: str, code: int, gw: int, label: str) -> None:
            key = (kind, code, gw, label)
            if key not in seen:
                seen.add(key)
                bump(*key)

        first = plan.gw_plans[0]
        for code in first.buys:
            once("buy", int(code), int(first.gw), "buy")
        for code in first.sells:
            once("sell", int(code), int(first.gw), "sell")
        if not first.buys and not first.sells:
            once("no_transfer", 0, int(first.gw), "no_transfer")
        once("captain", int(first.captain), int(first.gw), "captain")
        for gp in plan.gw_plans:
            if gp.hits:
                once("hit", 0, int(gp.gw), "hit")
        chip = getattr(plan, "chip", None)
        if chip:
            once("chip", 0, int(getattr(plan, "chip_gw", first.gw)), str(chip))

    rows = [{"kind": kind, "code": code, "gw": gw, "label": label,
             "count": c, "frequency": c / n}
            for (kind, code, gw, label), c in counts.items()]
    out = pd.DataFrame(rows, columns=list(FREQ_COLUMNS))
    return out.sort_values(["kind", "frequency", "code"],
                           ascending=[True, False, True]).reset_index(
                               drop=True)
