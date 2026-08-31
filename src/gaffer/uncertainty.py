"""EP bands and haul/blank probabilities: the sweep's noise model, displayed.

The optimizer has always had an opinion about how wrong each of its numbers
is — the scenario sweep perturbs every EP cell by its own σ and re-solves
forty times, and that σ is the difference between a transfer that survives
thirty-eight of those worlds and one that survives twelve. Until now the
opinion was consumed and thrown away: the sweep printed a move frequency, and
the number on the squad table was still a bare point estimate with no width.

This module reads the same σ out and shows it. Nothing here is a new model,
and that constraint is the whole design. The distribution is not "a normal
around the EP" — it is literally the one :func:`gaffer.optimize.scenarios.
noise_ep` draws from, ``max(0, mu + σ·Z)``, with ``mu`` the recentred mean on
the calibrated path and the EP itself on the heuristic one. A band drawn any
other way would picture a distribution the optimizer does not use, which is
exactly the dishonesty the feature exists to remove.

Two consequences worth stating rather than discovering.

The band is **not symmetric about the headline EP** on the calibrated path.
The calibrated σ is absolute, so the clip at zero pushes only upward, and
``recentred_mean`` shifts the centre down so the clipped draw still averages
the forecast. That is why every label in the UI reads "p25-p75" and never
"plus or minus".

``p_haul`` and ``p_blank`` are **crude and labelled crude**. They price
forecast error, not football: the σ table says how much the model's own
estimate moves, not how much the ball does. A nailed-on premium's real haul
rate is higher than what comes out of here. The number is still worth showing
because it is consistent with what the optimizer assumes, and "what the
model's own noise model implies" is a claim this tool can actually stand
behind.

Serve-time only. Nothing here is a trained feature, nothing is banked, and
nothing writes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from gaffer.optimize.scenarios import (NOISE_DENOM, NOISE_FLOOR_XMINS,
                                       recentred_mean, scenario_noise,
                                       sigma_for, xmins_by_player_gw)

__all__ = ["BAND_Z", "BLANK_POINTS", "HAUL_POINTS", "Band", "band_for",
           "bands_by_player_gw", "shipped_table", "xmins_by_player_gw"]

BAND_Z = 0.6744897501960817
"""The standard normal's 75th percentile: the half-width of an interquartile
range in units of σ.

p25-p75 rather than a 90% interval on purpose. A quartile band is a claim
about the ordinary week — half the time he lands inside it — which is the
question a manager picking a captain is actually asking. A 90% band on a
rotation risk spans nearly the whole plausible range and tells nobody
anything.
"""

HAUL_POINTS = 10.0
"""What counts as a haul. The community's number, and the one the evaluation's
own return categories already use."""

BLANK_POINTS = 2.0
"""What counts as a blank: an appearance and nothing else. Not zero — a player
who came on and did nothing has blanked from a manager's point of view, and
distinguishing him from an unused substitute is the minutes model's job, not
this one's."""

_SQRT_2 = math.sqrt(2.0)

_SHIPPED = object()
"""Sentinel for "resolve the shipped asset yourself".

:func:`band_for` cannot use ``None`` for this the way ``noise_ep`` does,
because ``None`` is also the perfectly ordinary answer "there is no table,
use the heuristic" — and a caller that has already resolved the asset once
for a whole pool must be able to pass that answer down without every player
re-entering the loader.
"""


def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / _SQRT_2))


@dataclass(frozen=True)
class Band:
    """One player-gameweek's spread, as the sweep would draw it.

    ``ep_lo``/``ep_hi`` are quantiles, not a symmetric interval — see the
    module docstring. ``sigma`` travels with them so a caller can say how wide
    the uncertainty is without re-deriving it, and so gate G1 can spot-check
    that a boom-bust attacker carries a larger one than a keeper at equal EP.
    """

    sigma: float
    ep_lo: float
    ep_hi: float
    p_haul: float
    p_blank: float


def shipped_table() -> dict | None:
    """The σ table the scenario sweep serves, or ``None`` for the heuristic.

    One seam, so a rail that pins the sweep's asset optionality also pins this
    module's. Cached by :func:`gaffer.optimize.scenarios.scenario_noise`, so
    calling it once per request rather than once per player is a courtesy
    rather than a necessity — but a pool is several thousand rows and the
    lookup through the cache is not free.
    """
    return scenario_noise()


def _moments(ep: float, xmins: float,
             table: dict | None) -> tuple[float, float]:
    """``(mu, sigma)`` of the clipped normal ``noise_ep`` draws for this cell.

    The branch is `noise_ep`'s branch, in the same order and on the same
    condition, because the two must never disagree about which scale applies
    to a given player.
    """
    sigma = sigma_for(table, ep, xmins)
    if sigma is None:
        # The pre-v6 heuristic: multiplicative, vanishing with the EP it is
        # applied to, and so needing no recentring.
        return ep, ep * (NOISE_FLOOR_XMINS - xmins) / NOISE_DENOM
    return recentred_mean(ep, sigma), float(sigma)


def band_for(ep, xmins, table=_SHIPPED) -> Band | None:
    """One player-gameweek's band, or ``None`` when there is nothing to say.

    ``None`` for a player with no xMins — no minutes model, or a frame that
    never carried one. That is not a band of width zero: ``noise_ep`` passes
    such a cell through untouched precisely because "we have no minutes
    prediction for him" is a different claim from "his minutes are certain",
    and a zero-width band would draw the least-known player in the pool as the
    most certain one on the page.

    ``table`` omitted means "resolve the shipped asset"; ``table=None`` means
    "use the heuristic" and is how a caller pins the degraded arm. Pass a
    resolved table to price a whole pool off one load.
    """
    if table is _SHIPPED:
        table = shipped_table()
    if xmins is None:
        return None
    try:
        value, xm = float(ep), float(xmins)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or math.isnan(xm):
        return None
    if value <= 0.0:
        # An EP of zero has no spread to report and no haul to price. Blank is
        # a certainty rather than a probability, and saying so is more use
        # than an em dash.
        return Band(sigma=0.0, ep_lo=0.0, ep_hi=0.0, p_haul=0.0, p_blank=1.0)

    xm = min(max(xm, 0.0), NOISE_FLOOR_XMINS)
    mu, sigma = _moments(value, xm, table)
    if not sigma > 0.0:
        # A genuinely nailed-on 90-plus-minute starter under the heuristic.
        # The distribution is a point mass, and dividing by it is neither
        # necessary nor possible.
        point = max(0.0, mu)
        return Band(sigma=0.0, ep_lo=round(point, 2), ep_hi=round(point, 2),
                    p_haul=1.0 if point >= HAUL_POINTS else 0.0,
                    p_blank=1.0 if point <= BLANK_POINTS else 0.0)
    return Band(
        sigma=round(sigma, 3),
        ep_lo=round(max(0.0, mu - BAND_Z * sigma), 2),
        ep_hi=round(mu + BAND_Z * sigma, 2),
        p_haul=round(1.0 - _norm_cdf((HAUL_POINTS - mu) / sigma), 4),
        p_blank=round(_norm_cdf((BLANK_POINTS - mu) / sigma), 4))


def bands_by_player_gw(comp: pd.DataFrame | None,
                       table=_SHIPPED) -> dict[tuple[int, int], Band]:
    """``{(code, gw): Band}`` for a component frame.

    Keyed on ``(code, gw)`` and not on ``(code, fixture)``: that is
    ``noise_ep``'s key and ``xmins_by_player_gw``'s key, and a double
    gameweek is one answer to "how uncertain is he this week" rather than two.
    EP is therefore **summed** across a double's fixtures while xMins is
    averaged — his EP really does double, so his absolute noise doubles with
    it, but he is exactly as nailed on either way.

    ``{}`` for anything unusable: no frame, no ``ep``, no minutes model. An
    empty map is a page with no bands on it, which is the correct degraded
    render.
    """
    if comp is None or not isinstance(comp, pd.DataFrame) or comp.empty:
        return {}
    if not {"code", "gw", "ep"}.issubset(comp.columns):
        return {}
    xmins = xmins_by_player_gw(comp)
    if not xmins:
        return {}
    if table is _SHIPPED:
        table = shipped_table()

    frame = pd.DataFrame({
        "code": comp["code"].astype(int), "gw": comp["gw"].astype(int),
        "ep": pd.to_numeric(comp["ep"], errors="coerce").fillna(0.0)})
    totals = frame.groupby(["code", "gw"], as_index=False)["ep"].sum()

    out: dict[tuple[int, int], Band] = {}
    for row in totals.itertuples():
        key = (int(row.code), int(row.gw))
        band = band_for(float(row.ep), xmins.get(key), table=table)
        if band is not None:
            out[key] = band
    return out
