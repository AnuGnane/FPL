"""Live gameweek: the Saturday-afternoon view, straight off ``live_gw``.

``live_gw.run_live`` prints; this composes the same primitives and returns
them instead. Nothing is persisted, exactly as the module intends.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter

from gaffer.artifacts import load_advice, load_components, load_snapshot
from gaffer.config import load_config
from gaffer.data.tier_eo import tier_eo_table
from gaffer.errors import GafferError
from gaffer.live_gw import (active_gameweek, entry_live_points,
                            league_live_table, projected_multipliers,
                            projected_points, projected_subs,
                            provisional_bonus, race_value, remaining_ep_total,
                            remaining_fraction, safety_margins)
from gaffer.web.schemas import (LivePlayer, LiveRacePoint, LiveSafety,
                                LiveState, LiveTableRow)

router = APIRouter(prefix="/api", tags=["live"])

INACTIVE = LiveState(active=False, gw=None, my_points=0, matches_in_play=0,
                     players=[], table=[])

RACE_SERIES: dict[int, list[dict]] = {}
"""gameweek -> this process's poll-by-poll race trajectory.

Deliberately in memory and deliberately per process. Live state is ephemeral;
a restart mid-afternoon losing the last hour's trajectory is a smaller cost
than a file that has to be pruned, versioned and reasoned about between
gameweeks. Only the active gameweek is kept, and it is capped.
"""

RACE_SERIES_MAX = 500
"""Eight hours of minute polling, which outlasts any matchday."""


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


def _gameweek_over(fixtures: list[dict]) -> bool:
    """Every fixture in the gameweek has finished.

    The default for a team that appears nowhere in the fixture list — a blank
    gameweek. Until the last match is over a blank is indistinguishable from a
    fixture still to come; once it is over, the blank is settled and FPL will
    substitute the player who had no match to play in.
    """
    return bool(fixtures) and all(bool(f.get("finished")) for f in fixtures)


def _fixture_counts(fixtures: list[dict]) -> dict[int, tuple[int, int]]:
    """team id -> ``(fixtures this gameweek, of them not yet kicked off)``.

    What turns a double gameweek's summed EP into something that can be spent
    down one match at a time; see :func:`live_gw.remaining_fraction`.
    """
    out: dict[int, tuple[int, int]] = {}
    for fixture in fixtures:
        pending = 0 if fixture.get("started") else 1
        for side in ("team_h", "team_a"):
            team = fixture.get(side)
            if team is None:
                continue
            total, unplayed = out.get(int(team), (0, 0))
            out[int(team)] = (total + 1, unplayed + pending)
    return out


def _finished_by_team(fixtures: list[dict]) -> dict[int, bool]:
    """team id -> "every fixture this team has in the gameweek is over".

    Per-team, not gameweek-wide: a Saturday-lunchtime player has *played*
    while the Sunday games are still to come. In a double gameweek a team is
    only done when both of its matches are. A team with no fixture is absent
    from the result entirely; :func:`_gameweek_over` is what the caller reads
    in its place.
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


def _started_by_team(fixtures: list[dict]) -> dict[int, bool]:
    """team id -> "this team has at least one fixture under way or done".

    The mirror of :func:`_finished_by_team`, and deliberately ``any`` rather
    than ``all``: a player in a double gameweek whose first match has kicked
    off is no longer owed the full pre-match expectation.
    """
    out: dict[int, bool] = {}
    for fixture in fixtures:
        started = bool(fixture.get("started"))
        for side in ("team_h", "team_a"):
            team = fixture.get(side)
            if team is None:
                continue
            out[int(team)] = out.get(int(team), False) or started
    return out


def _ep_by_element(gw: int) -> tuple[dict[int, float], str | None]:
    """element -> this gameweek's banked EP, or ``({}, notice)``.

    The race is a nicety on top of a page that already works, so nothing here
    raises: a missing, stale or unreadable component file degrades the race to
    the projected score and says so on its own card. Double gameweeks sum both
    fixtures' EP; :func:`_fixture_counts` is what lets the caller spend that
    sum down one fixture at a time instead of against the team's aggregate
    state. The residual bias is inside a single fixture and is documented on
    :func:`live_gw.remaining_fraction`, in both directions.
    """
    try:
        frame = load_components(gw)
        wanted = frame[pd.to_numeric(frame["gw"], errors="coerce") == gw]
        elements = pd.to_numeric(wanted["element"], errors="coerce")
        eps = pd.to_numeric(wanted["ep"], errors="coerce").fillna(0.0)
        out: dict[int, float] = {}
        for element, ep in zip(elements, eps):
            if pd.isna(element):
                continue
            out[int(element)] = out.get(int(element), 0.0) + float(ep)
    except GafferError as exc:
        return {}, f"{exc} — the race shows live points only"
    except Exception as exc:  # noqa: BLE001 — schema drift, unreadable parquet
        return {}, (f"component breakdown unreadable ({exc}) — "
                    f"the race shows live points only")
    if not out:
        return {}, (f"no GW{gw} rows in the component breakdown — "
                    f"the race shows live points only")
    return out, None


def _race_reference(gw: int) -> float | None:
    """The pre-gameweek plan's expected score, when it is *this* gameweek's."""
    try:
        advice = load_advice(gw)
    except Exception:  # noqa: BLE001 — absent, pruned or half-written
        return None
    if int(advice.get("gw", -1)) != gw:
        return None
    expected = advice.get("expected_pts")
    return None if expected is None else round(float(expected), 2)


def _project(picks: list[dict], points_of: dict[int, int],
             bonus: dict[int, int], minutes_of: dict[int, int],
             started_of: dict[int, bool], finished_of: dict[int, bool],
             positions: dict[int, str], ep_of: dict[int, float],
             counts_of: dict[int, tuple[int, int]]
             ) -> tuple[list[dict], dict[int, int], int, float]:
    """One entry's projection: ``(subs, multipliers, points, remaining EP)``.

    Used for me and for every rival, on the same terms — their picks are
    already fetched to score them, and the EP table is one read for the whole
    league, so the full treatment costs no extra API call. A rival holding a
    player who is not in the snapshot simply projects no sub for him.
    """
    subs = projected_subs(picks, minutes_of, finished_of, positions)
    multipliers = projected_multipliers(picks, subs, minutes_of, finished_of)
    points = projected_points(points_of, bonus, multipliers)
    remaining = remaining_ep_total(multipliers, ep_of, minutes_of, started_of,
                                   finished_of, counts_of)
    return subs, multipliers, points, remaining


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
    started_by_team = _started_by_team(fixtures)
    counts_by_team = _fixture_counts(fixtures)
    gameweek_over = _gameweek_over(fixtures)
    ep_of, race_notice = _ep_by_element(gw)

    mine = _guard(client.get_entry_picks, cfg.entry_id, gw)
    my_points = entry_live_points(mine["picks"], points_of, bonus)
    history = mine.get("entry_history") or {}
    my_pre = int(history.get("total_points", 0)) - int(history.get("points",
                                                                  0))

    snapshot = load_snapshot("live/players.parquet")
    by_element = {int(r.element): r for r in snapshot.itertuples()}
    positions = {int(r.element): str(r.position)
                 for r in snapshot.itertuples()}
    team_of = {int(r.element): int(r.team_id) for r in snapshot.itertuples()}
    # A team with no fixture is absent from both tables. It counts as finished
    # only once the whole gameweek is (the blank is settled, and its players
    # are sub-out candidates); as never started, so it owes nothing it could
    # have banked.
    finished_of = {element: finished_by_team.get(team, gameweek_over)
                   for element, team in team_of.items()}
    started_of = {element: started_by_team.get(team, False)
                  for element, team in team_of.items()}
    counts_of = {element: counts_by_team.get(team, (1, 0))
                 for element, team in team_of.items()}
    my_subs, my_multipliers, my_projected, my_remaining = _project(
        mine["picks"], points_of, bonus, minutes_of, started_of, finished_of,
        positions, ep_of, counts_of)
    sub_out = {int(s["out_element"]): s for s in my_subs}
    sub_in = {int(s["in_element"]): s for s in my_subs}
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
        team_done = finished_of.get(element, False)
        sampled = tier.get(element) or {}
        # What he still owes *me*, which is what the projected eleven would
        # score him at: nothing at all if he is not on that pitch, and double
        # if he is wearing the armband on it.
        projected_mult = int(my_multipliers.get(element, 0))
        fixtures_total, unplayed = counts_of.get(element, (1, 0))
        remaining_ep = (
            round(max(projected_mult, 0)
                  * float(ep_of.get(element, 0.0))
                  * remaining_fraction(minutes,
                                       started_of.get(element, False),
                                       finished_of.get(element, False),
                                       fixtures=fixtures_total,
                                       unplayed=unplayed), 2)
            if ep_of and projected_mult >= 1 else 0.0 if ep_of else None)
        out_of = sub_out.get(element)
        into = sub_in.get(element)
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
                                 is not None else None),
            projected_out=out_of is not None,
            projected_in=into is not None,
            sub_partner=(int(out_of["in_element"]) if out_of
                         else int(into["out_element"]) if into else None),
            sub_reason=((out_of or into or {}).get("reason")
                        if (out_of or into) else None),
            remaining_ep=remaining_ep))

    rows = [{"entry": cfg.entry_id, "name": "You", "pre_total": my_pre,
             "live": my_points, "projected_live": my_projected,
             "remaining_ep": my_remaining,
             "race": race_value(my_projected, my_remaining)}]
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
            _, _, projected, remaining = _project(
                picks["picks"], points_of, bonus, minutes_of, started_of,
                finished_of, positions, ep_of, counts_of)
            rows.append({"entry": int(entry["entry"]),
                         "name": str(entry["entry_name"]),
                         "pre_total": int(entry["total"]),
                         "live": entry_live_points(picks["picks"], points_of,
                                                   bonus),
                         "projected_live": projected,
                         "remaining_ep": remaining,
                         "race": race_value(projected, remaining)})

    table_rows = league_live_table(rows)
    safety = [LiveSafety(**margin)
              for margin in safety_margins(table_rows, cfg.entry_id)]
    table = [LiveTableRow(**row) for row in table_rows]

    # The trajectory: one point per poll, this process only, this gameweek
    # only. Nothing is written to disk and nothing survives a restart.
    leader = next((r for r in table_rows
                   if int(r.get("entry", -1)) != cfg.entry_id), None)
    my_race = race_value(my_projected, my_remaining)
    for stale in [key for key in RACE_SERIES if key != gw]:
        RACE_SERIES.pop(stale, None)
    series = RACE_SERIES.setdefault(gw, [])
    series.append({
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "you": my_race,
        "leader": (float(leader["race"]) if leader
                   and leader.get("race") is not None else None)})
    del series[:-RACE_SERIES_MAX]

    in_play = sum(1 for f in fixtures
                  if f.get("started") and not f.get("finished"))
    return LiveState(active=True, gw=gw, my_points=my_points,
                     matches_in_play=in_play, players=players, table=table,
                     notice=notice, my_projected_points=my_projected,
                     my_race=my_race, race_reference=_race_reference(gw),
                     race_series=[LiveRacePoint(**point) for point in series],
                     safety=safety,
                     leader_name=(str(leader["name"]) if leader else None),
                     race_notice=race_notice)
