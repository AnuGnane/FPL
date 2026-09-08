"""GET /api/plan/{gw} — the served plan, shaped for the board.

A shape adapter and nothing else (v17f §2.6): every number here — the
prices, the running bank, the trace — was written by ``gaffer advise`` or
filled by ``artifacts.served_plan`` for a file written before this cycle. No
MILP runs here, deliberately: the plan the timeline draws must be the plan
the report printed, not a fresh solve that could differ.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from gaffer.artifacts import served_plan
from gaffer.errors import GafferError
from gaffer.served import ServedMove, ServedWeek
from gaffer.web.schemas import (PlanAlternative, PlanGw, PlanMove,
                                PlanTimeline)

router = APIRouter(prefix="/api", tags=["plan"])

LABELS = ("Plan B", "Plan C", "Plan D", "Plan E")
"""Names for the alternatives, by position. Longer than ``ALT_PLAN_MAX``
needs, so an artifact written by a build with a larger set does not fall off
the end of the list and lose its last tab."""


def _move(move: ServedMove | None) -> PlanMove | None:
    if move is None:
        return None
    return PlanMove(code=move.code, name=move.name, position=move.position,
                    ep=round(move.ep, 2), price=move.price)


@router.get("/plan/{gw}", response_model=PlanTimeline)
def plan(gw: int) -> PlanTimeline:
    try:
        served = served_plan(gw)
    except GafferError as exc:
        # 404, not the app-wide 422: the timeline hides on a missing artifact
        # and must not be confused with a constraint failure.
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    head = served.gw

    def week(w: ServedWeek, *, head_refs: bool) -> PlanGw:
        # The armband belongs to the plan that was recommended, on its head
        # week only; lending it to an alternative, or to the objective's
        # week, would be the most confident thing this payload could get
        # wrong.
        is_head = head_refs and w.gw == head
        return PlanGw(
            gw=w.gw, buys=[_move(m) for m in w.buys], sells=[_move(m) for m in w.sells],
            hits=w.hits, hit_cost=w.hit_cost, chip=w.chip,
            captain=_move(served.captain) if is_head else None,
            vice=_move(served.vice) if is_head else None,
            expected_pts=round(w.expected_pts, 2), bank=w.bank, trace=w.trace)

    weeks = [week(w, head_refs=True) for w in served.plan_by_gw]
    alternatives = [
        PlanAlternative(label=LABELS[i], gap=alt.gap,
                        weeks=[week(w, head_refs=False) for w in alt.plan_by_gw])
        for i, alt in enumerate(served.alternative_plans[:len(LABELS)])]
    # v16 §4: the objective's week one beside the served rung's only when
    # the two differ — an agreeing objective would say it twice.
    objective = None
    if (served.objective is not None and served.objective.week is not None
            and served.restraint is not None and served.restraint.agrees is False):
        objective = week(served.objective.week, head_refs=False)
    # ``or ""``: the stamp is the one served field the board only prints,
    # and a file with no ``generated_at`` is a pre-v17f file whose solve
    # state carried none either — a blank "as of" line, not a 404 over a
    # plan that is otherwise whole.
    return PlanTimeline(gw=head, generated_at=served.generated_at or "", weeks=weeks,
                        bank=served.bank, alternatives=alternatives, objective=objective)
