"""GET /api/sensitivity — the banked robustness report for this week's board.

Read-only and never an error. A week nobody has swept is not a degraded state,
it is every week before the button is pressed, so it is a 200 with
``available: false`` and the card shows the button. A report from an *older*
gameweek is also ``available: false``, with a notice: last week's robustness
is not this week's, and a stale card is worse than an empty one. Its numbers
are still in the body — refusing to headline a stale report is not a reason
to hide what it said — but nothing renders them as current.
"""

from __future__ import annotations

import math

from fastapi import APIRouter, Query

from gaffer.artifacts import latest_gw, load_components
from gaffer.sensitivity import load_sensitivity
from gaffer.uncertainty import band_for, shipped_table, xmins_by_player_gw
from gaffer.web.schemas import SensitivityReport

router = APIRouter(prefix="/api", tags=["sensitivity"])


def _plan_codes(plan) -> set[int]:
    """Every player one signature names: its buys, its sells, its captain.

    The captain is in there because an armband is a decision the sweep can
    disagree about, and a margin between two plans that differ only in who
    wears it is separated by exactly that player's noise.
    """
    if not isinstance(plan, dict):
        return set()
    out: set[int] = set()
    for key in ("buys", "sells"):
        for row in plan.get(key) or []:
            if isinstance(row, dict) and row.get("code") is not None:
                out.add(int(row["code"]))
    captain = plan.get("captain")
    if isinstance(captain, dict) and captain.get("code") is not None:
        out.add(int(captain["code"]))
    return out


def decision_sigma(payload: dict, gw: int) -> float | None:
    """Noise on the players that separate the modal plan from the runner-up.

    Plan A6. Not a σ on a whole plan — the table cannot price one, and it does
    not need to: two signatures differ in a handful of named players, so the
    noise that could flip the comparison is the noise on those players and
    nothing else. Summed in quadrature because ``noise_ep`` draws one
    independent standard normal per cell and adds no cross-player correlation.

    ``None`` for every case where the comparison cannot be made honestly: no
    runner-up, no banked components frame, no minutes model, or two signatures
    whose named players happen to coincide. The card then prints its margin
    line exactly as it did before this field existed.
    """
    modal, runner_up = payload.get("modal"), payload.get("runner_up")
    if not modal or not runner_up:
        return None
    codes = _plan_codes(modal) ^ _plan_codes(runner_up)
    if not codes:
        return None
    try:
        comp = load_components(gw)
    except Exception as exc:  # noqa: BLE001 — an honesty line is not a 500
        print(f"sensitivity: no components frame for the noise line ({exc})")
        return None
    try:
        xmins = xmins_by_player_gw(comp)
        ep = (comp[comp["gw"].astype(int) == int(gw)]
              .groupby("code")["ep"].sum().to_dict())
    except Exception as exc:  # noqa: BLE001
        print(f"sensitivity: components frame unusable ({exc})")
        return None

    table = shipped_table()
    total = 0.0
    seen = 0
    for code in codes:
        band = band_for(ep.get(code, 0.0), xmins.get((int(code), int(gw))),
                        table=table)
        if band is None:
            continue
        total += band.sigma ** 2
        seen += 1
    return round(math.sqrt(total), 3) if seen else None


@router.get("/sensitivity", response_model=SensitivityReport)
def sensitivity(gw: int | None = Query(default=None)) -> SensitivityReport:
    current = latest_gw()
    wanted = current if gw is None else int(gw)
    if wanted is None:
        return SensitivityReport()
    payload = load_sensitivity(wanted)
    if payload is None:
        return SensitivityReport(
            gw=wanted,
            notice=f"no sensitivity report for GW{wanted} — run it to see "
                   f"how much of this plan survives the forecast being wrong")
    fields = {k: v for k, v in payload.items()
              if k in SensitivityReport.model_fields and k != "available"}
    banked = payload.get("gw")
    sigma = decision_sigma(payload, int(banked) if banked is not None
                           else wanted)
    if current is not None and banked is not None and int(banked) != current:
        # Served, but not as this week's: the numbers are real and the card is
        # entitled to show what it is refusing to headline.
        return SensitivityReport(available=False, decision_sigma=sigma, **{
            **fields,
            "notice": f"that sensitivity report is GW{int(banked)}'s and the "
                      f"saved board is GW{current} — re-run the sweep to see "
                      f"how much of *this* plan survives"})
    return SensitivityReport(available=True, decision_sigma=sigma, **fields)
