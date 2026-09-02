"""GET /api/plan/{gw} — the solved horizon the advice artifact already holds.

Reads ``plan_by_gw`` (written by ``run_advise``) and joins prices out of the
saved solve-state pool. No MILP runs here, deliberately: the plan the timeline
draws must be the plan the report printed, not a fresh solve that could differ.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from gaffer.artifacts import load_advice, load_solve_state
from gaffer.errors import GafferError
from gaffer.web.schemas import (PlanAlternative, PlanGw, PlanMove,
                                PlanTimeline)

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


def _moves(entries, prices: dict[int, float]) -> tuple[list[PlanMove], bool]:
    """``(moves, whole)``, where ``whole`` is False if anything was dropped.

    A move that cannot be parsed — not a dict, no code, a code that is not a
    number — is exactly as damaging to the running bank as one that could not
    be priced, and for the same reason: the week's total is then short by that
    player's price with nothing on the page to say so. The caller blanks the
    bank on either, so the two failures leave the same mark.

    A missing ``buys`` key is not a failure: a week with no moves is a week
    with no moves. A ``buys`` that is not a list at all is one — the plan said
    something here and it could not be read.
    """
    if entries is None:
        return [], True
    if not isinstance(entries, list):
        return [], False
    parsed = [_move(e, prices) for e in entries]
    return ([m for m in parsed if m is not None],
            all(m is not None for m in parsed))


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


LABELS = ("Plan B", "Plan C", "Plan D", "Plan E")
"""Names for the alternatives, by position. Longer than ``ALT_PLAN_MAX``
needs, so an artifact written by a build with a larger set does not fall off
the end of the list and lose its last tab."""


def _gap(value) -> float | None:
    """The signed objective gap, or ``None`` if it is not a number.

    Never 0.0 for unreadable: zero is "exactly level with the recommendation",
    which is a real and different claim — and, on a signed quantity, the
    boundary between "behind" and "ahead".
    """
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else round(out, 2)       # NaN


def _alternatives(advice: dict, build) -> list[PlanAlternative]:
    """``alternative_plans`` off the artifact, however it was written.

    Absent on every payload before v12 and on any run with the search off, so
    the empty list is the main case rather than the degraded one. An entry
    that is not a dict, or whose weeks are not a list, is dropped and the rest
    are drawn: a malformed alternative costs the reader a tab, not the board.

    v12 W3 §4.3 (specs/2026-09-01-gaffer-v12-program-design.md).
    """
    raw = advice.get("alternative_plans")
    if not isinstance(raw, list):
        return []
    out: list[PlanAlternative] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        weeks = entry.get("plan_by_gw")
        if isinstance(weeks, dict):
            weeks = list(weeks.values())
        if not isinstance(weeks, list):
            continue
        entries = [w for w in weeks
                   if isinstance(w, dict) and w.get("gw") is not None]
        if len(out) >= len(LABELS):
            break
        out.append(PlanAlternative(label=LABELS[len(out)],
                                   gap=_gap(entry.get("gap")),
                                   weeks=build(entries, head_refs=False)))
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
    # say so, and there is no later week at which the sum re-synchronises. A
    # move too broken to parse is dropped by ``_moves`` and does the same
    # damage, so it blanks the bank by the same mechanism.
    start = _price(getattr(state, "bank", None))

    def build(entries: list[dict], *, head_refs: bool) -> list[PlanGw]:
        """``plan_by_gw`` entries -> priced weeks with a running bank.

        v12 W3 §4.3 (specs/2026-09-01-gaffer-v12-program-design.md): shared by
        the recommended plan and by every alternative, because the board prints
        their banks side by side and two implementations of one running total
        disagree within a week. ``head_refs`` is False for an alternative: the
        armband belongs to the plan that was recommended, and lending it to a
        plan that never chose it is the most confident thing this payload could
        get wrong.
        """
        running = start
        out: list[PlanGw] = []
        for entry in entries:
            week_gw = _int(entry.get("gw"), 0)
            is_head = head_refs and week_gw == head
            hits = _int(entry.get("hits"))
            buys, buys_whole = _moves(entry.get("buys"), buy_price)
            sells, sells_whole = _moves(entry.get("sells"), sell_price)
            if running is not None and buys_whole and sells_whole and all(
                    m.price is not None for m in buys + sells):
                # round(..., 1) because every price here is already one decimal;
                # letting float drift accumulate over a six-week horizon puts
                # 0.8999999999999995 on the page.
                running = round(running
                                + sum(m.price for m in sells)
                                - sum(m.price for m in buys), 1)
            else:
                running = None
            out.append(PlanGw(
                gw=week_gw,
                buys=buys,
                sells=sells,
                hits=hits,
                hit_cost=hits * hit_cost,
                chip=chips.get(week_gw),
                # A captain the artifact cannot name is a missing armband, not
                # a missing timeline.
                captain=(_move(advice.get("captain"), buy_price)
                         if is_head else None),
                vice=(_move(advice.get("vice"), buy_price)
                      if is_head else None),
                expected_pts=round(_float(entry.get("expected_pts")), 2),
                bank=running))
        return out

    weeks = build(_weeks_of(advice), head_refs=True)
    return PlanTimeline(gw=head, generated_at=state.generated_at, weeks=weeks,
                        bank=start, alternatives=_alternatives(advice, build))
