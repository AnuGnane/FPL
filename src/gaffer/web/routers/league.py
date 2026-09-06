"""League Race and rival intel.

The only endpoints that need the network: standings, rival picks and rival
histories are not artifacts ``advise`` writes. Every failure is converted to
a readable 422 so the page can show a retry button instead of a stack trace
(spec §4).
"""

from __future__ import annotations

import threading
import time

from fastapi import APIRouter

from gaffer.artifacts import latest_gw, load_solve_state
from gaffer.config import load_config
from gaffer.errors import GafferError
from gaffer.league_mode import (LeagueParams, Strategy, apply_stance,
                                explain_lam, win_probability)
from gaffer.web.schemas import (GapPoint, GwPoint, LeagueRace, LeaguesOverview,
                                PrivateLeagueRow, PublicLeagueRow, RivalDetail,
                                RivalSummary, SquadPlayer, StandingRow,
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


OVERVIEW_TTL_S = 300.0
"""How long the league list and its gaps are served from memory. Roughly
eight FPL calls uncached, asked for by two hubs."""

_OVERVIEW: dict[int, tuple[float, dict]] = {}
"""entry_id -> (monotonic stamp, rows). Holds only what the FPL API said —
never the focus or the stance, which come from config on every request."""
_OVERVIEW_LOCK = threading.Lock()


def _maybe_int(value) -> int | None:
    return None if value is None else int(value)


def _stance_of(lam: float) -> str:
    return "neutral" if lam == 0 else ("chase" if lam > 0 else "defend")


def _league_rows(client, cfg) -> dict:
    """The entry's classic leagues, split by the private flag, with a gap per
    started private league from one standings page. Cached per entry for
    ``OVERVIEW_TTL_S``.

    The gap is the leader's or the runner-up's total against mine: when I am
    not on page 1 my total is the entry payload's own. A league of one, or
    one with no scored gameweek yet, has no gap.
    """
    now = time.monotonic()
    with _OVERVIEW_LOCK:
        hit = _OVERVIEW.get(cfg.entry_id)
        if hit is not None and now - hit[0] < OVERVIEW_TTL_S:
            return hit[1]
    entry = _guard(client.get_entry, cfg.entry_id)
    my_total = int(entry.get("summary_overall_points") or 0)
    private, public = [], []
    for league in (entry.get("leagues") or {}).get("classic") or []:
        base = {"league_id": int(league["id"]), "name": str(league["name"]),
                "rank": _maybe_int(league.get("entry_rank")),
                "last_rank": _maybe_int(league.get("entry_last_rank")),
                "entries": _maybe_int(league.get("rank_count"))}
        if league.get("league_type") != "x":
            public.append(base)
            continue
        started = base["entries"] is not None
        gap = gap_kind = would = None
        if started and (base["entries"] or 0) > 1:
            page = _guard(client.get_league_standings, base["league_id"], 1)
            results = page["standings"]["results"]
            mine = next((r for r in results
                         if int(r["entry"]) == cfg.entry_id), None)
            total = int(mine["total"]) if mine else my_total
            others = sorted((int(r["total"]) for r in results
                             if int(r["entry"]) != cfg.entry_id), reverse=True)
            if others:
                if base["rank"] == 1:
                    gap, gap_kind, would = total - others[0], "ahead", "defend"
                else:
                    gap, gap_kind, would = others[0] - total, "behind", "chase"
        private.append({**base, "started": started, "gap": gap,
                        "gap_kind": gap_kind, "would": would})
    private.sort(key=lambda r: (r["rank"] if r["rank"] is not None else 10**9,
                                -(r["entries"] or 0)))
    public.sort(key=lambda r: -(r["entries"] or 0))
    rows = {"private": private, "public": public,
            "gw": _maybe_int(entry.get("current_event"))}
    with _OVERVIEW_LOCK:
        _OVERVIEW[cfg.entry_id] = (now, rows)
    return rows


def _focus_strategy(cfg) -> Strategy:
    """The focus league's tilt as the next advise will see it (plan R2): the
    solve state's λ, then the manual stance over it."""
    gw = latest_gw()
    state = load_solve_state(gw) if gw is not None else None
    lam = float(state.lam) if state else 0.0
    base = Strategy(lam=lam, gap=0, weeks_left=1, stance=_stance_of(lam),
                    rival_name="the field")
    return apply_stance(base, cfg.stance, LeagueParams.from_config(cfg))


@router.get("/leagues", response_model=LeaguesOverview)
def leagues() -> LeaguesOverview:
    """Every league the entry is in (v15 §5.1). Does not require a focus:
    with none, or a focus that is not private, the page still lists the
    leagues and says so in ``focus_warning``."""
    cfg = load_config()
    rows = _league_rows(fpl_client(), cfg)
    private = [PrivateLeagueRow(**r, is_focus=r["league_id"] == cfg.league_id)
               for r in rows["private"]]
    focus = next((r for r in private if r.is_focus), None)
    strategy = _focus_strategy(cfg)
    if focus is not None:
        warning = None
    elif cfg.league_id:
        warning = (f"focus league {cfg.league_id} is not one of your private "
                   "leagues — make one the focus below, or reset the focus "
                   "in Settings")
    else:
        warning = "no focus league yet — make one the focus below"
    return LeaguesOverview(
        focus_league_id=int(cfg.league_id), focus_name=focus.name if focus else None,
        stance=cfg.stance, focus_stance=strategy.stance,
        focus_lam=round(strategy.lam, 3), focus_warning=warning,
        private=private,
        public=[PublicLeagueRow(**r) for r in rows["public"]],
        gw=rows["gw"])


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


def _players_snapshot():
    from gaffer.artifacts import load_snapshot

    return load_snapshot("live/players.parquet")


def _my_codes() -> set[int]:
    gw = latest_gw()
    if gw is None:
        raise GafferError("no saved squad — run `gaffer advise` first")
    return {int(c) for c in load_solve_state(gw).owned_codes}


def _last_scored_gw() -> int:
    """Picks are public for finished gameweeks only, so plan-GW minus one."""
    gw = latest_gw()
    if gw is None:
        raise GafferError("no saved advice — run `gaffer advise` first")
    return max(1, load_solve_state(gw).gw - 1)


def _squad(picks: list[dict], players) -> list[SquadPlayer]:
    by_element = {int(r.element): r for r in players.itertuples()}
    out = []
    for pick in picks:
        row = by_element.get(int(pick["element"]))
        if row is None:
            continue          # a player removed from the game since the pick
        out.append(SquadPlayer(
            code=int(row.code), element=int(row.element), name=str(row.name),
            position=str(row.position), price=round(int(row.now_cost) / 10, 1),
            is_captain=int(pick.get("multiplier", 0)) >= 2,
            multiplier=int(pick.get("multiplier", 0))))
    return out


@router.get("/rivals", response_model=list[RivalSummary])
def rivals() -> list[RivalSummary]:
    cfg = _config()
    client = fpl_client()
    players = _players_snapshot()
    mine = _my_codes()
    gw = _last_scored_gw()
    out = []
    for row in _standings(client, cfg.league_id):
        if int(row["entry"]) == cfg.entry_id:
            continue
        try:
            picks = _guard(client.get_entry_picks, int(row["entry"]), gw)
        except GafferError:
            picks = {"picks": []}     # joined late: no public picks yet
        codes = {p.code for p in _squad(picks.get("picks", []), players)}
        out.append(RivalSummary(
            entry=int(row["entry"]), name=str(row["entry_name"]),
            player_name=str(row["player_name"]), rank=int(row["rank"]),
            total=int(row["total"]), event_total=int(row["event_total"]),
            overlap=len(codes & mine), differentials=len(codes - mine)))
    return out


@router.get("/rivals/{entry_id}", response_model=RivalDetail)
def rival(entry_id: int) -> RivalDetail:
    from gaffer.live_gw import active_gameweek, entry_live_points

    cfg = _config()
    client = fpl_client()
    players = _players_snapshot()
    mine = _my_codes()
    row = next((r for r in _standings(client, cfg.league_id)
                if int(r["entry"]) == entry_id), None)
    if row is None:
        raise GafferError(f"entry {entry_id} is not in league {cfg.league_id}")

    squad_gw = _last_scored_gw()
    picks_payload = _guard(client.get_entry_picks, entry_id, squad_gw)
    squad = _squad(picks_payload.get("picks", []), players)
    history = _guard(client.get_entry_history, entry_id)
    entry_history = picks_payload.get("entry_history") or {}
    value = (int(entry_history.get("value", 0))
             + int(entry_history.get("bank", 0))) / 10

    live_points = None
    live_gw = active_gameweek(_guard(client.get_event_status))
    if live_gw is not None:
        elements = _guard(client.get_event_live, live_gw)["elements"]
        points_of = {int(e["id"]): (e.get("stats") or {})
                     .get("total_points", 0) for e in elements}
        live_picks = _guard(client.get_entry_picks, entry_id, live_gw)
        live_points = entry_live_points(live_picks["picks"], points_of, {})

    their = {p.code for p in squad}
    my_squad = _squad([{"element": int(r.element), "multiplier": 1}
                       for r in players[players["code"].isin(mine)]
                       .itertuples()], players)
    return RivalDetail(
        entry=entry_id, name=str(row["entry_name"]),
        player_name=str(row["player_name"]), total=int(row["total"]),
        team_value=round(value, 1),
        chips_used=[str(c["name"]) for c in history.get("chips", [])],
        captain=next((p for p in squad if p.is_captain), None),
        squad_gw=squad_gw, squad=squad,
        shared=[p for p in squad if p.code in mine],
        their_differentials=[p for p in squad if p.code not in mine],
        your_differentials=[p for p in my_squad if p.code not in their],
        live_points=live_points)
