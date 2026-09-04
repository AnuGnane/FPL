"""The transfer ladder (v13 §3, specs/2026-09-04-gaffer-v13-transfer-ladder-design.md).

One row per rung of appetite — *bank*, then 0, 1, 2 and 3 hits, and an
*open* row only when the uncapped solve spends more than three — each
solved off the saved board exactly as the What-If lab re-solves it, and
every fixed plan then scored on **one** matrix of noise draws. Shared draws
are what make the rows comparable: the players two rungs have in common
score identically in every draw, so P(rung k beats rung j) is a statement
about the players that differ and nothing else.

The noise is the *outcome* distribution the squad table's bands already show
(:func:`gaffer.uncertainty.bands_by_player_gw`), not the sensitivity card's
narrower estimation σ. "Will two hits actually outscore one" is a question
about what the players score, so the probabilities here are closer to a
coin flip than that card's margins, and the spec chose that on purpose.

The board is built as ``sensitivity.run_sensitivity`` builds it — saved
state, raw EP, the cover table converted from ``league_eo`` when the state
predates it, ``tilt_ep``, ``milp_pool``, ``solve_kw_from_state`` — and the
idiom is repeated rather than shared, for the reason that module records:
two tests pin ``solve_whatif``'s own source text.
"""

from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from gaffer import artifacts
from gaffer.artifacts import (caps_from_state, latest_gw, load_advice,
                              load_components, load_solve_state, milp_pool,
                              raw_ep_by, solve_kw_from_state)
from gaffer.errors import GafferError
from gaffer.io import atomic_write
from gaffer.league_mode import cover_from_eo, tilt_ep
from gaffer.league_sim import OUTCOME_VAR_PER_EP
from gaffer.optimize.milp import GwPlan, Plan, SolveInput, solve_plan
from gaffer.uncertainty import bands_by_player_gw

LADDER_DRAWS = 200
"""Draws per rung. Two hundred resolves a probability to about ±3.5%, which
is the precision the card prints (whole percents) and no finer."""

LADDER_HITS = (0, 1, 2, 3)
"""The hit rungs. Above three the *open* row exists only if the solver wants
it, so the table never lists a rung nobody would take."""

SEED_OFFSET = 2_000_000
"""Two million clear of the advice sweep's ``scenarios_seed + gw`` and one
million clear of the sensitivity sweep's, so the three draw independent
noise rather than replaying each other."""


def ladder_path(gw: int) -> Path:
    return artifacts.REPORTS / f"ladder_gw{gw}.json"


def load_ladder(gw: int) -> dict | None:
    """The banked ladder for ``gw``, or ``None`` — ``load_sensitivity``'s
    contract: a missing report is a card with a rebuild button, not an
    error."""
    path = ladder_path(gw)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001 — a corrupt report is no report
        print(f"ladder report unreadable: {exc}")
        return None


def save_ladder(payload: dict, gw: int) -> Path:
    """Atomic, like every other banked report."""
    artifacts.REPORTS.mkdir(exist_ok=True)
    path = ladder_path(gw)
    atomic_write(path, json.dumps(payload, indent=1, allow_nan=False))
    return path


def signature(first: GwPlan) -> tuple:
    """First-week buys, sells and captain — the decision a rung represents
    (``sensitivity.plan_signature``'s definition)."""
    return (tuple(sorted(int(c) for c in first.buys)),
            tuple(sorted(int(c) for c in first.sells)),
            int(first.captain))


def plan_points(gw_plans: list[GwPlan], ep_by: dict, hit_cost: int) -> float:
    """XI plus the captain again, minus the hits, on **raw** EP — the
    measure ``routers/whatif._summary`` and ``sensitivity.plan_value`` use."""
    total = 0.0
    for plan in gw_plans:
        def ep(code) -> float:
            return float(ep_by.get((int(code), int(plan.gw)), 0.0))

        total += sum(ep(c) for c in plan.xi) + ep(plan.captain)
        total -= plan.hits * hit_cost
    return round(total, 2)


def sigma_table(gw: int) -> tuple[dict[tuple[int, int], float], str]:
    """``{(code, gw): σ}`` off the banked components frame, and where it
    came from. ``{}`` with ``"outcome_only"`` when no frame is banked, and
    :func:`draw_points` then falls back cell by cell."""
    try:
        comp = load_components(gw)
    except Exception as exc:  # noqa: BLE001 — a ladder is not worth a crash
        print(f"ladder: no component breakdown ({exc})")
        return {}, "outcome_only"
    bands = bands_by_player_gw(comp)
    if not bands:
        return {}, "outcome_only"
    return {key: float(band.sigma) for key, band in bands.items()}, "bands"


def draw_points(keys, ep_by: dict, sigmas: dict, rng: np.random.Generator,
                n_draws: int) -> dict[tuple[int, int], np.ndarray]:
    """One vector of ``n_draws`` points per player-week, ``max(0, N(ep, σ))``.

    Keys are visited in sorted order so the draw a player-week receives is a
    function of the seed and the set, never of which rung named him first.
    """
    out: dict[tuple[int, int], np.ndarray] = {}
    for key in sorted(keys):
        mu = float(ep_by.get(key, 0.0))
        sigma = sigmas.get(key)
        if sigma is None:
            sigma = math.sqrt(OUTCOME_VAR_PER_EP * max(mu, 0.0))
        out[key] = np.maximum(0.0, mu + float(sigma)
                              * rng.standard_normal(n_draws))
    return out


def score_plan(gw_plans, draws: dict, hit_cost: int,
               n_draws: int) -> np.ndarray:
    """A fixed plan's horizon points in every draw: XI plus the captain
    again, minus the hits, undecayed, the vice and the bench ignored —
    :func:`plan_points` per draw."""
    total = np.zeros(n_draws)
    for plan in gw_plans:
        gw = int(plan.gw)
        for code in plan.xi:
            total += draws[(int(code), gw)]
        total += draws[(int(plan.captain), gw)]
        total -= float(plan.hits * hit_cost)
    return total


def p_best(scores: dict[str, np.ndarray]) -> dict[str, float]:
    """The share of draws each rung is the maximum in, ties split evenly."""
    keys = list(scores)
    matrix = np.stack([scores[k] for k in keys])            # rungs × draws
    winners = (matrix == matrix.max(axis=0)).astype(float)
    share = winners / winners.sum(axis=0)
    return {k: float(share[i].mean()) for i, k in enumerate(keys)}


def _refs(codes, gw: int, meta: dict, ep_by: dict) -> list[dict]:
    return [{"code": int(c),
             "name": str(meta.get(int(c), {}).get("name", c)),
             "position": str(meta.get(int(c), {}).get("position", "")),
             "ep": round(float(ep_by.get((int(c), int(gw)), 0.0)), 2)}
            for c in codes]


def vs_below(below, rung, *, prev_mean: float, mean: float, hit_cost: int,
             meta: dict, ep_by: dict) -> dict:
    """What the extra hit bought: the first-week moves this rung makes that
    the rung below did not (and any it dropped), the mean-points gain and
    the points it cost."""
    below_buys, buys = set(int(c) for c in below.buys), set(int(c) for c in rung.buys)
    below_sells, sells = set(int(c) for c in below.sells), set(int(c) for c in rung.sells)
    return {
        "extra_buys": _refs(sorted(buys - below_buys), rung.gw, meta, ep_by),
        "extra_sells": _refs(sorted(sells - below_sells), rung.gw, meta, ep_by),
        "dropped_buys": _refs(sorted(below_buys - buys), below.gw, meta, ep_by),
        "dropped_sells": _refs(sorted(below_sells - sells), below.gw, meta,
                               ep_by),
        "delta_mean_pts": round(float(mean - prev_mean), 2),
        "delta_cost": int((int(rung.hits) - int(below.hits)) * hit_cost),
    }


def _week(plan: GwPlan, meta: dict, ep_by: dict, hit_cost: int) -> dict:
    return {"gw": int(plan.gw), "hits": int(plan.hits),
            "buys": _refs(plan.buys, plan.gw, meta, ep_by),
            "sells": _refs(plan.sells, plan.gw, meta, ep_by),
            "xi": _refs(plan.xi, plan.gw, meta, ep_by),
            "bench": _refs(plan.bench, plan.gw, meta, ep_by),
            "captain": _refs([plan.captain], plan.gw, meta, ep_by)[0],
            "vice": _refs([plan.vice], plan.gw, meta, ep_by)[0],
            "expected_pts": plan_points([plan], ep_by, hit_cost)}


def _empty_rung(key: str, hits: int, transfers: int, cost: int,
                same_as: str) -> dict:
    return {"key": key, "hits": hits, "transfers": transfers, "cost": cost,
            "same_as": same_as, "plan_by_gw": [], "week_pts": None,
            "horizon_pts": None, "objective": None, "mean_pts": None,
            "p10_pts": None, "p90_pts": None, "p_beats_bank": None,
            "p_beats_top": None, "p_best": None, "vs_below": None}


def _cap_rung(max_hits: int | None, max_transfers: int | None,
              keys: list[str]) -> str:
    if max_transfers == 0:
        return "bank"
    if max_hits is None or max_hits > max(LADDER_HITS):
        return keys[-1]
    return f"hits{int(max_hits)}"


def _recommended(gw: int, solved: list[tuple[str, Plan]]) -> str | None:
    """The rung whose first-week decision is the served advice's, or None."""
    try:
        advice = load_advice(gw)
        wanted = (tuple(sorted(int(b["code"]) for b in advice.get("buys", []))),
                  tuple(sorted(int(s["code"]) for s in advice.get("sells", []))),
                  int(advice["captain"]["code"]))
    except Exception as exc:  # noqa: BLE001 — no advice is no chip, not a crash
        print(f"ladder: no served advice to mark ({exc})")
        return None
    for key, plan in solved:
        if signature(plan.gw_plans[0]) == wanted:
            return key
    return None


def build_ladder(gw: int | None = None, *, n_draws: int = LADDER_DRAWS,
                 seed: int | None = None) -> dict:
    """Solve every rung off the saved board, score them on shared draws,
    bank the payload. The job body and the end of ``advise``'s run.

    Raises :class:`GafferError` when there is no saved state — the job
    runner's cue to say "run `gaffer advise` first" rather than 500.
    """
    gw = latest_gw() if gw is None else int(gw)
    if gw is None:
        raise GafferError("no saved solve state — run `gaffer advise` first")
    state = load_solve_state(gw)
    horizon = state.opt.get("horizon") or len(state.gws)
    gws = state.gws[:max(1, int(horizon))]
    ep_by = raw_ep_by(state)
    cover = (state.cover if state.cover is not None
             else cover_from_eo(state.league_eo))
    pool = milp_pool(state, tilt_ep(ep_by, cover, state.lam), gws)
    opt = solve_kw_from_state(state)
    hit_cost = int(opt["hit_cost"])
    meta = {int(r.code): {"name": str(r.name), "position": str(r.position)}
            for r in state.pool.drop_duplicates("code").itertuples()}
    if seed is None:
        from gaffer.config import serving_config
        seed = int(serving_config().scenarios_seed) + SEED_OFFSET + int(gw)
    n_draws = max(1, int(n_draws))
    started = time.perf_counter()

    base = dict(owned_codes=state.owned_codes, bank=state.bank,
                free_transfers=state.free_transfers, gws=gws)
    specs: list[tuple[str, SolveInput]] = [
        ("bank", SolveInput(**base, max_transfers=0))]
    specs += [(f"hits{k}", SolveInput(**base, max_hits=k))
              for k in LADDER_HITS]
    specs.append(("open", SolveInput(**base)))

    solved: list[tuple[str, Plan]] = []
    for key, solve_state in specs:
        plan = solve_plan(pool, solve_state, **opt)
        if key == "open" and plan.gw_plans[0].hits <= max(LADDER_HITS):
            continue
        solved.append((key, plan))

    # Distinct rungs solve and score; a rung whose first-week decision is the
    # rung below's is kept as a row that says so and carries no numbers.
    distinct: list[tuple[str, Plan]] = []
    same_as: dict[str, str] = {}
    for key, plan in solved:
        if distinct and signature(plan.gw_plans[0]) == signature(
                distinct[-1][1].gw_plans[0]):
            same_as[key] = distinct[-1][0]
        else:
            distinct.append((key, plan))

    keys_needed: set[tuple[int, int]] = set()
    for _, plan in distinct:
        for week in plan.gw_plans:
            keys_needed.update((int(c), int(week.gw)) for c in week.xi)
            keys_needed.add((int(week.captain), int(week.gw)))
    sigmas, sigma_source = sigma_table(gw)
    rng = np.random.default_rng(int(seed))
    draws = draw_points(keys_needed, ep_by, sigmas, rng, n_draws)
    scores = {key: score_plan(plan.gw_plans, draws, hit_cost, n_draws)
              for key, plan in distinct}
    best = p_best(scores)
    top_key = distinct[-1][0]

    rows: list[dict] = []
    by_key: dict[str, dict] = {}
    prev: tuple[str, Plan] | None = None
    for key, plan in solved:
        if key in same_as:
            src = by_key[same_as[key]]
            row = _empty_rung(key, src["hits"], src["transfers"],
                              src["cost"], same_as[key])
            rows.append(row)
            by_key[key] = row
            continue
        first = plan.gw_plans[0]
        sc = scores[key]
        mean = float(sc.mean())
        row = {
            "key": key, "hits": int(first.hits),
            "transfers": int(len(first.buys)),
            "cost": int(first.hits * hit_cost), "same_as": None,
            "plan_by_gw": [_week(p, meta, ep_by, hit_cost)
                           for p in plan.gw_plans],
            "week_pts": plan_points(plan.gw_plans[:1], ep_by, hit_cost),
            "horizon_pts": plan_points(plan.gw_plans, ep_by, hit_cost),
            "objective": round(float(plan.objective), 2),
            "mean_pts": round(mean, 2),
            "p10_pts": round(float(np.percentile(sc, 10)), 2),
            "p90_pts": round(float(np.percentile(sc, 90)), 2),
            "p_beats_bank": (None if key == "bank"
                             else round(float((sc > scores["bank"]).mean()), 4)),
            "p_beats_top": (None if key == top_key
                            else round(float((sc > scores[top_key]).mean()), 4)),
            "p_best": round(best[key], 4),
            "vs_below": (None if prev is None else vs_below(
                prev[1].gw_plans[0], first,
                prev_mean=float(scores[prev[0]].mean()), mean=mean,
                hit_cost=hit_cost, meta=meta, ep_by=ep_by)),
        }
        rows.append(row)
        by_key[key] = row
        prev = (key, plan)

    max_hits, max_transfers = caps_from_state(state)
    payload = {
        "gw": int(gw), "gws": [int(g) for g in gws],
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "free_transfers": int(state.free_transfers),
        "cap": {"max_hits": max_hits, "max_transfers": max_transfers},
        "cap_rung": _cap_rung(max_hits, max_transfers,
                              [r["key"] for r in rows]),
        "recommended": _recommended(gw, solved),
        "n_draws": n_draws, "seed": int(seed), "sigma_source": sigma_source,
        "wall_s": round(time.perf_counter() - started, 1),
        "rungs": rows,
    }
    save_ladder(payload, gw)
    return payload
