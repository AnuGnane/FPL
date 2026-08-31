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


def _was_pinned(gw: int, code: int) -> bool:
    """Did ``gw``'s banked availability artifact record a pin on ``code``?

    Never raises: no artifact, no column, an unreadable parquet — all "no",
    because this only ever decides whether a comparison is *shown*.
    """
    try:
        from gaffer.artifacts import load_availability

        banked = load_availability(gw)
        if banked is None or "override" not in getattr(banked, "columns", []):
            return False
        rows = banked[pd.to_numeric(banked["code"],
                                    errors="coerce") == code]
        return bool(rows["override"].fillna(False).any())
    except Exception as exc:  # noqa: BLE001 — a read is never worth a 500
        print(f"overrides: no availability marker for {code} ({exc})")
        return False


COHERENCE_SLACK = 0.3
"""How far ``e_min / 90`` may sit above ``p_play`` before the pin is worth a
second look.

Some slack is real: a nailed starter is 90 minutes at p_play 1.0, but a
regular substitute can be a genuine 0.5 with thirty minutes in him, and the
two numbers are separate claims. Three tenths is wide enough that no ordinary
pin trips it and narrow enough to catch the slip this exists for — minutes
typed for a player the same form says probably will not play.
"""


def _coherence_warning(p_play: float | None, e_min: float | None,
                       model_p_play: float | None) -> str | None:
    """The sentence for a pin whose two numbers disagree, or ``None``.

    Not a refusal. Both values are inside their own ranges and the manager is
    entitled to mean exactly what he typed; this is the endpoint saying it
    noticed, which is what the dialog stays open to show.
    """
    if e_min is None:
        return None
    reference = p_play if p_play is not None else model_p_play
    if reference is None:
        return None
    implied = float(e_min) / 90.0
    if implied <= float(reference) + COHERENCE_SLACK:
        return None
    source = "pinned at" if p_play is not None else "the model's"
    return (f"{e_min:g} minutes implies he plays, but the probability of "
            f"playing is {source} {reference:g} — pin both if you meant it")


def _model_values(code: int) -> tuple[float | None, float | None]:
    """What the served pipeline currently has for ``code``: ``(p_play, e_min)``.

    ``p_play`` comes from this gameweek's component breakdown, averaged over
    the gameweek's fixtures because a double is one answer to "does he play".
    ``e_min`` is not in that file — ``components_frame`` drops it — so it comes
    from the newest news-shadow row for the week, which is the only place the
    served expected minutes are banked.

    Both are ``None`` when nothing has been run yet, and the panel simply
    omits the comparison. Recorded once, at pin time (plan A3).

    They are also ``None`` when the banked availability artifact says this
    player was already pinned when it was written. The readings on disk are
    then the *pinned* numbers — an advise run applies the override and the
    components it writes carry it — so re-reading them after a delete and a
    re-pin would put "the model had 1.00" beside a pin of 1.00: the pin
    looking at itself. The marker is what makes that case detectable, and an
    undetectable comparison is better omitted than invented.
    """
    gw = latest_gw()
    if gw is None:
        return None, None
    if _was_pinned(gw, code):
        print(f"overrides: GW{gw}'s readings for {code} were taken under a "
              f"pin — banking no model comparison")
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
    panel = _panel()
    panel.warning = _coherence_warning(req.p_play, req.e_min, model_p_play)
    return panel


@router.delete("/overrides/{code}", response_model=OverridesPanel)
def unpin(code: int) -> OverridesPanel:
    if not delete_override(int(code)):
        raise HTTPException(status_code=404,
                            detail=f"no override for player {code}")
    return _panel()
