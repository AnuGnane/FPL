"""``/api/drafts`` — named constraint sets, and their side-by-side re-solve.

CRUD is synchronous and cheap. The comparison is not: it is one MILP solve per
draft plus one for the reference row, so it goes through the same legacy job
registry the what-if lab uses (202 + ``job_id``, polled by ``useJob``) rather
than the single-flight v7 runner, which belongs to the named kinds. Six drafts
is the cap on one request: at ~7s a solve that is inside ``WHATIF_TIMEOUT_S``
with the reference row paid for (plan A8).

The board is built exactly as ``whatif.solve_whatif`` builds it — the idiom is
repeated rather than shared, because two existing tests pin that function's own
source text and namespace (plan A7).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from gaffer.artifacts import (latest_gw, load_solve_state, milp_pool,
                              raw_ep_by, solve_kw_from_state)
from gaffer.drafts import (MAX_DRAFTS, add_draft, delete_draft, load_drafts)
from gaffer.errors import GafferError
from gaffer.league_mode import cover_from_eo, tilt_ep
from gaffer.optimize.milp import SolveInput, solve_plan
from gaffer.web.jobs import WHATIF_TIMEOUT_S, JobQueueFull
from gaffer.web.routers.whatif import _summary, _validate
from gaffer.web.schemas import (CHIP_CODES, DraftCompare, DraftCompareRequest,
                                DraftCompareRow, DraftList, DraftRow,
                                DraftSaveRequest, JobAccepted, WhatIfRequest)

router = APIRouter(prefix="/api", tags=["drafts"])

MAX_COMPARE = 6
"""Drafts per comparison. Seven solves at ~7s each, inside the 120s job
timeout with room for a slow board."""

NO_RUN = "no saved solve state — run `gaffer advise` first"


def _fail(constraint: str, error: str, players: list[int]) -> HTTPException:
    return HTTPException(status_code=422,
                         detail={"constraint": constraint, "error": error,
                                 "players": players})


def _list() -> DraftList:
    return DraftList(drafts=[DraftRow(name=r["name"],
                                      created_at=r["created_at"],
                                      constraints=WhatIfRequest(
                                          **r["constraints"]))
                             for r in load_drafts()])


@router.get("/drafts", response_model=DraftList)
def drafts() -> DraftList:
    return _list()


@router.post("/drafts", response_model=DraftList)
def save(req: DraftSaveRequest) -> DraftList:
    """Save a draft, validating it against today's pool before it is stored.

    Early rather than at compare time on purpose: a draft naming a player who
    is not in the candidate pool can never be solved, and finding that out
    three days later, in a comparison, is finding it out at the wrong moment.
    """
    gw = latest_gw()
    if gw is not None:
        # Reuses the what-if lab's own validator, so a draft and a what-if
        # are refused for the same reasons in the same words.
        _validate(req.constraints, load_solve_state(gw))
    try:
        add_draft(req.name, req.constraints.model_dump())
    except GafferError as exc:
        raise _fail("draft_name", str(exc), []) from exc
    return _list()


@router.delete("/drafts/{name}", response_model=DraftList)
def remove(name: str) -> DraftList:
    if not delete_draft(name):
        raise HTTPException(status_code=404, detail=f"no draft called {name}")
    return _list()


def compare_drafts(names: list[str], gw: int) -> dict:
    """Re-solve each named draft on the current board, plus the optimum.

    Every row is priced in **raw** expected points over the weeks all the rows
    share, so a draft that shortened the horizon is not flattered by having
    fewer weeks of decay to lose. The shared horizon is the shortest *solved
    plan*, not the shortest horizon anybody asked for —
    ``whatif.solve_whatif``'s own ``min(len(baseline), len(yours))`` idiom —
    because a free hit is a one-week squad however many weeks its draft named,
    and scoring its one week against everybody else's three is a units bug,
    not a comparison. Which is why every row also carries the horizon it was
    actually solved over.

    A draft the board cannot satisfy gets a row carrying its reason: the other
    drafts in the comparison are still worth reading, and a comparison that
    dies on one bad constraint set is a comparison nobody trusts.
    """
    state = load_solve_state(gw)
    wanted = {r["name"]: r["constraints"] for r in load_drafts()}
    requests = [(name, WhatIfRequest(**wanted[name])) for name in names]

    # The shared horizon: the shortest any row asked for, so every row is
    # scored over the same weeks.
    default_horizon = state.opt.get("horizon") or len(state.gws)
    horizons = [req.horizon or default_horizon for _, req in requests]
    gws = state.gws[:max(1, min([int(default_horizon)] + horizons))]

    ep_by = raw_ep_by(state)
    cover = (state.cover if state.cover is not None
             else cover_from_eo(state.league_eo))
    pool = milp_pool(state, tilt_ep(ep_by, cover, state.lam), gws)
    opt = solve_kw_from_state(state)
    meta = {int(r.code): {"name": str(r.name), "position": str(r.position)}
            for r in state.pool.drop_duplicates("code").itertuples()}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def solve(name: str, req: WhatIfRequest | None,
              reference: bool = False) -> tuple[DraftCompareRow, list | None,
                                                str | None]:
        chip = CHIP_CODES.get(req.chip) if req else None
        if req is None:
            solve_state = SolveInput(owned_codes=state.owned_codes,
                                     bank=state.bank,
                                     free_transfers=state.free_transfers,
                                     gws=gws)
        elif chip == "freehit":
            # The same one-week conjuring ``chips.free_hit_gain`` scores.
            budget = state.bank + int(
                pool[pool["code"].isin(state.owned_codes)]["sell"].sum())
            solve_state = SolveInput(
                owned_codes=[], bank=budget, free_transfers=15, gws=[gws[0]],
                locked_out=list(req.ban), locked_in=list(req.lock),
                force_in_gw=list(req.force_in), max_hits=None)
        else:
            solve_state = SolveInput(
                owned_codes=state.owned_codes, bank=state.bank,
                free_transfers=state.free_transfers, gws=gws,
                wildcard_gw=gws[0] if chip == "wildcard" else None,
                bench_boost_gw=gws[0] if chip == "bboost" else None,
                triple_captain_gw=gws[0] if chip == "3xc" else None,
                locked_out=list(req.ban), locked_in=list(req.lock),
                force_in_gw=list(req.force_in), max_hits=req.max_hits)
        try:
            plans = solve_plan(pool, solve_state, **opt).gw_plans
        except Exception as exc:  # noqa: BLE001 — one bad draft is a row
            return (DraftCompareRow(name=name, is_reference=reference,
                                    solved_at=now,
                                    error=f"no legal squad satisfies this "
                                          f"draft: {exc}"), None, chip)
        return (DraftCompareRow(name=name, is_reference=reference,
                                solved_at=now, chip=chip,
                                horizon=len(plans)), plans, chip)

    solved = [solve("the optimum", None, reference=True)]
    solved += [solve(name, req) for name, req in requests]
    # The weeks every solved row shares. A free hit answers with one plan
    # whatever horizon its draft named, and it sets the bar for everybody.
    lengths = [len(plans) for _, plans, _ in solved if plans]
    weeks = min(lengths) if lengths else len(gws)

    rows = []
    for entry, plans, chip in solved:
        if plans is not None:
            summary = _summary(plans, ep_by, meta, weeks,
                               hit_cost=opt["hit_cost"],
                               cap_extra=2.0 if chip == "3xc" else 1.0,
                               bench_counts=chip == "bboost")
            entry.horizon_pts = summary.horizon_pts
            entry.expected_pts = summary.expected_pts
            entry.hits = summary.hits
            entry.buys = summary.buys
            entry.sells = summary.sells
            entry.captain = summary.captain
        rows.append(entry)
    base = rows[0].horizon_pts
    for entry in rows:
        if entry.horizon_pts is not None and base is not None:
            entry.delta_xpts = round(entry.horizon_pts - base, 2)
    return DraftCompare(gw=int(gw), weeks=weeks, rows=rows).model_dump()


@router.post("/drafts/compare", status_code=202, response_model=JobAccepted)
def compare(req: DraftCompareRequest, request: Request):
    gw = latest_gw()
    if gw is None:
        raise GafferError(NO_RUN)
    if len(req.names) > MAX_COMPARE:
        raise _fail("too_many_drafts",
                    f"compare at most {MAX_COMPARE} drafts at once — the "
                    f"solve budget is {MAX_COMPARE + 1} boards", [])
    known = {r["name"] for r in load_drafts()}
    missing = [n for n in req.names if n not in known]
    if missing:
        raise _fail("unknown_draft", f"no draft called {missing[0]}", [])
    names = list(req.names)
    try:
        job_id = request.app.state.jobs.submit(
            lambda: compare_drafts(names, gw), timeout_s=WHATIF_TIMEOUT_S)
    except JobQueueFull as exc:
        return JSONResponse(status_code=429, content={"detail": str(exc)})
    return JobAccepted(job_id=job_id)
