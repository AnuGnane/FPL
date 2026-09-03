"""Why the plan makes each move (v12 W5 §6.5).

**Accounting, not a counterfactual.** Every number here is a term of the MILP's
own objective (``optimize/milp.py:805-889``) evaluated at the plan the solver
already returned. None of them is "the plan is this much better than not doing
this move" — that is a re-solve, and §6.5 exists precisely so that no view
solves.

The spec put this inside ``milp.py``, in ``_decision_scales``' neighbourhood.
It is here instead, for two reasons (plan A8). ``_decision_scales`` computes
autosub frailty weights between two solves and never sees a transfer, a price
or a hit — its neighbourhood is the wrong neighbourhood. And a "read-only
accounting" function that lives in the module which builds the objective is one
refactor away from being read *by* the objective; the way to guarantee it
changes no decision is to put it where no decision can see it. A test in
``tests/test_v12_w5_trace.py`` asserts that ``advise.py`` and every module under
``optimize/`` import this file nowhere.

**What is attributed and what is not.** The objective's transfer-side terms are
all here: the decayed EP difference of a position-matched swap, the decayed hit
charge, the per-transfer friction, the price-timing charge, the terminal free
transfer and bank values, and the league tilt. Its *squad*-side terms are
not — the XI, captain and vice weightings and the three bench seats, each of
which depends on the whole fifteen and on a per-week autosub scale
(``milp.py:813-835``, ``_decision_scales``), not on one swap. A swap changes
them, and there is no honest way to say by how much without re-solving. The
week docstring and the board's caption both say so, because a reader who adds
these lines up and finds they miss the week's xPts is owed the reason.

Pure. No I/O, no network, no pandas. Everything it needs is already on disk in
``SolveState`` and the advice payload, and the caller — ``routers/plan.py`` —
loads both anyway. That includes the price-fall probabilities: the router calls
W2's own ``owned_price_falls`` and hands the answer in, so this module reads no
log of its own and the charge it prints is computed from the same numbers the
objective's term was.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gaffer.optimize.milp import MAX_FREE_TRANSFERS, SEASON_LAST_GW

PRICE_TIMING_COEFF = 0.1
"""W2 §3.4's coefficient: a later-week sell is charged
``p_fall_tonight * 0.1 * itb_value``. Restated here rather than imported so
this module has no reason to reach into the objective, and asserted against the
spec in the test file.

Applied only when ``price_timing`` is on. With the setting off the objective
carries no such term at all, and a reported zero would say "we checked and it
was free" — a different sentence from "we did not charge for this"."""


@dataclass(frozen=True)
class MoveTrace:
    gw: int
    buy_code: int | None
    buy_name: str
    sell_code: int | None
    sell_name: str
    ep_gain: float | None
    """Decayed expected points the swap adds over the rest of the horizon.

    ``Σ_{k=i..n-1} decay**k * (ep[buy][T[k]] - ep[sell][T[k]])``, where ``k``
    indexes the *whole* horizon from zero because that is what ``d = decay **
    t_i`` does in the objective. ``None`` when the pair could not be formed or
    either side has no expected points in the pool — never 0.0, which is a
    measured tie."""
    lambda_tilt: float | None
    """What the league tilt did to that difference. Positive means the tilt
    made this swap more attractive than raw points alone. 0.0 at ``lam = 0``,
    which is a real and measured answer."""
    note: str = ""


@dataclass(frozen=True)
class WeekTrace:
    """One planned week's charges, in the objective's own terms.

    Four of these are week-level on purpose: a week with two transfers and one
    hit cannot attribute the hit to one of them, and splitting it would be
    arithmetic dressed as a finding.

    **What this week does not attribute.** The captain, vice and bench
    weightings — ``d * e * (xi + cap_mult * cap + vw * vice)`` and the three
    bench seats at ``milp.py:813-835``, including the per-week autosub scales
    ``_decision_scales`` supplies — are not here. They price the whole squad,
    not a swap, and a share of them assigned to one transfer would be invented.
    So these lines do not sum to the week's expected points, and they are not
    meant to.
    """

    gw: int
    moves: list[MoveTrace] = field(default_factory=list)
    ep_gain: float | None = None
    """The week's paired moves summed, or ``None`` if any one of them is
    unknown. Not "the rest of them": a total short by one move is a confident
    number that is wrong by exactly that move."""
    hits: int = 0
    hit_cost: float = 0.0
    """``hit_cost * decay**i * hits`` — the objective's own charge
    (``milp.py:837``), so a hit taken in week three does not cost four points
    of this week's money."""
    ft_used: int = 0
    ft_after: int = 0
    ft_use_penalty: float = 0.0
    """``ft_use_penalty * decay**i * transfers`` — the per-transfer friction at
    ``milp.py:867``, waived on a wildcard exactly as the objective waives it.

    A charge, and charges are the half an accounting layer must not drop: an
    omitted charge flatters the move it was charged against. 0.0 when the
    coefficient is 0.0, which is a measured "there is no such friction" rather
    than an unknown."""
    ft_shadow: float | None = None
    """What one banked free transfer is worth, priced at the horizon's end.

    Flat ``ft_value``, or ``λ(this week's banked count, the weeks left after
    the horizon's last gameweek)``. The count is **this week's** and only the
    basis is terminal: λ is concave in the count, so the same table answers
    differently for a week holding one and a week holding four, and
    ``weeks_left`` is the horizon's because the end of the horizon is the only
    place the objective prices a free transfer at all (``milp.py:878-888``).

    It is not the intra-horizon price of spending one — the model does not
    price that either."""
    ft_basis: str = "flat"
    bank_value: float | None = None
    """``itb_value * bank`` — the objective's terminal bank term
    (``(itb_value / 10) * bank[T[-1]]`` at ``milp.py:889``, in tenths, against
    a bank stated here in millions).

    Reported on the horizon's **last** week only, because that is the only
    week the objective prices the bank at. ``None`` everywhere else, and
    ``None`` when the running bank itself is unknown — 0.0 is "fully
    invested", which is a state a manager can really be in."""
    theta: float | None = None
    price_charge: float | None = None
    note: str = ""


def _name(code: int | None, names: dict) -> str:
    """A player's name, or an em dash for a side of the swap that is not there.

    ``names.get(None, str(None))`` puts the word "None" on the board, where it
    reads as a player. The em dash is what every other unknown in this UI
    prints.
    """
    if code is None:
        return "—"
    return str(names.get(code, code))


def _pair(sells: list[int], buys: list[int],
          positions: dict[int, str]) -> list[tuple[int | None, int | None]]:
    """``[(buy, sell)]`` matched by position, unmatched sides carried as None.

    A local six lines rather than ``review.pair_by_position``: that module
    loads the ledger and the journal on import, and the plan router has no
    business paying for either to label a transfer.

    A code the ``positions`` map does not know is matched with nothing. Two
    unknowns are not a position match — ``None == None`` would pair a
    goalkeeper with a striker on a pool that lost its position column, and a
    guessed pair prices a swap that was never made.
    """
    left = list(sells)
    out: list[tuple[int | None, int | None]] = []
    for buy in buys:
        want = positions.get(buy)
        match = (None if want is None else
                 next((s for s in left if positions.get(s) == want), None))
        if match is not None:
            left.remove(match)
        out.append((buy, match))
    out.extend((None, s) for s in left)
    return out


def trace_plan(weeks, *, gws: list[int], ep_by: dict, positions: dict,
               names: dict, decay: float, hit_cost: float, ft_value: float,
               itb_value: float, free_transfers: int, ft_lambda=None,
               ft_use_penalty: float = 0.0, lam: float = 0.0,
               cover: dict | None = None, thresholds: dict | None = None,
               banks: dict | None = None, price_timing: bool = False,
               price_fall: dict | None = None) -> list[WeekTrace]:
    """One :class:`WeekTrace` per planned week, in the order given.

    ``weeks`` is ``[{"gw", "buys": [code], "sells": [code], "hits", "chip"}]``
    — exactly what ``plan_by_gw`` holds once the router has parsed it.
    ``ep_by`` is ``{(code, gw): raw expected points}``, straight off the solve
    state's pool. ``banks`` is ``{gw: bank in millions after that week}``, of
    which only the horizon's last week is ever priced.

    ``price_timing`` and ``price_fall`` come from W2's own reader by way of the
    router. ``price_timing=False`` — the default, and what a build without W2
    gets — reports ``None`` for every charge and says why, rather than a zero.

    Nothing is mutated. Every input is read and every output is frozen.
    """
    order = {g: i for i, g in enumerate(list(gws))}
    tilted = _tilted(ep_by, cover or {}, lam)
    thresholds = thresholds or {}
    price_fall = price_fall or {}
    banks = banks or {}
    last_gw = list(gws)[-1] if gws else None
    weeks_left = max(1, SEASON_LAST_GW - (last_gw if gws else 0))
    use_lambda = ft_lambda is not None and not getattr(ft_lambda, "empty",
                                                       True)
    ft = int(free_transfers)
    out: list[WeekTrace] = []

    for entry in weeks:
        gw = int(entry.get("gw", 0))
        i = order.get(gw)
        buys = [int(c) for c in entry.get("buys") or []]
        sells = [int(c) for c in entry.get("sells") or []]
        hits = int(entry.get("hits") or 0)
        chip = entry.get("chip")
        wildcard = str(chip or "").lower() in ("wildcard", "wc")

        moves, notes = [], []
        if i is None:
            notes.append(f"GW{gw} is not in the solved horizon {list(gws)}, "
                         "so nothing here can be priced against it")
        for buy, sell in _pair(sells, buys, positions):
            gain, tilt, note = _swap(buy, sell, i, gws, order, ep_by, tilted,
                                     decay)
            moves.append(MoveTrace(
                gw=gw, buy_code=buy, buy_name=_name(buy, names),
                sell_code=sell, sell_name=_name(sell, names),
                ep_gain=gain, lambda_tilt=tilt, note=note))

        gains = [m.ep_gain for m in moves]
        week_gain = (None if any(g is None for g in gains)
                     else round(sum(gains), 3))

        if wildcard:
            used, after = 0, min(MAX_FREE_TRANSFERS, ft + 1)
        else:
            used = min(len(buys), ft)
            after = min(MAX_FREE_TRANSFERS,
                        max(0, ft - len(buys) + hits) + 1)

        # The price-timing charge, W2 §3.4: only a sell scheduled for a *later*
        # week is charged, because selling now is what the term encourages.
        #
        # Gated on ``price_timing`` (orchestrator ruling 1, 2026-09-02). With
        # the setting off the objective carries no such term at all, so
        # reporting a number would price a charge the solver never paid — and
        # a zero would say "we checked and it was free", which is a different
        # claim from "we did not charge for this".
        if not price_timing:
            charge = None
            if sells and i not in (None, 0):
                notes.append("price_timing is off, so the plan was solved "
                             "without a price-timing term")
        elif i is None or i == 0 or not sells:
            charge = 0.0
        elif all(c in price_fall for c in sells):
            charge = round(sum(price_fall[c] * PRICE_TIMING_COEFF * itb_value
                               for c in sells), 6)
        else:
            charge = None
            notes.append("the chance of a price fall was not recorded for "
                         "every player sold here, so the price-timing charge "
                         "is unknown")

        d = decay ** i if i is not None else 1.0
        # The terminal bank term is one term on one week (milp.py:889). An
        # intermediate week's bank is not priced by the objective, and a
        # number reported for it would be a term the solver never carried.
        terminal = last_gw is not None and gw == last_gw
        bank = banks.get(gw) if terminal else None
        out.append(WeekTrace(
            gw=gw, moves=moves, ep_gain=week_gain, hits=hits,
            hit_cost=round(hit_cost * d * hits, 3), ft_used=used,
            ft_after=after,
            ft_use_penalty=(0.0 if wildcard
                            else round(ft_use_penalty * d * len(buys), 4)),
            ft_shadow=(round(ft_lambda(max(1, after), weeks_left), 4)
                       if use_lambda else float(ft_value)),
            ft_basis="lambda" if use_lambda else "flat",
            bank_value=(None if bank is None
                        else round(float(itb_value) * float(bank), 4)),
            theta=thresholds.get(gw), price_charge=charge,
            note="; ".join(notes)))
        ft = after
    return out


def _tilted(ep_by: dict, cover: dict, lam: float) -> dict:
    """``tilt_ep``'s answer, or the raw table when the tilt is neutral.

    Imported lazily: ``league_mode`` pulls pandas in, and a plan with no tilt
    should not pay for it.
    """
    if not lam:
        return dict(ep_by)
    from gaffer.league_mode import tilt_ep

    return tilt_ep(dict(ep_by), dict(cover), float(lam))


def _swap(buy, sell, i, gws, order, ep_by, tilted, decay):
    """One pair's ``(ep_gain, lambda_tilt, note)``."""
    if buy is None or sell is None:
        side = "buy" if sell is None else "sell"
        return (None, None,
                f"no {'sell' if side == 'buy' else 'buy'} of the same "
                "position to pair this move with, so it cannot be priced as "
                "a swap")
    if i is None:
        return None, None, "outside the solved horizon"
    horizon = list(gws)[i:]
    missing = [c for c in (buy, sell)
               if not any((c, g) in ep_by for g in horizon)]
    if missing:
        return (None, None,
                f"player {missing[0]} is not in the pool the solver used, so "
                "no expected points can be read for him")
    gain = tilt = 0.0
    for g in horizon:
        d = decay ** order[g]
        gain += d * (ep_by.get((buy, g), 0.0) - ep_by.get((sell, g), 0.0))
        tilt += d * ((tilted.get((buy, g), 0.0) - tilted.get((sell, g), 0.0))
                     - (ep_by.get((buy, g), 0.0) - ep_by.get((sell, g), 0.0)))
    return round(gain, 3), round(tilt, 3), ""
