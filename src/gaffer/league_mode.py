"""Rank-aware strategy for the mini-league (spec 2026-08-26 §3-§5).

z is the deficit to the *win condition* in units of remaining-horizon margin
spread, and lam = LAMBDA_CAP * tanh(|z| / Z_SCALE) * sign(z). Positive lam
chases (favor players the threats do not own), negative defends (cover them),
zero leaves the optimizer exactly at v1 points-max.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

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

THREAT_SIGMAS = 3.0
"""Ahead: rivals more than this many sigma-root-W back are not threats."""


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
    # --- v4d, appended last and defaulted so positional callers still work --
    z: float = 0.0
    sigma_m: float = SIGMA_FALLBACK
    cover_weights: dict = field(default_factory=dict)


def _sign(x: float) -> float:
    return 1.0 if x > 0 else (-1.0 if x < 0 else 0.0)


def threat_weights(my_total: int, rivals: pd.DataFrame,
                   sigmas: dict[int, float], weeks_left: int,
                   params: LeagueParams | None = None) -> dict[int, float]:
    """rival entry -> threat weight, summing to 1.

    Behind, the relevant side is the leader alone: he is the win condition.
    Ahead, it is every rival within ``THREAT_SIGMAS`` normalized units behind
    me, softmaxed on ``-|gap_r| / (sigma_mr * sqrt(W))`` so a rival 200 points
    adrift contributes nothing. A rivals frame with no ``entry`` column (the
    report-only shape) yields no weights rather than raising.
    """
    p = params or LeagueParams()
    if rivals.empty or "entry" not in rivals.columns:
        return {}
    root = math.sqrt(max(1, weeks_left))
    fallback = _bounded(SIGMA_FALLBACK, p)
    scored = []
    for _, row in rivals.iterrows():
        entry, total = int(row["entry"]), int(row["total"])
        sigma = sigmas.get(entry, fallback)
        scored.append((entry, total, (my_total - total) / (sigma * root)))
    if max(total for _, total, _ in scored) > my_total:
        leader = max(scored, key=lambda s: s[1])
        return {leader[0]: 1.0}
    relevant = [s for s in scored if 0.0 <= s[2] <= THREAT_SIGMAS]
    if not relevant:
        nearest = min(scored, key=lambda s: abs(s[2]))
        return {nearest[0]: 1.0}
    shift = max(-s[2] for s in relevant)          # softmax, numerically safe
    exps = {s[0]: math.exp(-s[2] - shift) for s in relevant}
    total_exp = sum(exps.values())
    return {entry: value / total_exp for entry, value in exps.items()}


def cover_table(rival_picks: dict[int, list[dict]],
                weights: dict[int, float]) -> dict[int, float]:
    """element -> covered fraction in [0, 1] over the rivals that matter.

    ``own`` is 0 (benched or unowned), 1 (owned) or 2 (captained): captaincy
    counts double, and a triple captain is still 2. The sum is clamped to
    [0, 1] *after* weighting, exactly as ``min(EO%/100, 1)`` clamped league EO.
    With equal weights and no armbands this reduces to league EO / 100.
    """
    out: dict[int, float] = {}
    for entry, picks in rival_picks.items():
        weight = weights.get(int(entry))
        if not weight:
            continue
        for pick in picks:
            own = min(int(pick.get("multiplier", 0)), 2)
            if own <= 0:
                continue
            element = int(pick["element"])
            out[element] = out.get(element, 0.0) + weight * own
    return {element: min(value, 1.0) for element, value in out.items()}


def captain_cover(rival_picks: dict[int, list[dict]],
                  weights: dict[int, float]) -> dict[int, float]:
    """element -> weighted share of the threats who captain him."""
    out: dict[int, float] = {}
    for entry, picks in rival_picks.items():
        weight = weights.get(int(entry))
        if not weight:
            continue
        for pick in picks:
            if int(pick.get("multiplier", 0)) >= 2:
                element = int(pick["element"])
                out[element] = out.get(element, 0.0) + weight
    return {element: min(value, 1.0) for element, value in out.items()}


def cover_from_eo(eo_pct: dict[int, float]) -> dict[int, float]:
    """League EO percent -> the v1 cover fraction. The old tilt, one table
    away: it is what ``cover_table`` reduces to under equal weights."""
    return {key: min(float(value) / 100.0, 1.0)
            for key, value in eo_pct.items()}


def compute_strategy(my_total: int, rivals: pd.DataFrame, current_gw: int,
                     history=None, my_entry: int | None = None,
                     params: LeagueParams | None = None) -> Strategy:
    """The dial: z against the whole league, then lam = cap * tanh(z / scale).

    Behind the leader, z is the normalized deficit to the one entry standing
    between me and the title. Ahead of everyone, z is minus the *nearest*
    threat in normalized units — the rival with the largest P(catch me),
    which is not always the rival with the largest total.

    ``history`` and ``my_entry`` are optional: without them every sigma is
    the pin, which is exactly the pre-v4d spread.
    """
    p = params or LeagueParams()
    weeks = max(1, LAST_GW - current_gw + 1)
    if rivals.empty:
        return Strategy(0.0, 0, weeks, "neutral", "")
    sigmas = (margin_sigma(history, my_entry, p)
              if history is not None and my_entry is not None else {})
    root = math.sqrt(weeks)
    fallback = _bounded(SIGMA_FALLBACK, p)

    def sigma_of(row) -> float:
        if "entry" not in row.index:
            return fallback
        return sigmas.get(int(row["entry"]), fallback)

    top = rivals.sort_values("total", ascending=False).iloc[0]
    if int(top["total"]) > my_total:
        rival_row = top
        sigma_m = sigma_of(top)
        z = (int(top["total"]) - my_total) / (sigma_m * root)
        gap = int(top["total"]) - my_total
    else:
        rival_row, sigma_m, nearest = None, fallback, None
        for _, row in rivals.iterrows():
            sigma = sigma_of(row)
            norm = (my_total - int(row["total"])) / (sigma * root)
            if nearest is None or norm < nearest:
                rival_row, sigma_m, nearest = row, sigma, norm
        z = -nearest
        gap = my_total - int(rival_row["total"])
    if z == 0.0:
        z = 0.0          # a dead-level league gives -0.0, which reads as a typo
    lam = p.lambda_cap * math.tanh(abs(z) / p.z_scale) * _sign(z)
    stance = "neutral" if lam == 0 else ("chase" if lam > 0 else "defend")
    weights = threat_weights(my_total, rivals, sigmas, weeks, p)
    return Strategy(lam, gap, weeks, stance, str(rival_row["entry_name"]),
                    z=z, sigma_m=sigma_m, cover_weights=weights)


def tilt_ep(ep_by: dict, cover: dict, lam: float) -> dict:
    """Tilted EP for MILP pool construction ONLY. Raw ep is what reports show.

    ``cover`` is the observed-squad cover table from :func:`cover_table`: a
    fraction in [0, 1] per player code, where 1 means "the rivals that matter
    all own him, or captain him". It is clamped again here so a stale or
    hand-built table can never invert the tilt. lam=0 returns an equal dict —
    the v1 points-max solution is reproduced exactly (regression-tested).

    The result is normalized by the board's largest multiplier, ``1 + max(lam,
    0)``, so no tilted value ever exceeds the player's raw ep. That matters
    because the objective is not scale-free: ``hit_cost``, ``ft_value`` and
    ``itb_value`` are priced in *points*, and a chasing lam that multiplied
    every candidate up would quietly discount all three — a 4-point hit
    costing 4 / (1 + lam) tilted points buys transfers nobody sanctioned.
    Chasing therefore leaves the uncovered player at raw ep and marks the
    covered ones down by 1 / (1 + lam); defending (lam < 0) is already
    anchored on the covered player at raw ep, so its scale is 1 and its
    numbers are unchanged.
    """
    if lam == 0.0:
        return dict(ep_by)
    scale = 1.0 + max(lam, 0.0)
    out = {}
    for key, ep in ep_by.items():
        code = key[0]
        covered = min(max(float(cover.get(code, 0.0)), 0.0), 1.0)
        out[key] = ep * (1 + lam * (1 - covered)) / scale
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


def tilted_captaincy(xi: list[int], ep_of: dict[int, float],
                     cap_cover: dict[int, float],
                     lam: float) -> tuple[int, int]:
    """(captain, vice) over the final XI by tilted score.

    ``cap_score_p = ep_p * (1 + lam * (1 - cap_cover_p))``. Behind (lam > 0)
    an unowned armband scores higher; ahead (lam < 0) the threats' armband
    does. At lam = 0 this is argmax raw EP, exactly what v4c produced. Ties
    fall back to raw EP and then to the code, so the answer never depends on
    the order the MILP happened to list the XI in.
    """
    def score(code: int) -> float:
        covered = min(max(float(cap_cover.get(code, 0.0)), 0.0), 1.0)
        return float(ep_of.get(code, 0.0)) * (1 + lam * (1 - covered))

    ranked = sorted(xi, key=lambda c: (-score(c), -float(ep_of.get(c, 0.0)),
                                       int(c)))
    return ranked[0], (ranked[1] if len(ranked) > 1 else ranked[0])


def captaincy_note(lam: float, chosen: int, demoted: int,
                   rival_captains: dict[int, int], weights: dict[int, float],
                   names: dict[int, str]) -> str:
    """The half-sentence the report puts after the captain's name.

    Defending, the armband is covering the heaviest threat who owns it;
    chasing, it is a differential against the heaviest threat who captains
    the man we just demoted. Nothing at all when the tilt changed nothing.
    """
    if lam == 0.0 or chosen == demoted:
        return ""
    target = chosen if lam < 0 else demoted
    owners = [entry for entry, code in rival_captains.items()
              if code == target]
    if lam < 0:
        if not owners:
            return "covering the field's armband"
        who = max(owners, key=lambda e: weights.get(e, 0.0))
        return f"covering {names.get(who, 'a rival')}'s armband"
    if not owners:
        return "differential vs the field"
    who = max(owners, key=lambda e: weights.get(e, 0.0))
    return f"differential vs {names.get(who, 'a rival')}"
