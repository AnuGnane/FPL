"""The served plan, owned once (v17f §4,
specs/2026-09-08-v17f-served-plan-design.md).

One value answers "what does the user see for GW N": the moves, the weeks
with their prices, banks and traces, the restraint walk and the objective's
own week. ``advise`` builds it and writes it whole; ``artifacts.served_plan``
reads it back and, for a file written before v17f, fills the same fields
through the same functions. Everything here is a value in and a value out.

The four pool readers at the bottom moved from ``web/routers/plan.py`` with
their docstrings: the pool parquet is written by whatever run wrote the
advice and drifts with it, so they still degrade a column they cannot
read rather than raise.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _Frozen(BaseModel):
    """Frozen, and blind to keys it does not declare: the advice JSON
    carries more than the plan (chip table, threats, scenarios), and a
    key a future writer adds must not break this reader."""

    model_config = ConfigDict(frozen=True, extra="ignore")


class PlanMoveTrace(_Frozen):
    """One transfer, priced against the objective's own terms (v12 W5 §6.5).

    Not a counterfactual. ``ep_gain`` is the decayed expected-points
    difference of a position-matched swap over the rest of the horizon — the
    objective's own arithmetic at the plan the solver returned — and **not**
    "the plan is this much worse without this move", which would need a
    re-solve. ``None`` everywhere means unknown, never a measured zero.
    """

    buy_code: int | None = None
    buy_name: str = ""
    sell_code: int | None = None
    sell_name: str = ""
    ep_gain: float | None = None
    lambda_tilt: float | None = None
    note: str = ""


class PlanWeekTrace(_Frozen):
    """One planned week's charges. Four of them are week-level on purpose:
    a week with two transfers and one hit cannot attribute the hit to one of
    them, and splitting it would be arithmetic dressed as a finding.

    Three of the objective's terms are **not** here — the XI, captain and vice
    weightings and the bench seats (``milp.py:813-835``, including
    ``_decision_scales``' per-week autosub scales). They price the whole squad
    rather than a swap, so these numbers do not sum to ``expected_pts`` and
    are not meant to. The board's caption says so in the same words.
    """

    gw: int
    moves: list[PlanMoveTrace] = Field(default_factory=list)
    ep_gain: float | None = None
    hit_cost: float = 0.0
    ft_used: int = 0
    ft_after: int = 0
    ft_use_penalty: float = 0.0
    """The per-transfer friction this week, decayed exactly as the objective
    decays it (``milp.py:867``).

    Charged even in a week the chip table recommends a wildcard for: the plan
    on this payload is the base solve, which the solver returned with the
    transfers charged and the free-transfer recurrence running. The week's
    ``note`` says so."""
    ft_shadow: float | None = None
    """What one banked free transfer is worth, priced at the horizon's end:
    flat ``ft_value``, or λ at **this week's** banked count and the weeks left
    after the horizon's last gameweek. The count is the week's and only the
    basis is terminal, because the end of the horizon is the only place the
    objective prices a free transfer at all (``milp.py:878-888``)."""
    ft_basis: Literal["flat", "lambda"] = "flat"
    bank_value: float | None = None
    """``itb_value * bank`` on the horizon's **last** week, which is the only
    week the objective prices the bank at (``milp.py:889``). ``None``
    elsewhere, and ``None`` when the running bank is unknown."""
    theta: float | None = None
    price_charge: float | None = None
    note: str = ""


def _codeable(value) -> bool:
    if not isinstance(value, dict) or value.get("code") is None:
        return False
    try:
        return int(value["code"]) >= 0
    except (TypeError, ValueError):
        return False


class ServedMove(_Frozen):
    """A player on a move or in the XI, in ``advise._named``'s shape plus
    the price the pool gives him (millions; ``None`` when it cannot) and
    the decorations advise adds to a served buy or sell."""

    code: int
    name: str = ""
    position: str = ""
    ep: float = 0.0
    price: float | None = None
    tag: str | None = None
    frequency: float | None = None

    @model_validator(mode="before")
    @classmethod
    def _named_by_code(cls, data):
        if isinstance(data, dict) and data.get("name") is None and data.get("code") is not None:
            return {**data, "name": str(data["code"])}
        return data


class ServedWeek(_Frozen):
    gw: int
    hits: int = 0
    hit_cost: int = 0
    buys: list[ServedMove] = Field(default_factory=list)
    sells: list[ServedMove] = Field(default_factory=list)
    expected_pts: float = 0.0
    chip: str | None = None
    bank: float | None = None
    """What is left after this week's moves, in millions. ``None`` means
    unknown — some move in this week or an earlier one had no price — and
    never 0.0, which is "fully invested"."""
    trace: PlanWeekTrace | None = None


class ServedStep(_Frozen):
    """One step of the ladder's restraint walk (v16 §3), as the ladder
    writes it, with v17b's served sentence."""

    below: str
    above: str
    share: float
    taken: bool
    reason: str = ""
    reason_kind: str = ""
    line: str | None = None


class ServedRestraint(_Frozen):
    chosen: str | None = None
    label: str | None = None
    bar: float | None = None
    steps: list[ServedStep] = Field(default_factory=list)
    agrees: bool = True
    note: str | None = None
    hit_cost: int | None = None
    """Not invented (v17b §3.3): a reader of a block that carries none
    falls back to the config's default."""
    line: str | None = None


class ServedObjective(_Frozen):
    """The solver's own week one, kept beside the served plan (v16 §4),
    and the same week priced, banked and traced under ``week`` so the
    board's objective column is carried rather than rebuilt."""

    buys: list[ServedMove] = Field(default_factory=list)
    sells: list[ServedMove] = Field(default_factory=list)
    hits: int = 0
    expected_pts: float = 0.0
    line: str | None = None
    week: ServedWeek | None = None


def _number_or_none(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else out


class ServedAlternative(_Frozen):
    """A plan the solver ranked behind the recommended one (v12 W3 §4.3),
    under the advice's own ``alternative_plans`` key and shape."""

    gap: float | None = None
    plan_by_gw: list[ServedWeek] = Field(default_factory=list)

    @field_validator("gap", mode="before")
    @classmethod
    def _signed_or_unknown(cls, value):
        # Never 0.0 for unreadable: zero is "exactly level with the
        # recommendation", a real and different claim.
        out = _number_or_none(value)
        return None if out is None else round(out, 2)

    @field_validator("plan_by_gw", mode="before")
    @classmethod
    def _weeks_however_written(cls, raw):
        return list(raw.values()) if isinstance(raw, dict) else raw


class ServedPlan(_Frozen):
    """Field names are the advice JSON's own keys: ``model_dump`` is the
    write and ``model_validate(advice_dict)`` is the read."""

    gw: int
    generated_at: str | None = None
    bank: float | None = None
    """The bank before the horizon's first move, in millions; ``None``
    when the solve state carried no usable figure, never 0.0."""
    buys: list[ServedMove] = Field(default_factory=list)
    sells: list[ServedMove] = Field(default_factory=list)
    hits: int = 0
    xi: list[ServedMove] = Field(default_factory=list)
    bench: list[ServedMove] = Field(default_factory=list)
    captain: ServedMove | None = None
    vice: ServedMove | None = None
    captain_note: str | None = None
    expected_pts: float = 0.0
    plan_by_gw: list[ServedWeek] = Field(default_factory=list)
    objective: ServedObjective | None = None
    restraint: ServedRestraint | None = None
    alternative_plans: list[ServedAlternative] = Field(default_factory=list)

    @field_validator("plan_by_gw", mode="before")
    @classmethod
    def _weeks_however_written(cls, raw):
        # An older writer keyed the horizon by gameweek.
        return list(raw.values()) if isinstance(raw, dict) else raw

    @field_validator("captain", "vice", mode="before")
    @classmethod
    def _armband_or_none(cls, raw):
        # A captain the artifact cannot name is a missing armband, not a
        # missing plan.
        return raw if _codeable(raw) else None


# --- the pool readers, moved whole from routers/plan.py (v17f §4) ---------

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


def pool_prices(pool) -> tuple[dict[int, float], dict[int, float]]:
    """``({code: buy price}, {code: sell value})`` in millions.

    A column the pool does not carry, and a value that is not a number, leave
    that side unpriced. The timeline renders a move with no price; it cannot
    render a 500.
    """
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


def trace_inputs(pool) -> tuple[dict, dict, dict]:
    """``({(code, gw): ep}, {code: position}, {code: name})`` off the pool.

    A pool with no ``ep_raw`` column yields an empty EP table, which the
    trace reports as "not in the pool" per move rather than as a zero.
    """
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
            # A NaN is not a 0.0: leaving the key out is what makes the
            # trace say "not in the pool".
            ep = _float(getattr(row, "ep_raw", None), float("nan"))
            if ep == ep:
                ep_by[(code, _int(getattr(row, "gw", None), -1))] = ep
    return ep_by, positions, player_names


def chip_by_gw(chip_table) -> dict[int, str]:
    """``{gw: chip}`` for chips this run actually recommended playing."""
    out: dict[int, str] = {}
    if not isinstance(chip_table, list):
        return out
    for row in chip_table:
        # A chip the solver could not place writes the key with a null.
        if not (isinstance(row, dict) and row.get("play_now")):
            continue
        if row.get("gw") is None:
            continue
        out[_int(row["gw"], -1)] = str(row.get("chip"))
    out.pop(-1, None)
    return out


def thresholds(chip_table) -> dict[int, float]:
    """``{gw: θ}`` for the chips this run recommends playing.

    A threshold that is not a number is dropped rather than defaulted. 0.0 is
    a real θ — "play it in any week that is not actively worse" — so a string
    where a number belongs must not be served as the most permissive threshold
    the model can have.
    """
    out: dict[int, float] = {}
    if not isinstance(chip_table, list):
        return out
    for row in chip_table:
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


def price_falls(state) -> tuple[bool, dict[int, float]]:
    """``(price_timing is on, {code: p_fall_tonight})`` for the owned squad.

    The same reader the objective's price-timing term uses (W2 §3.4), called
    the same way — so the charge the board prints is not a second estimate
    computed from the same log by slightly different arithmetic. Read at
    write time by advise (v17f §2.2), so a fresh file carries what the
    solve saw; read again only for a file written before v17f, where it
    is a present-tense read and the week note says so.

    ``price_timing`` off means the objective carried **no such term**, so
    the trace reports ``None`` and says so rather than printing a zero. A
    table that will not read is also ``None`` — an unknown, which is not a
    zero chance of a fall.
    """
    from gaffer.config import config_in_force
    from gaffer.price_timing import owned_price_falls

    try:
        if not config_in_force().price_timing:
            return False, {}
        owned = [int(c) for c in getattr(state, "owned_codes", []) or []]
        return True, {int(k): float(v)
                      for k, v in (owned_price_falls(owned) or {}).items()}
    except Exception as exc:  # noqa: BLE001
        print(f"plan trace: price falls unreadable ({exc})")
        return True, {}


# --- the passes: a value in, a value out (v17f §4) -------------------------

def decorated(plan: ServedPlan, *, tags: dict[int, str],
              frequencies: dict[tuple[str, int], float]) -> ServedPlan:
    """The tags and sweep frequencies on the *served* moves (v16 §4): a tag
    for every buy ``tags`` names, a frequency for a buy or sell the sweep
    saw. A move with neither is left unset, so the write carries no null
    for it."""
    def one(kind: str, move: ServedMove) -> ServedMove:
        update: dict = {}
        if kind == "buy" and move.code in tags:
            update["tag"] = tags[move.code]
        if (kind, move.code) in frequencies:
            update["frequency"] = frequencies[(kind, move.code)]
        return move.model_copy(update=update) if update else move
    return plan.model_copy(update={
        "buys": [one("buy", m) for m in plan.buys],
        "sells": [one("sell", m) for m in plan.sells]})


def with_alternatives(plan: ServedPlan, rows) -> ServedPlan:
    """The alternatives typed from the rows advise built, or from the file's
    ``alternative_plans`` on a backfill. ``None`` and ``[]`` are the same
    empty strip."""
    return plan.model_copy(update={
        "alternative_plans": [ServedAlternative.model_validate(r) for r in (rows or [])]})


def with_objective_week(plan: ServedPlan) -> ServedPlan:
    """The objective's own week, synthesised from the four keys a file
    written before v17f carries (§2.3).

    Such a file has ``objective`` with its buys, sells, hits and expected
    points and no ``week``, and the old router built the week from exactly
    those four before pricing it — without this the board loses its
    objective column. ``serve_rung`` writes the week at write time, so a
    loaded plan that already carries one is left alone.
    """
    objective = plan.objective
    if objective is None or objective.week is not None:
        return plan
    week = ServedWeek(gw=plan.gw, hits=objective.hits, buys=objective.buys,
                      sells=objective.sells, expected_pts=objective.expected_pts)
    return plan.model_copy(update={"objective": objective.model_copy(update={"week": week})})


def _priced_moves(moves, prices: dict[int, float]) -> list[ServedMove]:
    return [m.model_copy(update={"price": prices.get(m.code)}) for m in moves]


def _priced_week(week: ServedWeek, buy, sell) -> ServedWeek:
    return week.model_copy(update={"buys": _priced_moves(week.buys, buy),
                                   "sells": _priced_moves(week.sells, sell)})


def _each_week(plan: ServedPlan, fn) -> ServedPlan:
    """``fn(weeks) -> weeks`` over the served weeks, the objective's week
    (as a one-week list) and every alternative's weeks."""
    update: dict = {"plan_by_gw": fn(plan.plan_by_gw),
                    "alternative_plans": [a.model_copy(update={"plan_by_gw": fn(a.plan_by_gw)})
                                          for a in plan.alternative_plans]}
    if plan.objective is not None and plan.objective.week is not None:
        update["objective"] = plan.objective.model_copy(
            update={"week": fn([plan.objective.week])[0]})
    return plan.model_copy(update=update)


def priced(plan: ServedPlan, buy: dict[int, float], sell: dict[int, float]) -> ServedPlan:
    """Every move priced from the pool's two columns: buy price for an in,
    sell value for an out; the XI, bench and armband at buy price, as the
    board's head week always showed them. A code the pool cannot price is
    ``None``."""
    def moves(name, prices):
        return _priced_moves(getattr(plan, name), prices)

    out = _each_week(plan, lambda weeks: [_priced_week(w, buy, sell) for w in weeks])
    return out.model_copy(update={
        "buys": moves("buys", buy), "sells": moves("sells", sell),
        "xi": moves("xi", buy), "bench": moves("bench", buy),
        "captain": None if plan.captain is None else _priced_moves([plan.captain], buy)[0],
        "vice": None if plan.vice is None else _priced_moves([plan.vice], buy)[0]})


def charged(plan: ServedPlan, *, hit_cost: int, chips: dict[int, str]) -> ServedPlan:
    """The hit charge and the chip table's recommendation on every week."""
    return _each_week(plan, lambda weeks: [
        w.model_copy(update={"hit_cost": w.hits * hit_cost, "chip": chips.get(w.gw)})
        for w in weeks])


def _banked_weeks(weeks: list[ServedWeek], start: float | None) -> list[ServedWeek]:
    # v11 §F1: an unpriced move breaks the total permanently. Skipping it
    # would report a bank wrong by exactly that player's price with nothing
    # on the page to say so, and there is no later week at which the sum
    # re-synchronises.
    running = start
    out = []
    for week in weeks:
        moves = [*week.buys, *week.sells]
        if running is not None and all(m.price is not None for m in moves):
            # round(..., 1): every price is one decimal, and float drift over
            # a six-week horizon puts 0.8999999999999995 on the page.
            running = round(running + sum(m.price for m in week.sells)
                            - sum(m.price for m in week.buys), 1)
        else:
            running = None
        out.append(week.model_copy(update={"bank": running}))
    return out


def banked(plan: ServedPlan, start: float | None) -> ServedPlan:
    """The bank run forward from ``start`` (millions) over the served weeks,
    the objective's week and each alternative — one implementation, because
    the board prints their banks side by side."""
    return _each_week(plan, lambda weeks: _banked_weeks(weeks, start)).model_copy(
        update={"bank": start})


def _traced_weeks(weeks: list[ServedWeek], *, state, ep_by, positions, names,
                  theta_by_gw, ft_lambda, price_timing, price_fall) -> list[ServedWeek]:
    from gaffer.league_mode import cover_from_eo
    from gaffer.trace import trace_plan

    opt = state.opt if isinstance(state.opt, dict) else {}
    hit_cost = _int(opt.get("hit_cost", 4), 4)
    # The moves' own names under the pool's: a move can name a player who
    # is not on the solver's candidate list.
    move_names = {m.code: m.name for w in weeks for m in (*w.buys, *w.sells)}
    # ``chip: None``, deliberately: ``plan_by_gw`` is the base solve, which
    # charged this week's transfers and ran the free-transfer recurrence,
    # and telling the trace a wildcard was played would report a charge that
    # was made as zero. θ still comes from the chip table; the note says so.
    rows = trace_plan(
        [{"gw": w.gw, "hits": w.hits, "buys": [m.code for m in w.buys],
          "sells": [m.code for m in w.sells], "chip": None} for w in weeks],
        gws=[int(g) for g in getattr(state, "gws", [])],
        ep_by=ep_by, positions=positions, names={**move_names, **names},
        decay=_float(opt.get("decay", 1.0), 1.0), hit_cost=hit_cost,
        ft_value=_float(opt.get("ft_value", 0.0)),
        itb_value=_float(opt.get("itb_value", 0.0)),
        free_transfers=_int(getattr(state, "free_transfers", 0)),
        ft_lambda=ft_lambda,
        ft_use_penalty=_float(opt.get("ft_use_penalty", 0.0)),
        lam=_float(getattr(state, "lam", 0.0)),
        # ``is not None``, not ``or {}``: an empty cover tilts nothing, and
        # ``or {}`` would report 0.0 for a term the objective applied.
        cover=(state.cover if getattr(state, "cover", None) is not None
               else cover_from_eo(getattr(state, "league_eo", {}) or {})),
        thresholds=theta_by_gw, banks={w.gw: w.bank for w in weeks},
        price_timing=price_timing, price_fall=price_fall)
    out = []
    for week, one in zip(weeks, rows):
        payload = asdict(one)
        if week.chip:
            said = (f"a {week.chip} is recommended this week; these terms are "
                    f"the base plan's, which the solver returned without it")
            payload["note"] = "; ".join(part for part in (payload["note"], said) if part)
        out.append(week.model_copy(update={"trace": PlanWeekTrace(**payload)}))
    return out


def traced(plan: ServedPlan, *, state, theta_by_gw: dict[int, float], ft_lambda,
           price_timing: bool, price_fall: dict[int, float]) -> ServedPlan:
    """The objective's own terms on the served weeks and on the objective's
    week (v12 W5 §6.5, v16 §4) — never on an alternative, which was returned
    by a different solve. A trace that throws costs the trace and not the
    plan: every week is written with ``trace=None`` and one line is printed."""
    try:
        # Inside the guard: a pool that will not read costs the trace and not
        # the plan, which is what the line above promises.
        ep_by, positions, names = trace_inputs(getattr(state, "pool", None))
        kw = dict(state=state, ep_by=ep_by, positions=positions, names=names,
                  theta_by_gw=theta_by_gw, ft_lambda=ft_lambda,
                  price_timing=price_timing, price_fall=price_fall)
        update: dict = {"plan_by_gw": _traced_weeks(plan.plan_by_gw, **kw)}
        if plan.objective is not None and plan.objective.week is not None:
            update["objective"] = plan.objective.model_copy(
                update={"week": _traced_weeks([plan.objective.week], **kw)[0]})
        return plan.model_copy(update=update)
    except Exception as exc:  # noqa: BLE001 — a decoration, never a gate
        print(f"plan trace unavailable for GW{plan.gw}: {exc}")
        untraced = lambda weeks: [w.model_copy(update={"trace": None}) for w in weeks]  # noqa: E731
        update = {"plan_by_gw": untraced(plan.plan_by_gw)}
        if plan.objective is not None and plan.objective.week is not None:
            update["objective"] = plan.objective.model_copy(
                update={"week": untraced([plan.objective.week])[0]})
        return plan.model_copy(update=update)


def completed(plan: ServedPlan, *, state, chip_table) -> ServedPlan:
    """Prices, charges, chips, banks and traces off one solve state — the
    one pass advise runs at write time and ``artifacts.served_plan`` runs
    for a file written before v17f (§2.3). ``generated_at`` is the state's,
    so the two files that describe one run carry one stamp."""
    buy, sell = pool_prices(getattr(state, "pool", None))
    opt = state.opt if isinstance(state.opt, dict) else {}
    ft_lambda = None
    if opt.get("decision_priors"):
        try:
            from gaffer.assets import load_decision_priors
            from gaffer.optimize.ft_value import lambda_from_priors
            ft_lambda = lambda_from_priors(load_decision_priors())
        except Exception as exc:  # noqa: BLE001 — a decoration, never a gate
            print(f"plan trace: no lambda table ({exc}); flat ft_value")
    price_timing, price_fall = price_falls(state)
    out = priced(plan, buy, sell)
    out = charged(out, hit_cost=_int(opt.get("hit_cost", 4), 4), chips=chip_by_gw(chip_table))
    out = banked(out, _price(getattr(state, "bank", None)))
    out = traced(out, state=state, theta_by_gw=thresholds(chip_table), ft_lambda=ft_lambda,
                 price_timing=price_timing, price_fall=price_fall)
    return out.model_copy(update={"generated_at": getattr(state, "generated_at", None)})
