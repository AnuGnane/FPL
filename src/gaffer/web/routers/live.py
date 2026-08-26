"""Live gameweek: the Saturday-afternoon view, straight off ``live_gw``.

``live_gw.run_live`` prints; this composes the same primitives and returns
them instead. Nothing is persisted, exactly as the module intends.
"""

from __future__ import annotations

from fastapi import APIRouter

from gaffer.artifacts import load_snapshot
from gaffer.config import load_config
from gaffer.data.tier_eo import tier_eo_table
from gaffer.errors import GafferError
from gaffer.live_gw import (active_gameweek, entry_live_points,
                            league_live_table, provisional_bonus)
from gaffer.web.schemas import LivePlayer, LiveState, LiveTableRow

router = APIRouter(prefix="/api", tags=["live"])

INACTIVE = LiveState(active=False, gw=None, my_points=0, matches_in_play=0,
                     players=[], table=[])


def fpl_client():
    """Seam for tests; the real one is the same read-only client the CLI uses."""
    from gaffer.api.client import FPLClient

    return FPLClient()


def _guard(fn, *args, **kwargs):
    """Run an FPL call, turning any failure into a retriable message."""
    try:
        return fn(*args, **kwargs)
    except GafferError:
        raise
    except Exception as exc:  # noqa: BLE001 — network, JSON, schema drift
        raise GafferError(f"FPL API unavailable ({exc}) — retry in a moment") \
            from exc


def _status(minutes: int, in_play: bool) -> str:
    """Per-player state: no minutes yet is "yet to play" either way."""
    if minutes > 0 and not in_play:
        return "played"
    return "playing" if minutes > 0 else "yet to play"


def _finished_by_team(fixtures: list[dict]) -> dict[int, bool]:
    """team id -> "every fixture this team has in the gameweek is over".

    Per-team, not gameweek-wide: a Saturday-lunchtime player has *played*
    while the Sunday games are still to come. In a double gameweek a team is
    only done when both of its matches are.
    """
    out: dict[int, bool] = {}
    for fixture in fixtures:
        done = bool(fixture.get("finished"))
        for side in ("team_h", "team_a"):
            team = fixture.get(side)
            if team is None:
                continue
            out[int(team)] = out.get(int(team), True) and done
    return out


@router.get("/live", response_model=LiveState)
def live() -> LiveState:
    cfg = load_config()
    if not cfg.entry_id:
        raise GafferError("set fpl.entry_id in config.toml to use this page")
    client = fpl_client()
    gw = active_gameweek(_guard(client.get_event_status))
    if gw is None:
        return INACTIVE

    elements = _guard(client.get_event_live, gw)["elements"]
    fixtures = [f for f in _guard(client.get_fixtures)
                if f.get("event") == gw]
    bonus = provisional_bonus(elements, fixtures)
    points_of = {int(e["id"]): (e.get("stats") or {}).get("total_points", 0)
                 for e in elements}
    minutes_of = {int(e["id"]): (e.get("stats") or {}).get("minutes", 0)
                  for e in elements}
    finished_by_team = _finished_by_team(fixtures)

    mine = _guard(client.get_entry_picks, cfg.entry_id, gw)
    my_points = entry_live_points(mine["picks"], points_of, bonus)
    history = mine.get("entry_history") or {}
    my_pre = int(history.get("total_points", 0)) - int(history.get("points",
                                                                  0))

    snapshot = load_snapshot("live/players.parquet")
    by_element = {int(r.element): r for r in snapshot.itertuples()}
    # Tier EO is a display column, never a blocker: any failure leaves the
    # table exactly as it was plus a one-line notice.
    tier: dict[int, dict] = {}
    notice: str | None = None
    if getattr(cfg, "tier_eo", True):
        try:
            tier = tier_eo_table(client, gw, sample=cfg.tier_sample)
            if not tier:
                # No exception, no data: every sampled entry was private or
                # the gameweek has no picks yet. Silence would read as "the
                # top 10k own nobody", so say which it is.
                notice = ("top-10k EO empty this gameweek — league EO only")
        except Exception as exc:  # noqa: BLE001 — network, JSON, page drift
            notice = f"top-10k EO unavailable ({exc}) — league EO only"
    players = []
    for pick in mine["picks"]:
        element = int(pick["element"])
        row = by_element.get(element)
        if row is None:
            continue          # a player removed from the game since the pick
        minutes = int(minutes_of.get(element, 0))
        team_done = finished_by_team.get(int(row.team_id), False)
        sampled = tier.get(element) or {}
        players.append(LivePlayer(
            element=element, code=int(row.code), name=str(row.name),
            position=str(row.position),
            multiplier=int(pick.get("multiplier", 0)),
            points=int(points_of.get(element, 0)),
            provisional_bonus=int(bonus.get(element, 0)),
            minutes=minutes, status=_status(minutes, not team_done),
            tier_eo=sampled.get("eo"), tier_eo_se=sampled.get("se"),
            selected_by_percent=(float(row.selected_by_percent)
                                 if getattr(row, "selected_by_percent", None)
                                 is not None else None)))

    rows = [{"entry": cfg.entry_id, "name": "You", "pre_total": my_pre,
             "live": my_points}]
    if cfg.league_id:
        standings = _guard(client.get_league_standings,
                           cfg.league_id)["standings"]["results"]
        for entry in standings:
            if int(entry["entry"]) == cfg.entry_id:
                continue
            try:
                picks = _guard(client.get_entry_picks, int(entry["entry"]), gw)
            except GafferError:
                continue          # picks not public — skip, as the CLI does
            rows.append({"entry": int(entry["entry"]),
                         "name": str(entry["entry_name"]),
                         "pre_total": int(entry["total"]),
                         "live": entry_live_points(picks["picks"], points_of,
                                                   bonus)})

    table = [LiveTableRow(**row) for row in league_live_table(rows)]
    in_play = sum(1 for f in fixtures
                  if f.get("started") and not f.get("finished"))
    return LiveState(active=True, gw=gw, my_points=my_points,
                     matches_in_play=in_play, players=players, table=table,
                     notice=notice)
