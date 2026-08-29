"""GET /api/plan/{gw} — the solved horizon the advice artifact already holds.

Reads ``plan_by_gw`` (written by ``run_advise``) and joins prices out of the
saved solve-state pool. No MILP runs here, deliberately: the plan the timeline
draws must be the plan the report printed, not a fresh solve that could differ.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from gaffer.artifacts import load_advice, load_solve_state
from gaffer.errors import GafferError
from gaffer.web.schemas import PlanGw, PlanMove, PlanTimeline

router = APIRouter(prefix="/api", tags=["plan"])


def _prices(state) -> tuple[dict[int, float], dict[int, float]]:
    """``({code: buy price}, {code: sell value})`` in millions."""
    one = state.pool.drop_duplicates("code")
    buy = {int(r.code): round(int(r.cost) / 10, 1) for r in one.itertuples()}
    sell = {int(r.code): round(int(r.sell) / 10, 1) for r in one.itertuples()}
    return buy, sell


def _move(entry: dict, prices: dict[int, float]) -> PlanMove:
    code = int(entry["code"])
    return PlanMove(code=code, name=str(entry.get("name", code)),
                    position=str(entry.get("position", "")),
                    ep=round(float(entry.get("ep") or 0.0), 2),
                    price=prices.get(code))


def _chip_by_gw(advice: dict) -> dict[int, str]:
    """``{gw: chip}`` for chips this run actually recommended playing."""
    out: dict[int, str] = {}
    for row in advice.get("chip_table") or []:
        if isinstance(row, dict) and row.get("play_now") and "gw" in row:
            out[int(row["gw"])] = str(row.get("chip"))
    return out


@router.get("/plan/{gw}", response_model=PlanTimeline)
def plan(gw: int) -> PlanTimeline:
    try:
        advice = load_advice(gw)
        state = load_solve_state(gw)
    except GafferError as exc:
        # 404, not the app-wide 422: the timeline hides on a missing artifact
        # and must not be confused with a constraint failure.
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    buy_price, sell_price = _prices(state)
    chips = _chip_by_gw(advice)
    hit_cost = int(state.opt.get("hit_cost", 4))
    head = int(advice.get("gw", gw))

    weeks = []
    for entry in advice.get("plan_by_gw") or []:
        week_gw = int(entry.get("gw", 0))
        is_head = week_gw == head
        weeks.append(PlanGw(
            gw=week_gw,
            buys=[_move(m, buy_price) for m in entry.get("buys") or []],
            sells=[_move(m, sell_price) for m in entry.get("sells") or []],
            hits=int(entry.get("hits") or 0),
            hit_cost=int(entry.get("hits") or 0) * hit_cost,
            chip=chips.get(week_gw),
            captain=(_move(advice["captain"], buy_price)
                     if is_head and advice.get("captain") else None),
            vice=(_move(advice["vice"], buy_price)
                  if is_head and advice.get("vice") else None),
            expected_pts=round(float(entry.get("expected_pts") or 0.0), 2)))

    return PlanTimeline(gw=head, generated_at=state.generated_at, weeks=weeks)
