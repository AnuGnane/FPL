"""The week's biggest forecast errors, joined from two banked artifacts.

A calibration page that only ever shows aggregates is a page nobody argues
with. The reliability curves say the heads are well calibrated in the mean;
this says *who* the model got most wrong last week, which is the number a
manager can check against his own memory of the football.

Nothing is computed that was not already on disk: ``reports/components_gw{N}
.parquet`` holds what was forecast, ``data/live/player_gw.parquet`` holds what
happened, and the join is an inner one because a player the results frame does
not cover has not scored nought — he is unknown, and printing him at zero
would put the tool's worst-looking miss on a player who was never in the
data.

That join is also why this card is **late rather than instant**.
``data.live.refresh_live`` drops every gameweek FPL has not marked
``data_checked``, and FPL does not set that flag until bonus points and any
appeals are settled — typically the morning after the last fixture, not the
final whistle. So a Sunday-evening reader gets no misses card for a gameweek
that has visibly finished, and that is correct: the results frame it would
join against does not exist yet, and a card built from provisional bonus
would name the wrong players. :func:`scoreable_gw` therefore answers the last
gameweek that is *both* forecast and settled, which can be a week behind the
one the rest of the tool is planning.
"""

from __future__ import annotations

import re

import pandas as pd

from gaffer import artifacts

MISS_ROWS = 12
"""How many rows the card shows.

Enough that the tail is visible and few enough that it stays a list somebody
reads. Both directions are kept — the over-forecasts are the ones that cost
transfers, the under-forecasts are the ones that cost captaincies.
"""

_COMPONENTS_RE = re.compile(r"components_gw(\d+)\.parquet$")

PLAYER_GW = "live/player_gw.parquet"
PLAYERS = "live/players.parquet"


def component_gws() -> list[int]:
    """Every gameweek with a banked component breakdown, ascending."""
    out = []
    for path in artifacts.REPORTS.glob("components_gw*.parquet"):
        match = _COMPONENTS_RE.search(path.name)
        if match:
            out.append(int(match.group(1)))
    return sorted(out)


def _results() -> pd.DataFrame | None:
    from gaffer.data import store

    if not store.exists(PLAYER_GW):
        return None
    try:
        return store.load(PLAYER_GW)
    except Exception as exc:  # noqa: BLE001 — a card is not worth a 500
        print(f"misses: results frame unreadable ({exc})")
        return None


def scoreable_gw() -> int | None:
    """The newest gameweek that has **both** a forecast and a result.

    Not :func:`gaffer.artifacts.latest_gw`, which is normally the *upcoming*
    week: its components file is the whole point of the advice run and its
    results do not exist yet. Not "the last finished gameweek" either — on a
    fresh clone that may predate every components file on disk. The
    intersection is the only definition that is right in both directions, and
    it is empty exactly when there is nothing honest to show (plan A7).
    """
    live = _results()
    if live is None or live.empty or "gw" not in live.columns:
        return None
    played = set(pd.to_numeric(live["gw"], errors="coerce")
                 .dropna().astype(int))
    both = played & set(component_gws())
    return max(both) if both else None


def _context() -> tuple[dict[int, str], dict[int, str], dict[int, float]]:
    """``(names, positions, prices)`` from the bootstrap snapshot.

    Empty maps when there is no snapshot: the miss is the finding and the name
    is the context, so a clone without a player list still gets its list —
    with codes where the names would be.
    """
    try:
        players = artifacts.load_snapshot(PLAYERS)
    except Exception as exc:  # noqa: BLE001
        print(f"misses: player snapshot unreadable ({exc})")
        return {}, {}, {}
    names = {int(r.code): str(r.name) for r in players.itertuples()}
    positions = {int(r.code): str(r.position) for r in players.itertuples()}
    prices = {int(r.code): round(int(r.now_cost) / 10, 1)
              for r in players.itertuples()}
    return names, positions, prices


def biggest_misses(gw: int) -> list[dict]:
    """The ``MISS_ROWS`` largest ``|actual - ep|`` for one gameweek.

    ``ep`` is summed across the gameweek's fixtures and ``total_points`` with
    it, so a double gameweek is one row: the forecast was for the week and so
    was the return.

    ``[]`` for every absent input. Never raises — the caller is a card on a
    page whose other cards are fine.
    """
    try:
        comp = artifacts.load_components(int(gw))
    except Exception:  # noqa: BLE001 — an absent forecast is an absent card
        return []
    live = _results()
    if live is None or live.empty:
        return []
    if not {"code", "gw", "ep"}.issubset(comp.columns):
        return []
    if not {"code", "gw", "total_points"}.issubset(live.columns):
        return []

    forecast = (pd.DataFrame({
        "code": comp["code"].astype(int), "gw": comp["gw"].astype(int),
        "ep": pd.to_numeric(comp["ep"], errors="coerce").fillna(0.0)})
        .query("gw == @gw").groupby("code", as_index=False)["ep"].sum())
    if forecast.empty:
        return []

    played = live[pd.to_numeric(live["gw"], errors="coerce") == int(gw)]
    if played.empty:
        return []
    actual = pd.DataFrame({
        "code": played["code"].astype(int),
        "total_points": pd.to_numeric(played["total_points"],
                                      errors="coerce").fillna(0.0),
        "minutes": pd.to_numeric(played.get("minutes", 0),
                                 errors="coerce").fillna(0.0),
    }).groupby("code", as_index=False).sum()

    joined = forecast.merge(actual, on="code", how="inner")
    if joined.empty:
        return []
    joined["miss"] = joined["total_points"] - joined["ep"]
    joined = joined.reindex(
        joined["miss"].abs().sort_values(ascending=False).index)

    names, positions, prices = _context()
    return [{
        "code": int(r.code),
        "name": names.get(int(r.code), str(int(r.code))),
        "position": positions.get(int(r.code), ""),
        "price": prices.get(int(r.code)),
        "ep": round(float(r.ep), 2),
        "actual": int(r.total_points),
        "minutes": int(r.minutes),
        "miss": round(float(r.miss), 2),
    } for r in joined.head(MISS_ROWS).itertuples()]
