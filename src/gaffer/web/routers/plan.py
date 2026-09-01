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


# The advice JSON on disk was written by whatever version of `gaffer advise`
# last ran, which need not be this one — and so was the solve-state pool beside
# it. Every read below therefore degrades the field it could not make sense of
# and draws the rest of the timeline: a plan missing an armband is still a
# plan, and a 500 tells the user nothing at all.


def _int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return default if out != out else out          # NaN


def _price(value) -> float | None:
    """Tenths of a million as millions, or ``None`` if it is not a number."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else round(out / 10, 1)          # NaN


def _prices(state) -> tuple[dict[int, float], dict[int, float]]:
    """``({code: buy price}, {code: sell value})`` in millions.

    A column the pool does not carry, and a value that is not a number, leave
    that side unpriced. The timeline renders a move with no price; it cannot
    render a 500.
    """
    pool = state.pool
    if getattr(pool, "columns", None) is None or "code" not in pool.columns:
        return {}, {}
    one = pool.drop_duplicates("code")
    buy: dict[int, float] = {}
    sell: dict[int, float] = {}
    for row in one.itertuples():
        code = _int(getattr(row, "code", None), -1)
        if code < 0:
            continue
        for column, out in (("cost", buy), ("sell", sell)):
            price = _price(getattr(row, column, None))
            if price is not None:
                out[code] = price
    return buy, sell


def _move(entry, prices: dict[int, float]) -> PlanMove | None:
    """One buy or sell, or ``None`` if it is too broken to name a player."""
    if not isinstance(entry, dict) or entry.get("code") is None:
        return None
    code = _int(entry.get("code"), -1)
    if code < 0:
        return None
    return PlanMove(code=code, name=str(entry.get("name", code)),
                    position=str(entry.get("position", "")),
                    ep=round(_float(entry.get("ep")), 2),
                    price=prices.get(code))


def _moves(entries, prices: dict[int, float]) -> list[PlanMove]:
    moves = (_move(e, prices) for e in entries or []) \
        if isinstance(entries, list) else ()
    return [m for m in moves if m is not None]


def _weeks_of(advice: dict) -> list[dict]:
    """``plan_by_gw`` as a list of week dicts, however it was written.

    An older writer keyed the horizon by gameweek; iterating that dict yields
    its string keys, and ``"5".get(...)`` is an AttributeError rather than a
    plan.
    """
    raw = advice.get("plan_by_gw")
    if isinstance(raw, dict):
        raw = list(raw.values())
    if not isinstance(raw, list):
        return []
    return [e for e in raw if isinstance(e, dict) and e.get("gw") is not None]


def _chip_by_gw(advice: dict) -> dict[int, str]:
    """``{gw: chip}`` for chips this run actually recommended playing."""
    out: dict[int, str] = {}
    rows = advice.get("chip_table")
    if not isinstance(rows, list):
        return out
    for row in rows:
        # `"gw" in row` was not enough: a chip the solver could not place
        # writes the key with a null, and int(None) is a TypeError.
        if not (isinstance(row, dict) and row.get("play_now")):
            continue
        if row.get("gw") is None:
            continue
        out[_int(row["gw"], -1)] = str(row.get("chip"))
    out.pop(-1, None)
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
    opt = state.opt if isinstance(state.opt, dict) else {}
    hit_cost = _int(opt.get("hit_cost", 4), 4)
    head = _int(advice.get("gw", gw), gw)

    # v11 §F1 (specs/2026-09-02-gaffer-v11-ui-design.md, plan A8). The bank is
    # not in ``plan_by_gw`` — ``advise.py`` writes no money into it — so it is
    # run forward here from ``SolveState.bank`` and the same two price columns
    # the moves above are already priced from.
    #
    # An unpriced move breaks the total permanently. Skipping it would report
    # a bank wrong by exactly that player's price, with nothing on the page to
    # say so, and there is no later week at which the sum re-synchronises.
    start = _price(getattr(state, "bank", None))
    running = start

    weeks = []
    for entry in _weeks_of(advice):
        week_gw = _int(entry.get("gw"), 0)
        is_head = week_gw == head
        hits = _int(entry.get("hits"))
        buys = _moves(entry.get("buys"), buy_price)
        sells = _moves(entry.get("sells"), sell_price)
        if running is not None and all(
                m.price is not None for m in buys + sells):
            # round(..., 1) because every price here is already one decimal;
            # letting float drift accumulate over a six-week horizon puts
            # 0.8999999999999995 on the page.
            running = round(running
                            + sum(m.price for m in sells)
                            - sum(m.price for m in buys), 1)
        else:
            running = None
        weeks.append(PlanGw(
            gw=week_gw,
            buys=buys,
            sells=sells,
            hits=hits,
            hit_cost=hits * hit_cost,
            chip=chips.get(week_gw),
            # A captain the artifact cannot name is a missing armband, not a
            # missing timeline.
            captain=(_move(advice.get("captain"), buy_price)
                     if is_head else None),
            vice=(_move(advice.get("vice"), buy_price) if is_head else None),
            expected_pts=round(_float(entry.get("expected_pts")), 2),
            bank=running))

    return PlanTimeline(gw=head, generated_at=state.generated_at, weeks=weeks,
                        bank=start)
