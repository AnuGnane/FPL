"""``GET /api/prices/movers`` — tonight's changes among watched players.

The advice payload has carried ``price_alerts`` since v2, over a watch set of
squad-plus-plan, and it will keep carrying exactly that: ``advise.py`` is
protected and widening the set there is not a change this cycle is allowed to
make. So the wider set — squad, plan, **and** the watchlist — lives here
instead, and the two lists differ by exactly the starred players on purpose.

Two properties are worth stating because both are load-bearing.

It never touches the network. The readings come off disk — the bootstrap
snapshot every ``refresh`` and every ``advise`` rewrites, and the nightly
price log ``gaffer prices`` banks at 23:15 — because a card that fetched the
bootstrap on a page load would fetch it once per visitor on the one evening
every visitor is looking.

It therefore serves whichever of the two is newer, and says which. The
snapshot is only rewritten when somebody runs a pipeline, so on a Friday whose
last advise run was Tuesday the log is three days fresher;
:func:`gaffer.digest.freshest_prices` picks between them and this router
reports the answer in ``as_of``. A panel that quietly showed Tuesday's
predictor readings on a Friday evening would be worse than showing nothing —
the whole claim the card makes is about *tonight*.
"""

from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter

from gaffer.digest import freshest_prices
from gaffer.prices import price_alerts
from gaffer.watchlist import watch_targets
from gaffer.web.schemas import MoverRow, MoversPanel

router = APIRouter(prefix="/api/prices", tags=["prices"])


def _snapshot() -> tuple[pd.DataFrame | None, str | None]:
    """The freshest banked readings and their age, or ``(None, None)``.

    An absent snapshot and an unreadable one are the same answer: the panel is
    unavailable and the page renders without it. When the price log won, the
    stamp names it — ``as_of`` is the only field the card has to say what it is
    looking at, and "3 hours ago" that silently meant Tuesday would be a lie in
    the one place the card cannot afford one.
    """
    players, as_of, source = freshest_prices()
    if source == "price_log" and as_of:
        as_of = f"{as_of} (price log)"
    return players, as_of


def _cost(value) -> float:
    """The bootstrap's 0.1m integer as the millions the UI shows."""
    try:
        out = float(value) / 10.0
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(out) else round(out, 1)


@router.get("/movers", response_model=MoversPanel)
def movers() -> MoversPanel:
    players, as_of = _snapshot()
    if players is None or players.empty:
        return MoversPanel(available=False, as_of=as_of)
    sources = watch_targets()
    if not sources:
        # Not "unavailable": the snapshot is fine and nothing is watched, and
        # the card's empty state should say so rather than say it is broken.
        return MoversPanel(available=True, as_of=as_of)
    try:
        alerts = price_alerts(players, list(sources))
    except Exception as exc:  # noqa: BLE001 — a card is never worth a 500
        print(f"movers: price alerts unavailable ({exc})")
        return MoversPanel(available=False, as_of=as_of)
    cost_of = dict(zip(players["code"], players.get("now_cost", [])))
    return MoversPanel(available=True, as_of=as_of, rows=[
        MoverRow(code=int(r.code), name=str(r.name),
                 now_cost=_cost(cost_of.get(int(r.code))),
                 price_change_percent=round(float(r.price_change_percent), 1),
                 direction=str(r.direction),
                 calibrating=bool(r.calibrating),
                 source=sources.get(int(r.code), "watchlist"))
        for r in alerts.itertuples()])
