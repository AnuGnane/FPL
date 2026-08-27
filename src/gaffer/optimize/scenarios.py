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

import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd

from gaffer.assets import load_scenario_noise
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

SIGMA_MAX = 10.0
"""Refusal bound on a fitted σ.

A residual standard deviation of ten points on a weekly FPL forecast is not a
volatile player, it is a broken table — and the heuristic is a better answer
than a broken table. Matches the validator in
:mod:`gaffer.calibrate_noise`, deliberately: the write side refuses to
produce one and the read side refuses to use one.
"""


CALIBRATED_NOISE_DEFAULT = False
"""Whether :func:`scenario_noise` serves the fitted σ table by default.

**Off, because gate S1 failed.** The 2025-26 gated replay, identical seeds,
scenario gating injected at the replay's base solve, scored heuristic 1785 /
15 hits / 69 transfers against calibrated 1761 / 26 hits / 77 transfers: a
24-point loss where the tolerance was 5. Not a wash — a clear regression, and
in the direction that names its own cause.

The diagnosis is in what σ was fitted on. The calibration regresses realized
points minus EP, and that residual is *two* things added together: how wrong
the forecast was, and how much football would have varied even from a perfect
forecast. Only the first is decision-relevant — a scenario sweep asks "would
this transfer survive my forecast being wrong", not "would it survive the ball
going in". Fitting on outcomes conflates them, so every σ in the table is too
large, and a sweep run at that scale finds nothing robust. The live symptom
was exactly that: captain sim-support collapsed from 92% to 22% and the gate,
finding no move that cleared threshold on its own, advised a plan carrying
-20 in hits.

The asset stays shipped and the mean-preserving serving path stays wired, both
so this can be re-measured rather than rediscovered. The re-measurement a
future cycle wants is an *estimation-only* σ — ensemble spread across refits,
or a bootstrap over the training window — which prices how much the model's
own estimate moves rather than how much the world does. Flip this constant (or
pass ``table=`` explicitly) to serve the table again.
"""


@lru_cache(maxsize=1)
def scenario_noise() -> dict | None:
    """The shipped residual-σ table, read once per process.

    Cached because a scenario sweep calls :func:`noise_ep` once per player per
    gameweek per scenario — tens of thousands of times — and re-reading a JSON
    file for each of them would cost more than the solves.

    With :data:`CALIBRATED_NOISE_DEFAULT` off this returns ``None`` **without
    touching the asset**: the S1 result is that the fitted table is the wrong
    scale to plan on, and a switch that still read the file would leave the
    failure one stale cache away from coming back. Callers that want the table
    anyway pass it to :func:`noise_ep` explicitly.

    Otherwise every failure is the same failure: no asset, unreadable asset,
    asset that is not JSON. All of them return ``None``, which every caller
    reads as "use the heuristic".
    """
    if not CALIBRATED_NOISE_DEFAULT:
        return None
    try:
        return load_scenario_noise()
    except Exception as exc:  # noqa: BLE001 — never blocks a sweep
        print(f"scenario noise asset unreadable, using the heuristic: {exc}")
        return None


def bin_index(value: float, edges: list[float]) -> int:
    """Which half-open bin ``value`` falls in, given the left edges.

    ``edges`` are left edges only — ``[0, 2, 3, 4, 6]`` is five bins, the last
    of which runs to infinity. A value below the first edge lands in bin 0
    rather than at -1: expected points cannot be negative, and a stray -0.0
    indexing off the front of the table would silently read the *last* cell.
    """
    idx = 0
    for i, edge in enumerate(edges):
        if float(value) >= float(edge):
            idx = i
    return idx


def sigma_for(table: dict | None, ep_value: float,
              xmins: float) -> float | None:
    """σ for one (EP bin, xMins bin) cell, or ``None`` to use the heuristic.

    Three deep, exactly as the calibration writes it: the cell if it was
    populated (100+ observations), else the EP bin's marginal, else the global
    residual σ. ``None`` at the end of that chain — or for a σ that fails the
    :data:`SIGMA_MAX` sanity bound — hands the caller back to the heuristic
    rather than inventing a scale.
    """
    if not table:
        return None
    ep_edges = [float(e) for e in table.get("ep_edges") or []]
    x_edges = [float(e) for e in table.get("xmins_edges") or []]
    if not ep_edges or not x_edges:
        return None
    i = bin_index(float(ep_value), ep_edges)
    j = bin_index(float(xmins), x_edges)
    cell = (table.get("sigma") or {}).get(f"{i}_{j}")
    if cell is None:
        cell = (table.get("ep_marginal") or {}).get(str(i))
    if cell is None:
        cell = table.get("global")
    if cell is None:
        return None
    try:
        value = float(cell)
    except (TypeError, ValueError):
        return None
    return value if 0.0 < value < SIGMA_MAX else None


_SQRT_2 = math.sqrt(2.0)
_INV_SQRT_2PI = 1.0 / math.sqrt(2.0 * math.pi)

RECENTRE_TOL = 1e-9
RECENTRE_MAX_ITER = 40
"""Newton budget for :func:`recentred_mean`. Eight is typical; forty is the
refusal point, and it returns its best shift rather than raising — a scenario
sweep must not die of an arithmetic corner."""


def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / _SQRT_2))


def _norm_pdf(z: float) -> float:
    return _INV_SQRT_2PI * math.exp(-0.5 * z * z)


def recentred_mean(ep: float, sigma: float) -> float:
    """The shifted mean ``mu`` with ``E[max(0, mu + sigma Z)] == ep``.

    The calibrated path adds an *absolute* σ, so on a low-EP player the draw
    crosses zero often and the clip only ever pushes upward. Left alone that
    is a systematic upward bias, worst exactly where the table is thickest:
    at σ = 0.83 an EP of 0.05 comes back with a mean of 0.38, so every bench
    player in the pool is quietly handed a third of a point the forecast never
    gave him and the sweep's frequencies are read off a board nobody predicted.

    A censored normal has mean ``mu * Phi(mu/sigma) + sigma * phi(mu/sigma)``,
    which is increasing and convex in ``mu`` with derivative exactly
    ``Phi(mu/sigma)``. So Newton from ``mu = ep`` — where the value is always
    too high, because clipping can only raise a mean — descends monotonically
    onto the unique root.

    ``ep <= 0`` has no such shift (a clipped normal's mean is strictly
    positive for any finite ``mu``) and is handled by the caller, which leaves
    the cell at zero.
    """
    if not sigma > 0.0 or not ep > 0.0:
        return float(ep)
    mu = float(ep)
    for _ in range(RECENTRE_MAX_ITER):
        z = mu / sigma
        cdf = _norm_cdf(z)
        gap = mu * cdf + sigma * _norm_pdf(z) - ep
        if abs(gap) <= RECENTRE_TOL:
            break
        if cdf <= 1e-12:
            # Newton has walked into the flat tail; step back toward the
            # live region by hand rather than dividing by nearly nothing.
            mu += sigma
            continue
        mu -= gap / cdf
    return mu


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
             rng: np.random.Generator,
             table: dict | None = None) -> dict[tuple[int, int], float]:
    """One noised copy of an EP table.

    Two scales, one draw. Where the calibrated table has something to say,
    ``ep_noised = max(0, mu + σ(ep bin, xMins bin) * N(0, 1))`` — σ is an
    empirical residual standard deviation in *points*, so it is absolute and
    is not multiplied by the EP again, and ``mu`` is
    :func:`recentred_mean`'s shift, chosen so the *clipped* draw still
    averages ``ep``. Without it the clip is a one-way ratchet on every low-EP
    player and the sweep noises a board whose expected points are not the
    forecast's. Where the table has nothing to say (no asset, an unpopulated
    cell with no fallback, a σ that fails the sanity bound) the pre-v6
    heuristic stands: ``ep + ep * (92 - xmins) / 134 * N(0, 1)``, which needs
    no recentring because its scale is multiplicative and vanishes with the EP
    it is applied to.

    The draw is taken **before** the branch on purpose. Both paths consume
    exactly one standard normal per cell, so a seed produces the same sequence
    of draws either way and the two arms of gate S1 differ in the scale
    applied to them and in nothing else.

    No cross-gameweek correlation: a player's *minutes* risk really is close
    to independent week to week once the fixture is known, and spec §10 lists
    correlation as YAGNI until the simple version proves insufficient.

    Clipped at zero because a negative EP is not a worse player, it is an
    incoherent one — the MILP would want to leave a squad slot empty, which it
    cannot do, so it would distort the whole board instead.

    Cells with no xMins entry pass through untouched: "we have no minutes
    prediction for this player" is not the same claim as "his minutes are
    certain", and inventing a scale for him would be the worse error.

    ``table`` of ``None`` defers to :func:`scenario_noise`, which since gate
    S1 answers ``None`` — so the default really is the heuristic. Pass a table
    explicitly to price a whole sweep off a single load, or to opt into the
    calibrated arm.
    """
    if table is None:
        table = scenario_noise()
    out: dict[tuple[int, int], float] = {}
    for key, value in ep.items():
        xm = xmins.get(key)
        if xm is None:
            out[key] = value
            continue
        draw = float(rng.standard_normal())
        sigma = sigma_for(table, value, xm)
        if sigma is None:
            scale = (NOISE_FLOOR_XMINS - xm) / NOISE_DENOM
            out[key] = max(0.0, value + value * scale * draw)
        elif value > 0.0:
            out[key] = max(0.0, recentred_mean(value, sigma) + sigma * draw)
        else:
            # An EP of zero has no mean to preserve: every clipped draw round
            # it is non-negative, so any noise at all would invent points.
            out[key] = 0.0
    return out


def noised_pool(pool: pd.DataFrame, xmins: dict[tuple[int, int], float],
                rng: np.random.Generator,
                table: dict | None = None) -> pd.DataFrame:
    """A copy of the candidate pool with every ``ep`` dict noised.

    The *pool* is noised rather than rebuilt from noised EP, and that is a
    deliberate choice rather than a shortcut: ``build_pool`` applies a top-N
    filter per position, so rebuilding it per scenario would change which
    players are even candidates from one scenario to the next, and a move
    frequency computed across scenarios with different candidate sets is
    counting incomparable things. Fixing the board and varying only the values
    on it is what makes the frequencies mean something.

    The σ table is resolved once here rather than once per player: the loader
    is cached, but the lookup through it is not free at pool scale.
    """
    if table is None:
        table = scenario_noise()
    out = pool.copy()
    cells = []
    for code, cell in zip(pool["code"], pool["ep"]):
        keyed = {(int(code), int(gw)): float(v) for gw, v in cell.items()}
        noised = noise_ep(keyed, xmins, rng, table=table)
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
