"""Rank-aware strategy for the mini-league (spec 2026-08-24 §3).

lam = sign * LAMBDA_CAP * clamp(|gap| / (2*SIGMA*sqrt(W)) - 0.5, 0, 1)
Positive lam chases (favor differentials), negative defends (mirror rivals),
zero leaves the optimizer exactly at v1 points-max.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

import pandas as pd

SIGMA_FALLBACK = 18.0
"""Per-GW margin sigma when the league has no history at all (GW1)."""

SIGMA = SIGMA_FALLBACK
"""Kept name for the pin: existing callers and tests import SIGMA."""

LAMBDA_CAP = 0.5
Z_SCALE = 1.5
SIGMA_FLOOR = 8.0
SIGMA_CAP = 30.0
SIGMA_MIN_WEEKS = 6
LAST_GW = 38


@dataclass(frozen=True)
class LeagueParams:
    """The dial's constants, defaulted to the pins and overridable by
    ``[league]`` in config.toml. Duck-typed on the config object so that
    league_mode never imports gaffer.config."""

    z_scale: float = Z_SCALE
    lambda_cap: float = LAMBDA_CAP
    sigma_floor: float = SIGMA_FLOOR
    sigma_cap: float = SIGMA_CAP
    sigma_min_weeks: int = SIGMA_MIN_WEEKS

    @classmethod
    def from_config(cls, cfg) -> "LeagueParams":
        return cls(z_scale=float(getattr(cfg, "z_scale", Z_SCALE)),
                   lambda_cap=float(getattr(cfg, "lambda_cap", LAMBDA_CAP)),
                   sigma_floor=float(getattr(cfg, "sigma_floor", SIGMA_FLOOR)),
                   sigma_cap=float(getattr(cfg, "sigma_cap", SIGMA_CAP)),
                   sigma_min_weeks=int(getattr(cfg, "sigma_min_weeks",
                                               SIGMA_MIN_WEEKS)))


def _bounded(sigma: float, params: LeagueParams) -> float:
    return min(max(float(sigma), params.sigma_floor), params.sigma_cap)


def _stdev(series: list[float]) -> float | None:
    """Sample stdev, or None when there is not enough of a series to have one."""
    if len(series) < 2:
        return None
    return float(statistics.stdev(series))


def margin_sigma(history, my_entry: int,
                 params: LeagueParams | None = None) -> dict[int, float]:
    """rival entry -> sigma of the per-GW margin (my points minus theirs).

    Margin sigma is squad-overlap-aware for free: mirrored squads produce
    small margins, so a small sigma, so the same points gap counts for more.
    That is exactly what the flat 18.0 pin got wrong.

    Fallback chain, in order: the rival's own margin series when it has at
    least ``sigma_min_weeks`` shared gameweeks; the pooled league-wide margin
    series when it does not; :data:`SIGMA_FALLBACK` when there is no poolable
    history either. The result is bounded last, so no branch can escape
    ``[sigma_floor, sigma_cap]``.
    """
    p = params or LeagueParams()
    if history is None or len(history) == 0 or "entry" not in history.columns:
        return {}
    mine = history[history["entry"] == my_entry]
    my_points = {int(g): float(pts)
                 for g, pts in zip(mine["gw"], mine["points"])}
    margins: dict[int, list[float]] = {}
    for entry, group in history[history["entry"] != my_entry].groupby("entry"):
        margins[int(entry)] = [my_points[int(g)] - float(pts)
                               for g, pts in zip(group["gw"], group["points"])
                               if int(g) in my_points]
    pooled = [m for series in margins.values() for m in series]
    pooled_sigma = (_stdev(pooled) if len(pooled) >= p.sigma_min_weeks
                    else None)
    out: dict[int, float] = {}
    for entry, series in margins.items():
        own = _stdev(series) if len(series) >= p.sigma_min_weeks else None
        sigma = own if own is not None else pooled_sigma
        out[entry] = _bounded(sigma if sigma is not None else SIGMA_FALLBACK,
                              p)
    return out


@dataclass
class Strategy:
    lam: float
    gap: int
    weeks_left: int
    stance: str          # "chase" | "defend" | "neutral"
    rival_name: str


def compute_strategy(my_total: int, rivals: pd.DataFrame,
                     current_gw: int) -> Strategy:
    weeks = max(1, LAST_GW - current_gw + 1)
    if rivals.empty:
        return Strategy(0.0, 0, weeks, "neutral", "")
    top = rivals.sort_values("total", ascending=False).iloc[0]
    if int(top["total"]) > my_total:
        gap, sign, rival = int(top["total"]) - my_total, +1, str(top["entry_name"])
    else:
        gap, sign, rival = my_total - int(top["total"]), -1, str(top["entry_name"])
    raw = gap / (2 * SIGMA * math.sqrt(weeks)) - 0.5
    lam = sign * LAMBDA_CAP * min(max(raw, 0.0), 1.0)
    stance = "neutral" if lam == 0 else ("chase" if lam > 0 else "defend")
    return Strategy(lam, gap, weeks, stance, rival)


def tilt_ep(ep_by: dict, eo_pct: dict, lam: float) -> dict:
    """Tilted EP for MILP pool construction ONLY. Raw ep is what reports show.

    eo_pct: league effective ownership in percent (captaincy can push >100);
    clamped to [0, 1] as a fraction. lam=0 returns an equal dict — the v1
    points-max solution is reproduced exactly (regression-tested).
    """
    if lam == 0.0:
        return dict(ep_by)
    out = {}
    for key, ep in ep_by.items():
        code = key[0]
        eo1 = min(eo_pct.get(code, 0.0) / 100.0, 1.0)
        out[key] = ep * (1 + lam * (1 - eo1))
    return out


def win_probability(my_total: int, their_total: int, weeks_left: int) -> float:
    """P(I finish above them): normal approximation, independent scores."""
    if weeks_left <= 0:
        return 1.0 if my_total >= their_total else 0.0
    z = (my_total - their_total) / (SIGMA * math.sqrt(2 * weeks_left))
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def explain_lam(strategy: Strategy) -> str:
    """The tilt in a sentence, for the League Race panel (spec §3.3)."""
    if strategy.stance == "chase":
        return (f"λ {strategy.lam:+.2f}: you are {strategy.gap} points behind "
                f"{strategy.rival_name} with {strategy.weeks_left} gameweeks "
                f"left, so the optimizer favours differentials — players your "
                f"rivals do not own.")
    if strategy.stance == "defend":
        return (f"λ {strategy.lam:+.2f}: you are {strategy.gap} points ahead "
                f"of {strategy.rival_name} with {strategy.weeks_left} "
                f"gameweeks left, so the optimizer leans to mirror rival "
                f"ownership and protect the lead.")
    return (f"λ 0.00: the gap to {strategy.rival_name} is inside the noise, "
            f"so there is no tilt at all — this is the plain points-max plan.")
