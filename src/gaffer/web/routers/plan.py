"""GET /api/plan/{gw} — the solved horizon the advice artifact already holds.

Reads ``plan_by_gw`` (written by ``run_advise``) and joins prices out of the
saved solve-state pool. No MILP runs here, deliberately: the plan the timeline
draws must be the plan the report printed, not a fresh solve that could differ.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from gaffer.artifacts import load_advice, load_solve_state
from gaffer.errors import GafferError
from gaffer.league_mode import cover_from_eo
from gaffer.trace import trace_plan
from gaffer.web.schemas import (PlanAlternative, PlanGw, PlanMove,
                                PlanTimeline, PlanWeekTrace)

router = APIRouter(prefix="/api", tags=["plan"])

TRACE = True
"""Whether to compute the move trace (v12 W5 §6.5).

A module flag rather than a config key: it exists so the byte-identity test can
turn the accounting off and compare the payload the board already drew. There
is nothing here for a user to switch, and a ``Config`` field for a test would
be a knob nobody sets.
"""


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


def _trace_inputs(state) -> tuple[dict, dict, dict]:
    """``({(code, gw): ep}, {code: position}, {code: name})`` off the pool.

    Degrades the way every other reader in this module does: a pool with no
    ``ep_raw`` column yields an empty EP table, which the trace reports as
    "not in the pool" per move rather than as a zero.
    """
    pool = getattr(state, "pool", None)
    columns = getattr(pool, "columns", None)
    if columns is None or "code" not in columns:
        return {}, {}, {}
    ep_by: dict = {}
    positions: dict = {}
    player_names: dict = {}
    has_ep = "ep_raw" in columns
    for row in pool.itertuples():
        code = _int(getattr(row, "code", None), -1)
        if code < 0:
            continue
        positions.setdefault(code, str(getattr(row, "position", "")))
        player_names.setdefault(code, str(getattr(row, "name", code)))
        if has_ep:
            # A NaN is not a 0.0. ``_float`` defaults one to zero, and a zero
            # here would price a swap against this player as a measured tie
            # rather than as a reading the pool does not have. Leaving the key
            # out is what makes the trace say "not in the pool".
            ep = _float(getattr(row, "ep_raw", None), float("nan"))
            if ep == ep:
                ep_by[(code, _int(getattr(row, "gw", None), -1))] = ep
    return ep_by, positions, player_names


def _thresholds(advice: dict) -> dict[int, float]:
    """``{gw: θ}`` for the chips this run recommends playing.

    A threshold that is not a number is dropped rather than defaulted. 0.0 is
    a real θ — "play it in any week that is not actively worse" — so a string
    where a number belongs must not be served as the most permissive threshold
    the model can have.
    """
    out: dict[int, float] = {}
    rows = advice.get("chip_table")
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not (isinstance(row, dict) and row.get("play_now")):
            continue
        if row.get("gw") is None or row.get("threshold") is None:
            continue
        gw_key = _int(row["gw"], -1)
        theta = _float(row["threshold"], float("nan"))
        if gw_key < 0 or theta != theta:
            continue
        out[gw_key] = theta
    return out


def _price_falls(state) -> tuple[bool, dict[int, float]]:
    """``(price_timing is on, {code: p_fall_tonight})`` for the owned squad.

    The same reader the objective's price-timing term uses (W2 §3.4), called
    the same way — so the charge the board prints is not a second estimate
    computed from the same log by slightly different arithmetic.

    It is a *present-tense* read, and the week note says so. Both the switch
    and the probabilities are read here, when the board is drawn, off tonight's
    price log and today's ``[optimizer] price_timing``; nothing on
    ``SolveState`` records what the solve saw, so this cannot claim to be the
    charge the solver applied. Freezing it would need the writer, and the
    writer is ``advise.py``. Doubly gated, deliberately:
    ``owned_price_falls`` already returns ``{}`` when the switch is off
    (``price_timing.py:168``), and the switch is read here as well because the
    trace has to tell "off" from "on and empty" — the first is a term the
    objective never carried and the second is an unknown.

    Two switches, two different answers. ``price_timing`` off means the
    objective carried **no such term**, so the trace reports ``None`` and says
    so rather than printing a zero, which would read as "we checked and it was
    free". A reader that will not import, or that has no row for a code, is
    also ``None`` — an unknown, which is not a zero chance of a fall.

    Imported lazily and called inside the trace's own ``try`` for the same
    reason the λ table is: a decoration must never be the reason a plan does
    not render.
    """
    try:
        # W2's own reader and W2's own switch — the dotted paths
        # `settings_keys.py` names, so the two surfaces cannot disagree about
        # whether the term is on.
        from gaffer.config import price_timing as price_timing_on
        from gaffer.price_timing import owned_price_falls
    except Exception as exc:  # noqa: BLE001 — W2 may not have landed
        print(f"plan trace: no price-timing reader ({exc})")
        return False, {}
    try:
        if not price_timing_on():
            return False, {}
        owned = [int(c) for c in getattr(state, "owned_codes", []) or []]
        return True, {int(k): float(v)
                      for k, v in (owned_price_falls(owned) or {}).items()}
    except Exception as exc:  # noqa: BLE001
        print(f"plan trace: price falls unreadable ({exc})")
        return True, {}


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

    # v12 §6.5 (specs/2026-09-01-gaffer-v12-program-design.md, plan A8). Every
    # input the trace needs is already in these two artifacts, so it is
    # accounting over what the router has in hand — the solver is not called,
    # not imported for anything but two constants, and cannot see this.
    ep_by, positions, player_names = _trace_inputs(state)
    thresholds = _thresholds(advice)
    ft_lambda = None
    if opt.get("decision_priors"):
        try:
            from gaffer.assets import load_decision_priors
            from gaffer.optimize.ft_value import lambda_from_priors
            ft_lambda = lambda_from_priors(load_decision_priors())
        except Exception as exc:  # noqa: BLE001 — a decoration, never a gate
            print(f"plan trace: no lambda table ({exc}); flat ft_value")

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

    # The recommended plan only. An alternative was returned by a different
    # solve, over a different XI, and the free-transfer count this runs
    # forward is Plan A's — lending it to Plan B would print Plan A's numbers
    # under Plan B's moves. The board says so under the strip.
    #
    # One pass over the whole horizon rather than a week at a time, because
    # the free-transfer recurrence is what makes the week after depend on the
    # week before.
    if TRACE and weeks:
        try:
            price_timing, price_fall = _price_falls(state)
            # The moves' own names, under the pool's: the pool is the solver's
            # candidate list and a move can name a player who is not on it —
            # and a bare code on the board is a database key shown to a human.
            move_names = {m.code: m.name
                          for w in weeks for m in (*w.buys, *w.sells)}
            # `chip: None`, deliberately, and not `w.chip`. `w.chip` is what
            # the *chip table* recommends; `plan_by_gw` is the base solve, and
            # `advise` never sets `wildcard_gw` on it. So the objective did
            # charge this week's transfers and did run the free-transfer
            # recurrence normally, and telling the trace a wildcard was played
            # would report a charge that was made as zero — and then run every
            # later week's FT count forward from the wrong number. The note
            # below says which plan these terms belong to; θ still comes from
            # the chip table, because the recommendation is real and it is
            # only the pricing that predates it.
            traced = trace_plan(
                [{"gw": w.gw, "hits": w.hits,
                  "buys": [m.code for m in w.buys],
                  "sells": [m.code for m in w.sells], "chip": None}
                 for w in weeks],
                gws=[int(g) for g in getattr(state, "gws", [])],
                ep_by=ep_by, positions=positions,
                names={**move_names, **player_names},
                decay=_float(opt.get("decay", 1.0), 1.0), hit_cost=hit_cost,
                ft_value=_float(opt.get("ft_value", 0.0)),
                itb_value=_float(opt.get("itb_value", 0.0)),
                free_transfers=_int(getattr(state, "free_transfers", 0)),
                ft_lambda=ft_lambda,
                ft_use_penalty=_float(opt.get("ft_use_penalty", 0.0)),
                lam=_float(getattr(state, "lam", 0.0)),
                # `is not None`, not `or {}`. A state written before the field
                # existed carries `cover=None`, and the documented fallback is
                # `cover_from_eo(league_eo)` — what whatif.py, drafts.py and
                # sensitivity.py all do. An empty cover tilts nothing, so
                # `or {}` would report 0.0 for a term the objective applied,
                # which is the one thing this trace must never print.
                cover=(state.cover
                       if getattr(state, "cover", None) is not None
                       else cover_from_eo(getattr(state, "league_eo", {})
                                          or {})),
                thresholds=thresholds,
                banks={w.gw: w.bank for w in weeks},
                price_timing=price_timing, price_fall=price_fall)
            for week, one in zip(weeks, traced):
                payload = asdict(one)
                if week.chip:
                    said = (f"a {week.chip} is recommended this week; these "
                            f"terms are the base plan's, which the solver "
                            f"returned without it")
                    payload["note"] = "; ".join(
                        part for part in (payload["note"], said) if part)
                week.trace = PlanWeekTrace(**payload)
        except Exception as exc:  # noqa: BLE001
            # A decoration must never be the reason a plan does not render —
            # the board's own rule for the price movers.
            print(f"plan trace unavailable for GW{head}: {exc}")

    return PlanTimeline(gw=head, generated_at=state.generated_at, weeks=weeks,
                        bank=start, alternatives=_alternatives(advice, build))
