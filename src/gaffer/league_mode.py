"""Rank-aware strategy for the mini-league (spec 2026-08-24 §3).

lam = sign * LAMBDA_CAP * clamp(|gap| / (2*SIGMA*sqrt(W)) - 0.5, 0, 1)
Positive lam chases (favor differentials), negative defends (mirror rivals),
zero leaves the optimizer exactly at v1 points-max.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

SIGMA = 18.0        # per-GW score sigma, pinned; later: estimate from tracking
LAMBDA_CAP = 0.5
LAST_GW = 38


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
