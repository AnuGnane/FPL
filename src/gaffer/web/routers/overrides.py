"""GET/POST/DELETE ``/api/overrides`` — the user's own team news (spec D1/D2).

The only endpoint in the tool that writes a number the model must then obey,
which is why it is the only one that validates this hard. Reads never fail:
a panel on This Week is worth showing with a missing name in it. Writes fail
loudly and structurally, in the what-if lab's ``{constraint, error, players}``
shape, so the form can render the reason beside the offending field.

The store itself is :mod:`gaffer.overrides`; nothing here does arithmetic.
"""

from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter, HTTPException

from gaffer.artifacts import latest_gw, load_components, load_snapshot
from gaffer.errors import GafferError
from gaffer.news_shadow import SHADOW_PATH, load_shadow
from gaffer.overrides import delete_override, load_overrides, set_override
from gaffer.web.schemas import OverrideRequest, OverrideRow, OverridesPanel

router = APIRouter(prefix="/api", tags=["overrides"])


def _fail(constraint: str, error: str, players: list[int]) -> HTTPException:
    """The what-if lab's structured 422, reused so the UI has one shape."""
    return HTTPException(status_code=422,
                         detail={"constraint": constraint, "error": error,
                                 "players": players})


def _names() -> dict[int, str]:
    """``{code: name}`` from the bootstrap snapshot, or ``{}``."""
    try:
        players = load_snapshot("live/players.parquet")
        return {int(r.code): str(r.name) for r in players.itertuples()}
    except Exception as exc:  # noqa: BLE001 — a read is never worth a 500
        print(f"overrides panel: player snapshot unreadable ({exc})")
        return {}


def _model_values(code: int) -> tuple[float | None, float | None]:
    """What the served pipeline currently has for ``code``: ``(p_play, e_min)``.

    ``p_play`` comes from this gameweek's component breakdown, averaged over
    the gameweek's fixtures because a double is one answer to "does he play".
    ``e_min`` is not in that file — ``components_frame`` drops it — so it comes
    from the newest news-shadow row for the week, which is the only place the
    served expected minutes are banked.

    Both are ``None`` when nothing has been run yet, and the panel simply
    omits the comparison. Recorded once, at pin time (plan A3).
    """
    gw = latest_gw()
    if gw is None:
        return None, None
    p_play = e_min = None
    try:
        comp = load_components(gw)
        rows = comp[(pd.to_numeric(comp["code"], errors="coerce") == code)
                    & (pd.to_numeric(comp["gw"], errors="coerce") == gw)]
        if not rows.empty:
            value = float(pd.to_numeric(rows["p_play"],
                                        errors="coerce").mean())
            p_play = None if math.isnan(value) else round(value, 3)
    except Exception as exc:  # noqa: BLE001
        print(f"overrides: no component reading for {code} ({exc})")
    try:
        from gaffer.data import store

        if store.exists(SHADOW_PATH):
            shadow = load_shadow()
            rows = shadow[(pd.to_numeric(shadow["code"],
                                         errors="coerce") == code)
                          & (pd.to_numeric(shadow["gw"],
                                           errors="coerce") == gw)]
            if rows is not None and not rows.empty:
                newest = rows.sort_values("run_at").iloc[-1]
                value = float(newest["e_min_news"])
                e_min = None if math.isnan(value) else round(value, 1)
    except Exception as exc:  # noqa: BLE001
        print(f"overrides: no shadow reading for {code} ({exc})")
    return p_play, e_min


def _panel() -> OverridesPanel:
    from gaffer.config import serving_config

    names = _names()
    rows = [OverrideRow(code=code, name=names.get(code, str(code)),
                        p_play=row.get("p_play"), e_min=row.get("e_min"),
                        note=str(row.get("note") or ""),
                        set_at=str(row.get("set_at") or ""),
                        model_p_play=row.get("model_p_play"),
                        model_e_min=row.get("model_e_min"))
            for code, row in sorted(load_overrides().items())]
    return OverridesPanel(active=bool(serving_config().news_overrides),
                          rows=rows)


@router.get("/overrides", response_model=OverridesPanel)
def overrides() -> OverridesPanel:
    return _panel()


@router.post("/overrides", response_model=OverridesPanel)
def pin(req: OverrideRequest) -> OverridesPanel:
    known = _names()
    if not known:
        raise _fail("no_player_list",
                    "no player snapshot on disk — run `gaffer advise` before "
                    "pinning anyone", [int(req.code)])
    if int(req.code) not in known:
        raise _fail("unknown_player",
                    f"player {req.code} is not in the current player list",
                    [int(req.code)])
    model_p_play, model_e_min = _model_values(int(req.code))
    try:
        set_override(int(req.code), p_play=req.p_play, e_min=req.e_min,
                     note=req.note, known_codes=list(known),
                     model_p_play=model_p_play, model_e_min=model_e_min)
    except GafferError as exc:
        raise _fail("override_value", str(exc), [int(req.code)]) from exc
    return _panel()


@router.delete("/overrides/{code}", response_model=OverridesPanel)
def unpin(code: int) -> OverridesPanel:
    if not delete_override(int(code)):
        raise HTTPException(status_code=404,
                            detail=f"no override for player {code}")
    return _panel()
