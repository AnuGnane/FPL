"""``GET /api/prices/movers`` — tonight's changes among watched players.

The advice payload has carried ``price_alerts`` since v2, over a watch set of
squad-plus-plan, and it will keep carrying exactly that: ``advise.py`` is
protected and widening the set there is not a change this cycle is allowed to
make. So the wider set — squad, plan, **and** the watchlist — lives here
instead, and the two lists differ by exactly the starred players on purpose.

Two properties are worth stating because both are load-bearing.

It never touches the network. The reading comes off
``data/live/players.parquet``, the snapshot every ``refresh`` and every
``advise`` rewrites, because a card that fetched the bootstrap on a page load
would fetch it once per visitor on the one evening every visitor is looking.

It therefore says how old the reading is. ``as_of`` is that file's mtime, the
card prints it, and a panel that quietly showed Tuesday's predictor readings
on a Friday evening would be worse than showing nothing — the whole claim the
card makes is about *tonight*.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter

from gaffer.data import store
from gaffer.prices import price_alerts
from gaffer.watchlist import watch_targets
from gaffer.web.schemas import MoverRow, MoversPanel

router = APIRouter(prefix="/api/prices", tags=["prices"])

PLAYERS_PATH = "live/players.parquet"


def _snapshot() -> tuple[pd.DataFrame | None, str | None]:
    """The banked bootstrap slice and its age, or ``(None, None)``.

    An absent file and an unreadable one are the same answer: the panel is
    unavailable and the page renders without it. The mtime is read before the
    parquet so a file that exists but will not parse still cannot 500.
    """
    if not store.exists(PLAYERS_PATH):
        return None, None
    path = store.DATA_DIR / PLAYERS_PATH
    try:
        stamp = datetime.fromtimestamp(path.stat().st_mtime,
                                       tz=timezone.utc).isoformat(
                                           timespec="seconds")
    except OSError:
        stamp = None
    try:
        return store.load(PLAYERS_PATH), stamp
    except Exception as exc:  # noqa: BLE001 — a card is never worth a 500
        print(f"movers: player snapshot unreadable ({exc})")
        return None, stamp


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
