"""The chip workbench's read model (spec §3).

Disk-only and cheap: everything here was computed by ``gaffer advise`` and
written to ``reports/``. The workbench's *interactive* half re-solves through
the existing ``/api/whatif`` job flow, so no solver code lives here either —
this endpoint's whole job is to resolve codes into names, prices and expected
points, and to do the squad set arithmetic once, on the server, instead of in
three places in the page.

``/api/chips/plan`` in ``meta.py`` is a different endpoint and stays where it
is: that one *re-runs* ``evaluate_chips`` against the saved pool, and This
Week has called it since v3.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from gaffer.artifacts import latest_gw, load_advice, load_solve_state
from gaffer.errors import GafferError
from gaffer.web.schemas import (ChipsWorkbench, ChipWorkbenchRow, SquadDiff,
                                SquadPlayerRef)

router = APIRouter(prefix="/api", tags=["chips"])

NO_RUN = "no advice on disk yet — run `gaffer advise` first"


def _refs(codes, meta: dict[int, dict],
          price_key: str = "cost") -> list[SquadPlayerRef]:
    """Codes -> rendered players, in code order.

    ``price_key`` is ``"sell"`` for the players a wildcard drops and ``"cost"``
    for everyone else, because those are two different numbers and the diff
    is about money. A player bought at 7.0 and now worth 8.0 sells for 7.5 —
    FPL takes half the rise — so pricing the Out column at market value
    overstates what the wildcard actually frees up, and the three columns
    stop adding to the budget the solve was run against. Kept and In are
    priced at ``cost`` because that is what they cost to hold or to buy.
    """
    out = []
    for code in sorted(int(c) for c in codes):
        row = meta.get(code)
        price = 0.0
        if row is not None:
            price = round(float(row.get(price_key, row["cost"])) / 10, 1)
        out.append(SquadPlayerRef(
            code=code,
            name=str(row["name"]) if row else str(code),
            position=str(row["position"]) if row else "",
            price=price,
            ep=round(float(row["ep"]), 2) if row else 0.0))
    return out


@router.get("/chips", response_model=ChipsWorkbench)
def chips() -> ChipsWorkbench:
    gw = latest_gw()
    if gw is None:
        raise HTTPException(status_code=404, detail=NO_RUN)
    try:
        advice = load_advice(gw)
        state = load_solve_state(gw)
    except GafferError as exc:
        # 404 rather than the app-wide 422: the page hides its panels on a
        # missing artifact, and must not confuse that with a state it could
        # fix by re-running something.
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    first_gw = state.gws[0] if state.gws else gw
    meta: dict[int, dict] = {}
    for row in state.pool.itertuples():
        code = int(row.code)
        # The pool carries one row per (candidate, gameweek); the first
        # gameweek's is the one the workbench prices against, and the rest
        # differ only in ep_raw.
        if code not in meta or int(row.gw) == first_gw:
            meta[code] = {"name": row.name, "position": row.position,
                          "cost": row.cost,
                          "sell": getattr(row, "sell", row.cost),
                          "ep": row.ep_raw if int(row.gw) == first_gw
                          else meta.get(code, {}).get("ep", row.ep_raw)}

    rows = [ChipWorkbenchRow(chip=str(r.get("chip", "")),
                             gw=int(r.get("gw", first_gw)),
                             # v12 W3 §4.5
                             # (specs/2026-09-01-gaffer-v12-program-design.md)
                             gw2=(None if r.get("gw2") is None
                                  else int(r["gw2"])),
                             gain=float(r.get("gain", 0.0)),
                             per_week=(None if r.get("per_week") is None
                                       else float(r["per_week"])),
                             threshold=(None if r.get("threshold") is None
                                        else float(r["threshold"])),
                             # v12 W3 §4.2
                             # (specs/2026-09-01-gaffer-v12-program-design.md)
                             threshold_source=(
                                 None if r.get("threshold_source") is None
                                 else str(r["threshold_source"])),
                             play_now=bool(r.get("play_now", False)),
                             note=(None if r.get("note") is None
                                   else str(r["note"])))
            for r in advice.get("chip_table") or []
            if isinstance(r, dict)]

    wildcard = None
    wc = advice.get("wildcard_now")
    if isinstance(wc, dict) and wc.get("wc_squad") is not None:
        squad = {int(c) for c in wc["wc_squad"]}
        owned = {int(c) for c in state.owned_codes}
        wildcard = SquadDiff(
            gain_over_horizon=round(float(wc.get("gain_over_horizon", 0.0)),
                                    2),
            recommend=bool(wc.get("recommend", False)),
            # v12 W3 §4.2 (specs/2026-09-01-gaffer-v12-program-design.md): the
            # card showed a verdict and none of the rule behind it.
            threshold=(None if wc.get("threshold") is None
                       else round(float(wc["threshold"]), 2)),
            threshold_source=(None if wc.get("threshold_source") is None
                              else str(wc["threshold_source"])),
            kept=_refs(squad & owned, meta),
            dropped=_refs(owned - squad, meta, price_key="sell"),
            added=_refs(squad - owned, meta))
    return ChipsWorkbench(gw=gw, chips=rows, wildcard=wildcard)
