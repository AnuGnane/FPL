"""What-If Lab: re-solve the saved MILP under user constraints.

No training, no network: everything comes from ``reports/solve_state_gw{N}``
(spec §2.3), so a re-solve is a pure MILP run measured in seconds.

Both sides of the diff are solved in the same job. Re-solving the baseline
rather than reading the saved plan is what makes the comparison honest when
the user overrides the horizon — a three-week baseline against a one-week
constrained plan would show a delta that is mostly arithmetic.

Every number shown or differenced is **raw** (untilted) expected points; the
league tilt only ever shapes the candidate pool the MILP optimises over,
exactly as ``advise.run_advise`` does it.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from gaffer.artifacts import (latest_gw, load_solve_state, milp_pool,
                              raw_ep_by, solve_kw_from_state)
from gaffer.errors import GafferError
from gaffer.league_mode import cover_from_eo, tilt_ep
from gaffer.optimize.milp import GwPlan, SolveInput, solve_plan
from gaffer.web.jobs import WHATIF_TIMEOUT_S, JobQueueFull
from gaffer.web.schemas import (CHIP_CODES, JobAccepted, PlanSummary,
                                PlayerRef, WhatIfRequest, WhatIfResult)

router = APIRouter(prefix="/api", tags=["whatif"])


def _fail(constraint: str, error: str, players: list[int]) -> HTTPException:
    """A 422 the UI can render inline next to the offending input."""
    return HTTPException(status_code=422,
                         detail={"constraint": constraint, "error": error,
                                 "players": players})


def _validate(req: WhatIfRequest, state) -> None:
    both = sorted(set(req.lock) & set(req.ban))
    if both:
        raise _fail("lock_and_ban",
                    f"player {both[0]} cannot be both locked in and banned",
                    both)
    known = {int(c) for c in state.pool["code"]}
    # v12 W3 §4.1 (specs/2026-09-01-gaffer-v12-program-design.md): force_out is
    # checked against the same pool as the other three — ``_solve_once``
    # refuses an unknown code with a GafferError, which would reach the user as
    # a failed job rather than as a 422 beside the input he typed.
    unknown = sorted({*req.lock, *req.ban, *req.force_in,
                      *req.force_out} - known)
    if unknown:
        raise _fail("unknown_player",
                    f"player {unknown[0]} is not in this week's candidate "
                    f"pool", unknown)
    forced_and_owned = sorted(set(req.force_in) & set(state.owned_codes))
    if forced_and_owned:
        raise _fail("force_in_owned",
                    f"you already own player {forced_and_owned[0]} — use "
                    f"lock to keep him", forced_and_owned)
    forced_and_banned = sorted(set(req.force_in) & set(req.ban))
    if forced_and_banned:
        raise _fail("force_in_and_ban",
                    f"player {forced_and_banned[0]} cannot be forced in and "
                    f"banned", forced_and_banned)
    # v12 W3 §4.1 (specs/2026-09-01-gaffer-v12-program-design.md). Four
    # combinations that cannot mean anything, each named where the user typed
    # it rather than left to produce a constraint that silently does nothing.
    not_owned = sorted(set(req.force_out) - set(state.owned_codes))
    if not_owned:
        raise _fail("force_out_not_owned",
                    f"you do not own player {not_owned[0]} — use ban to keep "
                    f"him out of the squad", not_owned)
    out_and_lock = sorted(set(req.force_out) & set(req.lock))
    if out_and_lock:
        raise _fail("force_out_and_lock",
                    f"player {out_and_lock[0]} cannot be both kept and sold",
                    out_and_lock)
    out_and_ban = sorted(set(req.force_out) & set(req.ban))
    if out_and_ban:
        raise _fail("force_out_and_ban",
                    f"banning player {out_and_ban[0]} removes him without "
                    f"sale proceeds; force_out sells him — pick one",
                    out_and_ban)
    if req.force_out and req.chip == "fh":
        # A free hit squad is conjured from nothing (``owned_codes=[]``), so
        # there is nobody to sell and the constraint would apply to no one.
        raise _fail("force_out_on_free_hit",
                    "a free hit squad is built from scratch, so there is "
                    "nothing to force out of it", list(req.force_out))
    if req.chip != "none":
        chip = CHIP_CODES[req.chip]
        available = state.avail_by_gw.get(state.gws[0], [])
        if chip not in available:
            raise _fail("chip_unavailable",
                        f"{chip} is not available in GW{state.gws[0]} — "
                        f"available: {', '.join(available) or 'none'}", [])
    if req.max_hits < 0:
        raise _fail("max_hits", "max_hits cannot be negative", [])


def _summary(plans: list[GwPlan], ep_by: dict, meta: dict, weeks: int,
             *, hit_cost: int, cap_extra: float = 1.0,
             bench_counts: bool = False) -> PlanSummary:
    """A plan in **raw** expected points, the way the report does it.

    The squad shown is the first gameweek's — that is the decision the user
    actually makes this week. ``horizon_pts`` scores the first ``weeks``
    gameweeks of the plan so two plans of different length are compared over
    the stretch they share (a free hit covers one week only).
    """
    head = plans[0]

    def refs(codes: list[int]) -> list[PlayerRef]:
        return [PlayerRef(code=int(c), name=meta[int(c)]["name"],
                          position=meta[int(c)]["position"],
                          ep=round(float(ep_by.get((int(c), int(head.gw)),
                                                   0.0)), 2))
                for c in codes]

    def week_pts(plan: GwPlan) -> float:
        def ep(c) -> float:
            return float(ep_by.get((int(c), int(plan.gw)), 0.0))

        total = sum(ep(c) for c in plan.xi) + cap_extra * ep(plan.captain)
        if bench_counts:
            total += sum(ep(c) for c in plan.bench)
        return total - plan.hits * hit_cost

    return PlanSummary(gw=int(head.gw), xi=refs(head.xi),
                       bench=refs(head.bench), captain=refs([head.captain])[0],
                       vice=refs([head.vice])[0], buys=refs(head.buys),
                       sells=refs(head.sells), hits=int(head.hits),
                       expected_pts=round(week_pts(head), 2),
                       horizon_pts=round(
                           sum(week_pts(p) for p in plans[:weeks]), 2))


def solve_whatif(req: WhatIfRequest, gw: int) -> dict:
    """The job body: baseline and constrained solve, plus their diff."""
    state = load_solve_state(gw)
    horizon = req.horizon or state.opt.get("horizon") or len(state.gws)
    gws = state.gws[:max(1, int(horizon))]
    ep_by = raw_ep_by(state)
    # tilt_ep wants cover *fractions* in [0, 1]. The saved table is the one
    # advise tilted on; league_eo is a percent, so a state written before the
    # field existed has to be converted, not passed through — 90.0 would clamp
    # to 1.0 and re-solve a board the advice never saw.
    cover = (state.cover if state.cover is not None
             else cover_from_eo(state.league_eo))
    pool_ep = tilt_ep(ep_by, cover, state.lam)
    pool = milp_pool(state, pool_ep, gws)
    opt = solve_kw_from_state(state)
    meta = {int(r.code): {"name": str(r.name), "position": str(r.position)}
            for r in state.pool.drop_duplicates("code").itertuples()}

    base_state = SolveInput(owned_codes=state.owned_codes, bank=state.bank,
                            free_transfers=state.free_transfers, gws=gws)
    baseline = solve_plan(pool, base_state, **opt).gw_plans

    chip = CHIP_CODES.get(req.chip)
    yours_state = SolveInput(
        owned_codes=state.owned_codes, bank=state.bank,
        free_transfers=state.free_transfers, gws=gws,
        wildcard_gw=gws[0] if chip == "wildcard" else None,
        bench_boost_gw=gws[0] if chip == "bboost" else None,
        triple_captain_gw=gws[0] if chip == "3xc" else None,
        locked_out=list(req.ban), locked_in=list(req.lock),
        force_in_gw=list(req.force_in),
        # v12 W3 §4.1 (specs/2026-09-01-gaffer-v12-program-design.md)
        force_out=list(req.force_out), max_hits=req.max_hits)
    if chip == "freehit":
        # Free hit conjures a one-week squad on the sell value of the current
        # one and reverts after, exactly as ``chips.free_hit_gain`` scores it.
        budget = state.bank + int(
            pool[pool["code"].isin(state.owned_codes)]["sell"].sum())
        yours_state = SolveInput(
            owned_codes=[], bank=budget, free_transfers=15, gws=[gws[0]],
            locked_out=list(req.ban), locked_in=list(req.lock),
            force_in_gw=list(req.force_in), max_hits=None)
    try:
        yours = solve_plan(pool, yours_state, **opt).gw_plans
    except RuntimeError as exc:
        raise GafferError(
            f"no legal squad satisfies those constraints "
            f"(lock={req.lock}, ban={req.ban}, force_in={req.force_in}, "
            # v12 W3 §4.1 (specs/2026-09-01-gaffer-v12-program-design.md)
            f"force_out={req.force_out}, max_hits={req.max_hits}): "
            f"{exc}") from exc

    weeks = min(len(baseline), len(yours))
    base = _summary(baseline, ep_by, meta, weeks, hit_cost=opt["hit_cost"])
    mine = _summary(yours, ep_by, meta, weeks, hit_cost=opt["hit_cost"],
                    cap_extra=2.0 if chip == "3xc" else 1.0,
                    bench_counts=chip == "bboost")
    base_xi = {p.code for p in base.xi}
    mine_xi = {p.code for p in mine.xi}
    delta = round(mine.horizon_pts - base.horizon_pts, 2)
    if delta < 0:
        verdict = f"your version costs {abs(delta)} expected points"
    elif delta > 0:
        verdict = f"your version gains {delta} expected points"
    else:
        verdict = "your version scores the same expected points"
    return WhatIfResult(
        baseline=base, yours=mine, delta_xpts=delta,
        xi_in=[p for p in mine.xi if p.code not in base_xi],
        xi_out=[p for p in base.xi if p.code not in mine_xi],
        transfers_changed=({p.code for p in mine.buys}
                           != {p.code for p in base.buys}),
        captain_changed=mine.captain.code != base.captain.code,
        verdict=verdict).model_dump()


@router.post("/whatif", status_code=202, response_model=JobAccepted)
def whatif(req: WhatIfRequest, request: Request):
    gw = latest_gw()
    if gw is None:
        raise GafferError("no saved solve state — run `gaffer advise` first")
    _validate(req, load_solve_state(gw))
    try:
        job_id = request.app.state.jobs.submit(
            lambda: solve_whatif(req, gw), timeout_s=WHATIF_TIMEOUT_S)
    except JobQueueFull as exc:
        return JSONResponse(status_code=429, content={"detail": str(exc)})
    return JobAccepted(job_id=job_id)
