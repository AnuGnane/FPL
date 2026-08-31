"""How much of this week's plan is the forecast, and how much is its error.

The MILP hands back one squad with no error bars, and the interesting question
about that squad is not "what does it score" but "how much of it would survive
the forecast being wrong in a way we already expect it to be wrong". v4a
measured what happens when nobody asks: a planning ceiling ~175 points above
what the tool actually scored, most of it spent on transfers that were never
robust.

The advice path already answers a *gating* version of that question when
``[scenarios] n`` is on. This module asks the reporting version — the move
frequencies, the modal plan, and what the best *differing* plan would have
cost — on demand, off the saved board, as a job. It never runs inside
``advise`` and it never changes a served number.

Everything about a scenario comes from :mod:`gaffer.optimize.scenarios`,
imported and untouched: ``run_scenarios`` is the sweep, ``move_frequencies``
is the count, ``xmins_by_player_gw`` is the noise scale's input. Seeded, so a
re-run with the same seed is the same report.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from gaffer import artifacts
from gaffer.artifacts import (latest_gw, load_components, load_solve_state,
                              milp_pool, raw_ep_by, solve_kw_from_state)
from gaffer.errors import GafferError
from gaffer.league_mode import cover_from_eo, tilt_ep
from gaffer.optimize.milp import SolveInput
from gaffer.optimize.scenarios import (move_frequencies, run_scenarios,
                                       xmins_by_player_gw)

SENSITIVITY_K = 20
"""Scenarios per sweep (spec D3).

Twenty is a compromise the spec picked and this module keeps: at ~7s a solve
it is two to three minutes, which is a job you start and come back to, and it
resolves a frequency to the nearest 5% — enough to tell 17/20 from 12/20,
which is the distinction the report exists to draw. The advice path's own
gating sweep runs forty because it is deciding rather than describing.
"""

FALLBACK_XMINS = 75.0
"""Expected minutes assumed for every player when the component file cannot
supply one (plan A5).

Not 92: at the noise floor every draw is the same board, every frequency is
100%, and the report says "certain" about a sweep that never varied anything.
75 puts the heuristic scale at (92 - 75) / 134 ~ 12.7% relative standard
deviation and the calibrated table at its 75-minute bin. It is a stated
assumption carried on the report, not a silent default.
"""


def sensitivity_path(gw: int) -> Path:
    return artifacts.REPORTS / f"sensitivity_gw{gw}.json"


def load_sensitivity(gw: int) -> dict | None:
    """The banked report for ``gw``, or ``None``.

    ``None`` rather than a domain error, like ``load_availability``: a missing
    report means the card offers a "run sensitivity" button, and there is
    nothing for the user to go and fix.
    """
    path = sensitivity_path(gw)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001 — a corrupt report is no report
        print(f"sensitivity report unreadable: {exc}")
        return None


def save_sensitivity(payload: dict, gw: int) -> Path:
    """Atomic, through a temp file — ``pen_tracker.save_tracker``'s idiom."""
    artifacts.REPORTS.mkdir(exist_ok=True)
    path = sensitivity_path(gw)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=1, allow_nan=False))
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def plan_signature(plan) -> tuple:
    """The decision a scenario plan represents, stripped of its arithmetic.

    First horizon week only, and deliberately: weeks two and three are
    re-planned from scratch next Tuesday, so counting them would split the
    frequencies on decisions nobody is taking. Sorted tuples rather than sets
    so the signature is hashable *and* serialisable.
    """
    first = plan.gw_plans[0]
    return (tuple(sorted(int(c) for c in first.buys)),
            tuple(sorted(int(c) for c in first.sells)),
            int(first.captain),
            str(getattr(plan, "chip", "") or ""))


def plan_value(gw_plans, ep_by: dict, weeks: int, hit_cost: int) -> float:
    """A plan's horizon points on the **true** EP table.

    The same arithmetic ``routers/whatif.py::_summary`` scores a plan with —
    the XI plus the captain again, minus four a hit — and applied here to
    every distinct scenario signature so the margin between them is priced on
    the board the manager actually faces rather than on the draw that produced
    them (plan A6). Raw EP, never tilted: the tilt shapes the pool and is not
    a number anybody is shown.
    """
    total = 0.0
    for plan in gw_plans[:weeks]:
        def ep(code) -> float:
            return float(ep_by.get((int(code), int(plan.gw)), 0.0))

        total += sum(ep(c) for c in plan.xi) + ep(plan.captain)
        total -= plan.hits * hit_cost
    return round(total, 2)


def _xmins(gw: int, ep_by: dict) -> tuple[dict, str | None]:
    """``{(code, gw): xMins}`` for the noise scale, and a notice if guessed."""
    try:
        table = xmins_by_player_gw(load_components(gw))
    except Exception as exc:  # noqa: BLE001 — a sweep is not worth a crash
        print(f"sensitivity: no component breakdown ({exc})")
        table = {}
    if table:
        return table, None
    return ({key: FALLBACK_XMINS for key in ep_by},
            f"no expected minutes on disk — every player was perturbed at a "
            f"flat {FALLBACK_XMINS:.0f}-minute assumption, so the "
            f"frequencies below rank moves rather than measure them")


def _refs(codes, meta: dict) -> list[dict]:
    return [{"code": int(c), "name": str(meta.get(int(c), {}).get("name",
                                                                 c)),
             "position": str(meta.get(int(c), {}).get("position", ""))}
            for c in sorted(int(c) for c in codes)]


def run_sensitivity(gw: int | None = None, k: int = SENSITIVITY_K,
                    seed: int | None = None) -> dict:
    """Sweep the saved board and bank the report. The job body.

    The board is built exactly as ``routers/whatif.py::solve_whatif`` builds
    it — saved state, raw EP, the cover table converted from ``league_eo``
    when the state predates it, tilt, ``milp_pool``, ``solve_kw_from_state`` —
    because a sensitivity report about a *different* board than the what-if
    lab re-solves would be a report about nothing. The idiom is repeated
    rather than shared: two existing tests pin ``solve_whatif``'s own source
    text and module namespace (plan A7).

    Raises :class:`GafferError` when there is no saved state, which is the
    job runner's signal to say "run `gaffer advise` first" rather than 500.
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
    pool_ep = tilt_ep(ep_by, cover, state.lam)
    pool = milp_pool(state, pool_ep, gws)
    opt = solve_kw_from_state(state)
    meta = {int(r.code): {"name": str(r.name), "position": str(r.position)}
            for r in state.pool.drop_duplicates("code").itertuples()}

    if seed is None:
        from gaffer.config import serving_config
        # Per gameweek, like the advice sweep: one fixed seed reused every
        # week would re-draw the same noise sequence all season.
        seed = int(serving_config().scenarios_seed) + int(gw)
    xmins, notice = _xmins(gw, ep_by)

    solve_state = SolveInput(owned_codes=state.owned_codes, bank=state.bank,
                             free_transfers=state.free_transfers, gws=gws)
    started = time.perf_counter()
    run = run_scenarios(pool, solve_state, xmins, n=int(k), seed=int(seed),
                        **opt)
    wall = round(time.perf_counter() - started, 1)
    if not run.completed:
        raise GafferError(
            f"all {run.attempted} sensitivity solves failed — the saved board "
            f"cannot be re-solved; re-run `gaffer advise`")

    freqs = move_frequencies(run.plans).to_dict("records")
    for row in freqs:
        row["frequency"] = round(float(row["frequency"]), 4)
        row["count"] = int(row["count"])
        row["code"] = int(row["code"])
        row["gw"] = int(row["gw"])
        row["name"] = str(meta.get(int(row["code"]), {}).get("name", ""))

    # One entry per distinct decision, in scenario order so the tie-break is
    # deterministic: the signature that appeared first wins a tied count.
    groups: dict[tuple, dict] = {}
    weeks = len(gws)
    for plan in run.plans:
        key = plan_signature(plan)
        entry = groups.get(key)
        if entry is None:
            first = plan.gw_plans[0]
            entry = groups[key] = {
                "count": 0,
                "buys": _refs(first.buys, meta),
                "sells": _refs(first.sells, meta),
                "captain": _refs([first.captain], meta)[0],
                "chip": (str(getattr(plan, "chip", "")) or None),
                "hits": int(first.hits),
                "value": plan_value(plan.gw_plans, ep_by, weeks,
                                    int(opt["hit_cost"])),
            }
        entry["count"] += 1
    ranked = sorted(groups.values(),
                    key=lambda e: (-e["count"], -e["value"]))
    modal = ranked[0]
    others = sorted(ranked[1:], key=lambda e: -e["value"])
    runner_up = others[0] if others else None
    margin = (None if runner_up is None
              else round(modal["value"] - runner_up["value"], 2))

    payload = {
        "gw": int(gw), "k": int(k), "completed": int(run.completed),
        "failures": int(run.failures), "seed": int(seed),
        "horizon": weeks, "wall_s": wall,
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "notice": notice,
        "frequencies": freqs,
        "modal": modal, "runner_up": runner_up, "margin": margin,
        "verdict": _verdict(modal, runner_up, margin, run.completed),
    }
    save_sensitivity(payload, gw)
    return payload


def _verdict(modal: dict, runner_up: dict | None, margin: float | None,
             completed: int) -> str:
    """One sentence a manager can act on, in the spec's own register."""
    share = f"{modal['count']}/{completed}"
    if runner_up is None or margin is None:
        return (f"every one of the {completed} re-solves reached the same "
                f"decision")
    moves = ", ".join(p["name"] for p in modal["buys"]) or "the hold plan"
    alt = ", ".join(p["name"] for p in runner_up["buys"]) or "holding"
    return (f"{moves} appears in {share} re-solves; {alt} is within "
            f"{margin} expected points")
