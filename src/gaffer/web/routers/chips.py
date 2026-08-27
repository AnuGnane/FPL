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


def _refs(codes, meta: dict[int, dict]) -> list[SquadPlayerRef]:
    """Codes -> rendered players, in code order.

    A code the saved pool no longer knows is shown by its number rather than
    dropped or raised on: a solve state and an advice file can disagree after
    a partial re-run, and a workbench that 500s because one player moved club
    is worse than one that says "999".
    """
    out = []
    for code in sorted(int(c) for c in codes):
        row = meta.get(code)
        out.append(SquadPlayerRef(
            code=code,
            name=str(row["name"]) if row else str(code),
            position=str(row["position"]) if row else "",
            price=round(float(row["cost"]) / 10, 1) if row else 0.0,
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
                          "ep": row.ep_raw if int(row.gw) == first_gw
                          else meta.get(code, {}).get("ep", row.ep_raw)}

    rows = [ChipWorkbenchRow(chip=str(r.get("chip", "")),
                             gw=int(r.get("gw", first_gw)),
                             gain=float(r.get("gain", 0.0)),
                             per_week=(None if r.get("per_week") is None
                                       else float(r["per_week"])),
                             threshold=(None if r.get("threshold") is None
                                        else float(r["threshold"])),
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
            kept=_refs(squad & owned, meta),
            dropped=_refs(owned - squad, meta),
            added=_refs(squad - owned, meta))
    return ChipsWorkbench(gw=gw, chips=rows, wildcard=wildcard)
