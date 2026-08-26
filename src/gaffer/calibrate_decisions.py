"""Offline calibration for the v4c decision tables.

Both the free-transfer shadow price and the chip stopping thresholds need to
know the *shape* of the opportunities a season offers: how much a single
transfer is typically worth in a given week, and how much each chip is
typically worth. Neither is guessable — the difference between a 1.5-point and
a 4-point median transfer surplus changes every λ in the table — and both are
stable enough to compute once a season rather than once a week.

So they are replayed offline. The distributions and the two tables derived from
them ship as ``assets/decision_priors.json``, in git, so a fresh clone decides
sensibly without ever running this. Spec §7.

This module is deliberately isolated from the advise path: nothing in
``advise.py`` imports it, and it does no work at import time.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from gaffer.optimize.milp import SolveInput, solve_plan

PHASE_BOUNDS = {"early": (1, 12), "mid": (13, 25), "late": (26, 38)}
"""Season thirds.

Coarse on purpose. A per-week transfer-surplus distribution would be thirty-
eight samples per season deep, which is noise; thirds are twelve times denser
and the real variation — early-season churn, mid-season fixture swings,
late-season settling — happens on roughly that scale anyway.
"""

CHIPS = ("wildcard", "bboost", "3xc", "freehit")

ASSET_PATH = Path("src/gaffer/assets/decision_priors.json")

REQUIRED_KEYS = ("version", "generated_at", "seasons", "transfer_surplus",
                 "chip_surplus")


def phase_of(gw: int) -> str:
    """Which season third a gameweek belongs to, clamped at both ends."""
    for name, (lo, hi) in PHASE_BOUNDS.items():
        if lo <= gw <= hi:
            return name
    return "early" if gw < PHASE_BOUNDS["early"][0] else "late"


CONTAMINATING_KW = ("ft_lambda", "ft_use_penalty", "bench_curve")
"""Solver knobs a calibration sample must never be measured under.

``ft_lambda`` is literally this module's own previous output: measuring the
surplus of a transfer on a board that already prices banked transfers off the
old table is a feedback loop, and the asset walks every time it is
regenerated. ``ft_use_penalty`` and ``bench_curve`` are not feedback, but they
are objective *craft* — the distributions are supposed to describe what a week
offers, not what one configuration of the optimiser makes of it.
"""


def neutral_cfg(kw: dict) -> dict:
    """``kw`` stripped back to the plain objective the samples are measured
    under. See :data:`CONTAMINATING_KW`."""
    return {k: v for k, v in kw.items() if k not in CONTAMINATING_KW}


def best_single_transfer(pool: pd.DataFrame, state: SolveInput,
                         **solve_cfg) -> float:
    """EP gain from the best one-transfer move, over making none.

    This is the surplus draw the λ DP consumes: "if I spend a free transfer
    this week, what do I get". Measured as the difference between the
    one-transfer optimum and the no-transfer optimum on the same board, so it
    is a *marginal* number and cannot be inflated by the squad simply being
    good.

    Floored at zero. Nobody is forced to transfer, so a negative surplus is
    not a thing that can happen to a manager; letting one into the DP would
    teach it that transfers are a liability.

    The spent solve is pinned to *one* transfer and *no* hits. ``state`` says
    ``free_transfers=1``, but that caps nothing on its own — the solver is
    free to buy four players and pay for three of them, and ``expected_pts``
    is gross of the hit cost, so an unconstrained solve records a hit-taking
    week as the surplus of a single free transfer plus the points it paid to
    take. ``max_hits=0`` makes the MILP's own ``hits >= nt - prev_ft`` bind at
    ``nt <= 1``, which is exactly the question being asked.
    """
    from dataclasses import replace

    from gaffer.optimize.milp import FixedMoves

    held = solve_plan(pool, state, **solve_cfg,
                      fixed_moves=FixedMoves(no_transfer=True))
    spent = solve_plan(pool, replace(state, max_hits=0), **solve_cfg)
    gain = (spent.gw_plans[0].expected_pts - held.gw_plans[0].expected_pts)
    return max(0.0, float(gain))


def walk_season(season: str, start_gw: int = 5,
                horizon: int = 1) -> tuple[list[dict], list[dict]]:
    """One season's per-week transfer and chip surpluses.

    Reuses the backtest's own weekly loop rather than duplicating it: the
    replay already builds the pool, the EP matrix and a legal squad for every
    gameweek, and re-implementing that here would guarantee the calibration
    and the replay eventually disagree about what a week looks like.

    Returns ``([{gw, surplus}], [{gw, chip, gain}])``.
    """
    import gaffer.backtest as bt
    from gaffer.optimize.chips import evaluate_chips

    transfers: list[dict] = []
    chips: list[dict] = []
    real_solve = bt.solve_plan
    real_priors = bt.load_decision_priors

    def observing_solve(pool, state, **kw):
        plan = real_solve(pool, state, **kw)
        if state.owned_codes:
            gw = int(state.gws[0])
            cfg = neutral_cfg(kw)
            one_ft = SolveInput(
                owned_codes=list(state.owned_codes), bank=state.bank,
                free_transfers=1, gws=list(state.gws))
            # Two separate guards: a transfer solve that falls over used to
            # take the week's four chip surpluses down with it, which is a
            # much bigger hole in the distribution than the one sample that
            # actually failed.
            try:
                transfers.append({
                    "gw": gw,
                    "surplus": best_single_transfer(pool, one_ft, **cfg)})
            except Exception as exc:  # noqa: BLE001
                print(f"calibration: no transfer sample for GW{gw} ({exc})")
            try:
                table = evaluate_chips(pool, state, list(CHIPS), **cfg)
            except Exception as exc:  # noqa: BLE001
                print(f"calibration: no chip samples for GW{gw} ({exc})")
            else:
                for r in table.itertuples():
                    if int(r.gw) == gw:
                        chips.append({"gw": int(r.gw), "chip": str(r.chip),
                                      "gain": float(r.gain)})
        return plan

    bt.solve_plan = observing_solve
    # Blind the replay to the shipped asset for the duration. Without this the
    # calibration measures the objective *its own previous output* built — the
    # lambda table prices the weekly solve, the theta table decides which
    # chips get played, and regenerating drifts a little further every time.
    bt.load_decision_priors = lambda: None
    try:
        bt.run_backtest(season=season, start_gw=start_gw, horizon=horizon)
    finally:
        bt.solve_plan = real_solve
        bt.load_decision_priors = real_priors
    return transfers, chips


def run_calibration(seasons: list[str], start_gw: int = 5) -> dict:
    """Replay every season and assemble the priors payload.

    A season that cannot be replayed is skipped with a printed line and drops
    out of ``seasons``: the archive does not go back forever, and a five-season
    calibration must not die on the one with no history.
    """
    transfer_surplus: dict[str, list[float]] = {p: [] for p in PHASE_BOUNDS}
    chip_surplus: dict[str, dict[str, list[float]]] = {c: {} for c in CHIPS}
    used: list[str] = []
    for season in seasons:
        try:
            weeks, chips = walk_season(season, start_gw=start_gw)
        except Exception as exc:  # noqa: BLE001
            print(f"calibration: cannot replay {season} ({exc})")
            continue
        used.append(season)
        for row in weeks:
            transfer_surplus[phase_of(int(row["gw"]))].append(
                float(row["surplus"]))
        for row in chips:
            chip = str(row["chip"])
            key = str(int(row["gw"]))
            chip_surplus.setdefault(chip, {}).setdefault(key, []).append(
                float(row["gain"]))
    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seasons": used,
        "transfer_surplus": transfer_surplus,
        "chip_surplus": chip_surplus,
    }


def write_priors(payload: dict, path: Path | str = ASSET_PATH) -> Path:
    """Validate and write the asset.

    Validated before writing because a half-populated priors file is worse
    than none at all: an empty transfer distribution builds a λ table of
    zeroes, which tells the objective that banked transfers are worthless and
    every hit is worth taking. An absent file degrades honestly; a hollow one
    degrades silently.
    """
    missing = [k for k in REQUIRED_KEYS if k not in payload]
    if missing:
        raise ValueError(
            f"decision priors payload is missing {missing} — refusing to "
            "write a partial asset")
    pooled = [s for samples in payload["transfer_surplus"].values()
              for s in samples]
    if not pooled:
        raise ValueError(
            "decision priors carry no transfer surplus samples — a lambda "
            "table built from this would price every free transfer at zero")
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return dest
