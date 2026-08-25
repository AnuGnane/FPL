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
