"""EP bands and haul/blank probabilities: what he might actually score.

The question a band on a forecast is read as is "what might he score". There
is a second, narrower question — "how far would this number move if I refit
the model" — and v8g's first cut answered that one by accident.

It answered it defensibly. The scenario sweep perturbs every EP cell by a σ
out of ``optimize.scenarios``' calibrated table and re-solves, so drawing the
band off that same σ meant the picture on the page was exactly the
distribution the optimizer consumes. The trouble is what the numbers came out
as. That table is *estimation* σ — ``calibrate_noise`` measures how far
gaffer's own forecast of a cell moves when the ensemble is reseeded, and it
says so out loud: cell 0_0 is 0.018 over most of the pool, and the widest cell
in the shipped asset is 0.37. A band of ±0.25 on a 5.9-point forecast is
narrower than the rounding on the headline it decorates, and every tail read
off it collapsed: a nailed-on twelve-point captain came back as a *certain*
haul, a keeper as a *certain* blank. Those are claims about football that no
model is entitled to make.

So the distribution here is the one :func:`gaffer.league_sim.element_sigmas`
already ships on the League tab, and for the same reason it was introduced
there — two variances of independent things, added:

* **Outcome.** :data:`~gaffer.league_sim.OUTCOME_VAR_PER_EP` times the
  expected points. Whether the goal goes in, whether the clean sheet holds,
  who takes the bonus. Measured over three seasons of ``player_gw``, and an
  order of magnitude larger than the other term.
* **Estimation.** :func:`gaffer.optimize.scenarios.sigma_for` over the shipped
  table, falling back cell by cell to the pre-v6 heuristic exactly as
  ``noise_ep`` does. How far the *forecast* moves — real, and small.

Both are imported by name; nothing in ``optimize/**`` or ``league_sim`` is
edited or reached into.

Three consequences worth stating rather than discovering.

The band is **wide by construction**. At five expected points σ is about four,
and the interquartile range spans roughly three points either side. That is
not a defect in the model; it is what a footballer's week looks like, and a
tool that drew it narrower would be lying about the easiest thing in FPL to
check.

The band is **not symmetric about the headline EP**. The outcome σ is
absolute, so the clip at zero pushes only upward, and ``recentred_mean``
shifts the centre down so the clipped draw still averages the forecast. That
is why every label in the UI reads "p25-p75" and never "plus or minus".

**xMins reaches the band through the EP, not around it.** The shipped σ table
is close to flat across xMins bins at a fixed EP — 0.278 at ten expected
minutes against 0.257 at eighty-eight — so at *equal* EP a rotation risk and a
nailed-on starter get nearly the same absolute band. What separates them is
that the rotation risk's EP is lower in the first place, which narrows the
absolute band and widens the relative one. The estimation term still moves
with xMins on the heuristic arm, where the scale is ``ep * (92 - xmins) /
134``; it is simply not the term doing the work.

:func:`estimation_sigma_for` keeps the narrower quantity available on its own,
because the sensitivity card's decision line genuinely does ask "how wrong
might my forecast be" and must not have football's variance mixed into it.

Serve-time only. Nothing here is a trained feature, nothing is banked, and
nothing writes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from gaffer.league_sim import OUTCOME_VAR_PER_EP
from gaffer.optimize.scenarios import (NOISE_DENOM, NOISE_FLOOR_XMINS,
                                       recentred_mean, scenario_noise,
                                       sigma_for, xmins_by_player_gw)

__all__ = ["BAND_Z", "BLANK_POINTS", "HAUL_POINTS", "Band", "band_for",
           "bands_by_player_gw", "estimation_sigma_for", "shipped_table",
           "xmins_by_player_gw"]

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

    ``p_haul`` here is P(total points >= ``HAUL_POINTS``) in the tail of a
    normal on the *whole* forecast — cards, minutes, clean sheets and all. It
    is not :func:`gaffer.models.assemble.p_haul`, which is P(2+ attacking
    returns) under a Poisson on expected goals plus assists and knows nothing
    about a defender's week. Both were served under the name ``p_haul`` on one
    page until v9c; this one keeps it (``/api/players``, ``/api/components``)
    and the attacking one leaves the process as ``p_attacking_haul`` (spec D3).
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


def _estimation_sigma(ep: float, xmins: float, table: dict | None) -> float:
    """How far gaffer's own forecast of this cell moves. The smaller term.

    The branch is ``noise_ep``'s branch, in the same order and on the same
    condition, because the two must never disagree about which estimation
    scale applies to a given player — and because the sensitivity card's
    decision line is this quantity and nothing else.
    """
    sigma = sigma_for(table, ep, xmins)
    if sigma is None:
        # The pre-v6 heuristic: multiplicative, and vanishing at 92 xMins.
        return ep * (NOISE_FLOOR_XMINS - xmins) / NOISE_DENOM
    return float(sigma)


def _moments(ep: float, xmins: float,
             table: dict | None) -> tuple[float, float]:
    """``(mu, sigma)`` of the clipped normal this player's week is drawn from.

    Variances of independent things, added — the same quadrature
    :func:`gaffer.league_sim.element_sigmas` does, mirrored rather than
    imported because that function answers per *element* over a whole horizon
    and this one answers per (player, gameweek).

    ``recentred_mean`` on both arms now, unlike v8g's first cut. The old
    heuristic arm skipped it because a multiplicative σ vanishing with its own
    EP never pushed the clip; the outcome term is absolute and does, on every
    player in the pool.
    """
    est = max(_estimation_sigma(ep, xmins, table), 0.0)
    sigma = math.sqrt(OUTCOME_VAR_PER_EP * max(ep, 0.0) + est * est)
    return recentred_mean(ep, sigma), sigma


def _clean(ep, xmins) -> tuple[float, float] | None:
    """``(ep, clipped xmins)`` or ``None`` for a cell nothing can be said of.

    One parser, so :func:`band_for` and :func:`estimation_sigma_for` refuse
    the same inputs — a card and the line under it disagreeing about which
    players are modelled would be worse than either being absent.
    """
    if xmins is None:
        return None
    try:
        value, xm = float(ep), float(xmins)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or math.isnan(xm):
        return None
    return value, min(max(xm, 0.0), NOISE_FLOOR_XMINS)


def estimation_sigma_for(ep, xmins, table=_SHIPPED) -> float | None:
    """The **estimation** σ alone, in points, or ``None`` for an unusable cell.

    Deliberately not the band's σ. The sensitivity card's decision line asks
    "how wrong might my forecast of the players separating these two plans
    be", and answering it with football's own variance would inflate every
    margin into a coin flip: the two plans are re-solved off the *same* board,
    so an outcome shock that hits one hits the other.

    ``0.0`` for a non-positive EP, mirroring :func:`band_for`'s zero-EP arm —
    the cell is modelled, it is simply not moving.
    """
    if table is _SHIPPED:
        table = shipped_table()
    parsed = _clean(ep, xmins)
    if parsed is None:
        return None
    value, xm = parsed
    if value <= 0.0:
        return 0.0
    return max(_estimation_sigma(value, xm, table), 0.0)


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
    parsed = _clean(ep, xmins)
    if parsed is None:
        return None
    value, xm = parsed
    if value <= 0.0:
        # An EP of zero has no spread to report and no haul to price. Blank is
        # a certainty rather than a probability, and saying so is more use
        # than an em dash.
        return Band(sigma=0.0, ep_lo=0.0, ep_hi=0.0, p_haul=0.0, p_blank=1.0)

    mu, sigma = _moments(value, xm, table)
    if not sigma > 0.0:
        # Unreachable for a positive EP now that the outcome term is in —
        # ``OUTCOME_VAR_PER_EP * ep`` is strictly positive — and kept as the
        # arithmetic guard it always was rather than as a live branch. The
        # 92-xMins starter it used to catch is precisely the player who was
        # coming back as a *certain* haul.
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
