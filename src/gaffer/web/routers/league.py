"""League Race and rival intel.

The only endpoints that need the network: standings, rival picks and rival
histories are not artifacts ``advise`` writes. Every failure is converted to
a readable 422 so the page can show a retry button instead of a stack trace
(spec §4).
"""

from __future__ import annotations

from fastapi import APIRouter

from gaffer.artifacts import latest_gw, load_solve_state
from gaffer.config import load_config
from gaffer.errors import GafferError
from gaffer.league_mode import Strategy, explain_lam, win_probability
from gaffer.web.schemas import (GapPoint, GwPoint, LeagueRace, StandingRow,
                                Trajectory, WinProb)

router = APIRouter(prefix="/api/league", tags=["league"])


def fpl_client():
    """Seam for tests; the real one is the same read-only client the CLI uses."""
    from gaffer.api.client import FPLClient

    return FPLClient()


def _config():
    cfg = load_config()
    if not cfg.league_id:
        raise GafferError("set fpl.league_id in config.toml to use this page")
    return cfg


def _guard(fn, *args, **kwargs):
    """Run an FPL call, turning any failure into a retriable message."""
    try:
        return fn(*args, **kwargs)
    except GafferError:
        raise
    except Exception as exc:  # noqa: BLE001 — network, JSON, schema drift
        raise GafferError(f"FPL API unavailable ({exc}) — retry in a moment") \
            from exc


def _standings(client, league_id: int) -> list[dict]:
    rows, page = [], 1
    while True:
        data = _guard(client.get_league_standings, league_id, page)
        rows.extend(data["standings"]["results"])
        if not data["standings"].get("has_next") or len(rows) >= 50:
            break
        page += 1
    return sorted(rows, key=lambda r: -int(r["total"]))


@router.get("/race", response_model=LeagueRace)
def race() -> LeagueRace:
    cfg = _config()
    client = fpl_client()
    rows = _standings(client, cfg.league_id)
    standings = [StandingRow(entry=int(r["entry"]), name=str(r["entry_name"]),
                             player_name=str(r["player_name"]),
                             rank=int(r["rank"]), total=int(r["total"]),
                             event_total=int(r["event_total"]),
                             is_you=int(r["entry"]) == cfg.entry_id)
                 for r in rows]

    trajectory, by_entry = [], {}
    for row in standings:
        history = _guard(client.get_entry_history, row.entry)
        points = [GwPoint(gw=int(h["event"]), points=int(h["points"]),
                          total=int(h["total_points"]))
                  for h in history.get("current", [])]
        by_entry[row.entry] = {p.gw: p.total for p in points}
        trajectory.append(Trajectory(entry=row.entry, name=row.name,
                                     points=points))

    mine = by_entry.get(cfg.entry_id, {})
    leader = max((t for e, t in by_entry.items() if e != cfg.entry_id),
                 key=lambda t: max(t.values(), default=0), default={})
    gap = [GapPoint(gw=gw, gap=int(mine[gw] - leader.get(gw, 0)))
           for gw in sorted(mine)]

    state = None
    gw = latest_gw()
    if gw is not None:
        state = load_solve_state(gw)
    lam = state.lam if state else 0.0
    my_total = max(mine.values(), default=0)
    weeks_left = 38 - (max(mine, default=1))
    rivals = [row for row in standings if not row.is_you]
    win_probs = [WinProb(name=row.name, total=row.total,
                         p_win=round(win_probability(my_total, row.total,
                                                     max(1, weeks_left)), 3))
                 for row in rivals]
    top = max(rivals, key=lambda r: r.total, default=None)
    stance = "neutral" if lam == 0 else ("chase" if lam > 0 else "defend")
    strategy = Strategy(lam=lam, gap=abs(my_total - (top.total if top else 0)),
                        weeks_left=max(1, weeks_left), stance=stance,
                        rival_name=top.name if top else "the field")
    return LeagueRace(league_id=cfg.league_id, entry_id=cfg.entry_id,
                      standings=standings, trajectory=trajectory, gap=gap,
                      win_probability=win_probs, lam=lam, stance=stance,
                      lam_explained=explain_lam(strategy))
