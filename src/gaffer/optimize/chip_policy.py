"""When to play a chip: optimal stopping instead of a flat bar.

``CHIP_PLAY_THRESHOLD = 4.0`` asks the wrong question. It asks "is this chip
worth four points this week", when the question is "is this chip worth more
this week than the best week still to come". A bench boost worth five points in
September clears a flat four-point bar and gets burned, three months before the
December doubles it exists for.

The right bar is the option value of waiting, and it has a standard form::

    theta_T = 0
    theta_t = E[max(S_{t+1}, theta_{t+1})]

theta_T = 0 is what guarantees no chip is ever stranded: in the last week of
its window the bar is zero, so any positive surplus plays it. Everywhere else
the bar is the expected value of the best remaining opportunity, so an early
chip has to beat December to get played in September.

The per-week surplus distributions come from replay (``calibrate_decisions``),
so double and blank gameweeks are in the tail as history recorded them rather
than as anyone's guess. ``data/chip_scenarios.toml`` can shift that tail
forward when the season's real double gameweeks become knowable (see
:func:`apply_dgw_scenarios`).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

FIRST_HALF_LAST_GW = 19
"""Last gameweek of the first chip half.

2026/27 grants two of every chip; the first set expires after GW19 and a fresh
set arrives for GW20. A chip's stopping problem therefore runs to 19 or to 38,
never across the boundary.
"""

SEASON_LAST_GW = 38

CHIP_SCENARIOS_PATH = Path("data/chip_scenarios.toml")
"""Optional per-gameweek double-gameweek probabilities.

Absent today and expected to stay absent until the Crellin-style fixture
projections land around January. The hook exists so that populating it is a
data change rather than a code change; see spec §6 and §10.
"""

DGW_SURPLUS_MULTIPLIER = 2.0
"""How much a double gameweek is worth relative to a single one, for the
purpose of shifting a future week's surplus distribution.

A chip that plays over two fixtures instead of one roughly doubles its
surplus — a bench boost boosts twice as many bench appearances, a triple
captain triples twice. Deliberately crude: the scenario file supplies the
*probability*, and this supplies the magnitude, and neither is worth
over-fitting until the file actually exists.
"""


def chip_windows(gw: int) -> tuple[int, int]:
    """``(first, last)`` gameweek of the chip window containing ``gw``."""
    if gw <= FIRST_HALF_LAST_GW:
        return (gw, FIRST_HALF_LAST_GW)
    return (gw, SEASON_LAST_GW)


def stopping_thresholds(surplus_by_gw: dict[int, list[float]], last_gw: int,
                        first_gw: int | None = None) -> dict[int, float]:
    """``theta_t`` for every week in ``[first_gw, last_gw]``.

    ``surplus_by_gw`` maps a gameweek to an empirical sample of that week's
    chip surplus. A week with no samples contributes nothing to the
    expectation but does not truncate the recursion — a gap in the calibration
    is missing information, not a claim that the week is worthless.

    Thresholds are clamped at zero: a negative bar would mean "play this chip
    even though it loses points", which is never the recommendation.
    """
    start = first_gw if first_gw is not None else (
        min(surplus_by_gw) if surplus_by_gw else last_gw)
    theta: dict[int, float] = {last_gw: 0.0}
    for t in range(last_gw - 1, start - 1, -1):
        nxt = surplus_by_gw.get(t + 1) or []
        ahead = theta[t + 1]
        if not nxt:
            theta[t] = ahead
            continue
        theta[t] = max(0.0, sum(max(s, ahead) for s in nxt) / len(nxt))
    return {t: theta[t] for t in range(start, last_gw + 1)}


def load_chip_scenarios(path: Path | str = CHIP_SCENARIOS_PATH
                        ) -> dict[int, float]:
    """``{gw: P(double gameweek)}`` from the optional scenario file.

    Expected shape::

        [dgw]
        26 = 0.7
        29 = 0.4

    Returns ``{}`` when the file is absent, which is the normal case for most
    of a season and must never be an error.
    """
    p = Path(path)
    if not p.exists():
        return {}
    raw = tomllib.loads(p.read_text())
    return {int(gw): float(prob)
            for gw, prob in raw.get("dgw", {}).items()}


def apply_dgw_scenarios(surplus_by_gw: dict[int, list[float]],
                        dgw_probs: dict[int, float]
                        ) -> dict[int, list[float]]:
    """Shift future weeks' surplus samples by their double-gameweek mass.

    A week believed to be a double with probability ``p`` gets a mixture: the
    original samples with weight ``1 - p``, and the same samples scaled by
    :data:`DGW_SURPLUS_MULTIPLIER` with weight ``p``. Because the recursion
    consumes the samples as an unweighted empirical distribution, the mixture
    is realized by *duplication* — a 70% belief becomes seven scaled copies
    against three plain ones.

    Weeks not named in the file are untouched. The historical replay
    distribution already contains real double gameweeks, so an empty file
    leaves a perfectly usable prior rather than a fixture-blind one.
    """
    if not dgw_probs:
        return dict(surplus_by_gw)
    out = dict(surplus_by_gw)
    for gw, prob in dgw_probs.items():
        base = surplus_by_gw.get(gw)
        if not base:
            continue
        p = min(max(float(prob), 0.0), 1.0)
        n_dgw = int(round(p * 10))
        mixed = base * (10 - n_dgw)
        mixed += [s * DGW_SURPLUS_MULTIPLIER for s in base] * n_dgw
        out[gw] = mixed
    return out


FLAT_SOURCE = "flat: no calibrated priors asset"
"""Why a bar is the pre-v4c constant. One string, so the caption and the
fallback cannot drift apart."""


EMPTY_SURPLUS_SOURCE = "flat: priors asset has no usable chip_surplus"
"""Why a bar is flat when the asset *exists* and says nothing usable.

Deliberately not :data:`FLAT_SOURCE` (v12 W3 T4-T7 review, Minor 7): "there is
no calibrated priors asset" and "the asset is here and its ``chip_surplus`` is
empty or unparseable" are different problems with different fixes — install the
asset, or find out why calibration wrote nothing into it — and a caption that
reports the first for the second sends its reader to the wrong one.
"""


def flat_thresholds(reason: str = FLAT_SOURCE):
    """The pre-v4c bars, as a ``(chip, gw) -> float`` callable.

    This is the degradation rail for the whole workstream: with no priors
    asset, every caller gets exactly the constants it used before, including
    their indifference to the calendar.

    ``reason`` is what ``explain`` reports as the source, defaulted so every
    existing caller is unchanged. The one caller that overrides it is
    :func:`chip_thresholds_from_asset`, which reaches this function by a route
    :data:`FLAT_SOURCE` would misdescribe.
    """
    from gaffer.optimize.chips import (CHIP_PLAY_THRESHOLD,
                                       WILDCARD_RECOMMEND_THRESHOLD)

    def lookup(chip: str, gw: int) -> float:
        return (WILDCARD_RECOMMEND_THRESHOLD if chip == "wildcard"
                else CHIP_PLAY_THRESHOLD)

    # v12 W3 §4.2 (specs/2026-09-01-gaffer-v12-program-design.md): a caption
    # cannot say "θ" or "flat fallback" unless the lookup can be asked. An
    # attribute rather than a wrapper type, so every existing caller — which
    # calls this thing — keeps calling it.
    lookup.explain = lambda chip, gw: (lookup(chip, gw), reason)
    return lookup


def thresholds_from_priors(chip_surplus: dict[str, dict[int, list[float]]],
                           dgw_probs: dict[int, float] | None = None):
    """A ``(chip, gw) -> theta`` callable built from calibrated distributions.

    ``chip_surplus`` is ``{chip: {gw: [surplus samples]}}``. Each chip is
    solved twice — once over the GW1-19 window and once over GW20-38 — because
    a chip held in the first half cannot be saved for the second.

    An unknown chip, a chip with no samples at all, *or* a gameweek the table
    does not cover falls through to :func:`flat_thresholds` rather than to
    zero: no calibration is a reason to keep the old bar, not a reason to play
    the chip on any positive surplus. A bar of 0.0 is the most permissive
    number in the system and is not something a missing key should produce.
    """
    flat = flat_thresholds()
    tables: dict[str, dict[int, float]] = {}
    for chip, by_gw in chip_surplus.items():
        shifted = apply_dgw_scenarios(by_gw, dgw_probs or {})
        first = stopping_thresholds(shifted, last_gw=FIRST_HALF_LAST_GW,
                                    first_gw=1)
        second = stopping_thresholds(shifted, last_gw=SEASON_LAST_GW,
                                     first_gw=FIRST_HALF_LAST_GW + 1)
        tables[chip] = {**first, **second}

    def lookup(chip: str, gw: int) -> float:
        return explain(chip, gw)[0]

    # v12 W3 §4.2 (specs/2026-09-01-gaffer-v12-program-design.md): three
    # distinct fallbacks live in this function and every one of them was
    # silent. Named here so the caption can say *why* a bar is flat, which is
    # the half of the spec's sentence a boolean could not carry.
    def explain(chip: str, gw: int) -> tuple[float, str]:
        table = tables.get(chip)
        if not table:
            return (flat(chip, gw),
                    "flat: no calibrated surplus for this chip")
        value = table.get(int(gw))
        if value is None:
            return (flat(chip, gw),
                    "flat: gameweek outside the calibrated window")
        return (float(value), "theta")

    lookup.explain = explain
    return lookup


def chip_thresholds_from_asset(priors: dict | None,
                               dgw_probs: dict[int, float] | None = None):
    """``(chip, gw) -> theta`` from a decision-priors payload.

    The asset stores gameweeks as JSON object keys, which are strings; this is
    where they become integers. ``None`` or an empty ``chip_surplus`` gives
    :func:`flat_thresholds`, which is the pre-v4c behaviour exactly.

    The two routes there report *different* sources (v12 W3 T4-T7 review,
    Minor 7): no asset is :data:`FLAT_SOURCE`, an asset whose ``chip_surplus``
    is empty or unparseable is :data:`EMPTY_SURPLUS_SOURCE`. The bars are the
    same and the fixes are not.
    """
    if not priors:
        return flat_thresholds()
    raw = priors.get("chip_surplus") or {}
    parsed = {chip: {int(gw): [float(s) for s in samples]
                     for gw, samples in by_gw.items()}
              for chip, by_gw in raw.items() if by_gw}
    if not parsed:
        return flat_thresholds(EMPTY_SURPLUS_SOURCE)
    return thresholds_from_priors(parsed, dgw_probs)


UNKNOWN_SOURCE = "unknown"
"""A lookup that predates :func:`threshold_with_source`. Callers print the
bar and say nothing about where it came from, which is honest; inventing
"theta" for it would not be."""


def threshold_with_source(thresholds, chip: str,
                          gw: int) -> tuple[float, str]:
    """``(bar, source)`` for any ``(chip, gw) -> float`` callable.

    ``source`` is ``"theta"`` when the calibrated stopping rule answered, and
    a ``"flat: <reason>"`` string when it did not. A callable with no
    ``explain`` — a test's lambda, a lookup built before v12 — answers
    :data:`UNKNOWN_SOURCE` rather than raising: this is display metadata and
    must never be the reason a chip table fails to render.

    v12 W3 §4.2 (specs/2026-09-01-gaffer-v12-program-design.md).
    """
    explain = getattr(thresholds, "explain", None)
    if explain is None:
        return (float(thresholds(chip, int(gw))), UNKNOWN_SOURCE)
    bar, source = explain(chip, int(gw))
    return (float(bar), str(source))
