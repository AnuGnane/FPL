"""Offline calibration for the v5 injury-return curves.

``RECOVERY = 0.7`` says every injury recovers at the same rate, which is
plainly false: a knock is a week and an ACL is a season, and the flat constant
splits the difference between them badly in both directions. What the horizon
decay actually wants is ``P(returned by h gameweeks | injury type)``, and that
is an empirical distribution nobody has to guess at — Transfermarkt records the
length of every spell.

So it is fitted offline and shipped as ``assets/injury_return_curves.json``,
in git, the same way the v4c decision priors are. A clone without the asset
falls back to the pooled curve and then to the flat constant, which is the
pre-v5 behaviour exactly (spec §7).

Deliberately isolated from the advise path: nothing in ``advise.py`` imports
this module, and it does no work at import time.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ASSET_PATH = Path("src/gaffer/assets/injury_return_curves.json")

CURVE_HORIZON = 8
"""Gameweeks of curve, h = 0..8 inclusive.

Two more than the longest horizon the optimizer plans over, so the decay never
runs off the end of the table and starts extrapolating.
"""

DAYS_PER_GW = 7.0

MIN_SPELLS = 30
"""Spells a type needs before it earns its own curve.

Below this the empirical CDF is a step function through a handful of points,
and a horizon decay swinging on five samples is worse than the pooled curve it
would replace. Under-sampled types simply fall through to ``pooled``.
"""

REQUIRED_KEYS = ("version", "generated_at", "horizon", "curves", "pooled")

CLUBS: dict[str, int] = {}
"""``{transfermarkt club slug: club id}`` for the clubs to scrape.

Left empty on purpose: the Premier League's twenty change every August and a
stale table in git would silently scrape the wrong division. ``run_calibration``
takes the mapping as an argument, and the CLI's ``--clubs`` option points at a
JSON file the user maintains beside their config.
"""


def _cdf(days: pd.Series, horizon: int = CURVE_HORIZON) -> list[float]:
    """``[P(spell <= h weeks) for h in 0..horizon]``, monotone by construction.

    The empirical CDF of the observed spell lengths, evaluated at gameweek
    boundaries. ``h = 0`` asks "was he back before the week he got injured",
    which is never, so a spell of zero days is still a zero here — a player
    who missed no time was not injured for our purposes.
    """
    values = pd.to_numeric(days, errors="coerce").dropna()
    if values.empty:
        return []
    n = float(len(values))
    out = []
    for h in range(horizon + 1):
        share = float((values <= h * DAYS_PER_GW).sum()) / n if h else 0.0
        out.append(round(min(max(share, out[-1] if out else 0.0), 1.0), 4))
    return out


def fit_curves(spells: pd.DataFrame,
               horizon: int = CURVE_HORIZON,
               min_spells: int = MIN_SPELLS) -> dict:
    """Spell lengths -> the asset payload.

    One curve per injury type with at least ``min_spells`` samples, plus a
    pooled curve over every spell for the types that did not qualify and the
    ones the vocabulary has never seen.
    """
    curves = {}
    for itype, group in spells.groupby("injury_type"):
        if len(group) < min_spells:
            continue
        curve = _cdf(group["days_out"], horizon)
        if curve:
            curves[str(itype)] = curve
    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "horizon": int(horizon),
        "spells": int(len(spells)),
        "curves": curves,
        "pooled": _cdf(spells["days_out"], horizon),
    }


def run_calibration(clubs: dict[str, int],
                    cache_dir: Path | None = None) -> dict:
    """Scrape every club's injury history and fit the curves.

    ``clubs`` is ``{transfermarkt slug: club id}``. A club that fails
    contributes nothing and the fit proceeds on the rest — a calibration is
    not worth abandoning over one dead page.
    """
    from gaffer.data.news import NEWS_CACHE
    from gaffer.data.news.transfermarkt import fetch_club_spells

    frames = [fetch_club_spells(slug, club_id,
                                cache_dir=cache_dir or NEWS_CACHE)
              for slug, club_id in clubs.items()]
    frames = [f for f in frames if not f.empty]
    spells = (pd.concat(frames, ignore_index=True) if frames
              else pd.DataFrame(columns=["injury_type", "days_out"]))
    return fit_curves(spells)


def _check_cdf(name: str, curve) -> None:
    """Reject anything shipped as ``P(returned by h)`` that is not one.

    :func:`_cdf` cannot produce a bad curve, which is exactly why this belongs
    at the *write* boundary rather than in the fit: what reaches the asset may
    have been hand-edited, merged from an older schema, or built by a caller
    that fitted its own numbers. Each of the three faults rewrites the horizon
    decay for a whole season and none of them looks wrong in the JSON.
    """
    values = [float(v) for v in curve]
    if values and values[0] != 0.0:
        raise ValueError(
            f"injury curve '{name}' does not start at 0 ({values[0]}) — h=0 "
            "is the gameweek the injury is in, and nobody returns inside it")
    if any(v < 0.0 or v > 1.0 for v in values):
        raise ValueError(
            f"injury curve '{name}' leaves [0, 1] — it is read as a "
            "probability and nothing downstream clamps it")
    if any(b < a for a, b in zip(values, values[1:])):
        raise ValueError(
            f"injury curve '{name}' is not non-decreasing — a return "
            "probability that falls says a player un-returned")


def write_curves(payload: dict, path: Path | str = ASSET_PATH) -> Path:
    """Validate and write the asset.

    Validated before writing for the same reason ``write_priors`` is: an
    absent asset degrades honestly to the flat constant, and a hollow one
    degrades silently — a payload whose pooled curve is empty would answer
    every horizon question with "he is never coming back" and the optimizer
    would sell every flagged player in the game.
    """
    missing = [k for k in REQUIRED_KEYS if k not in payload]
    if missing:
        raise ValueError(
            f"injury curve payload is missing {missing} — refusing to write "
            "a partial asset")
    if not payload["pooled"]:
        raise ValueError(
            "injury curves carry no pooled fallback — every unseen injury "
            "type would decay on nothing")
    for name, curve in [("pooled", payload["pooled"]),
                        *sorted((payload.get("curves") or {}).items())]:
        _check_cdf(name, curve)
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return dest
