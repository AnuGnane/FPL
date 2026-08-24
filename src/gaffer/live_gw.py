"""In-gameweek tracking: live points for me and for the mini-league.

Read-only. Nothing here is persisted and nothing feeds the optimizer — it is
the Saturday-afternoon view of a gameweek that is still being played.

Two FPL quirks shape the module:

* **Bonus is not in the live payload until a match is settled.** While a game
  is in play the only signal is ``bps``, so :func:`provisional_bonus` recreates
  the 3/2/1 award from the current BPS table, including the real tie rule.
  Once FPL awards the actual bonus it lands inside ``total_points``, and the
  provisional value stands down so nothing is counted twice.
* **Autosubs do not exist mid-gameweek.** A starter who has not kicked off yet
  is indistinguishable from one who blanked, so the XI is taken exactly as
  picked: bench points never count, however the afternoon ends.
"""

from __future__ import annotations

from gaffer.errors import GafferError

BONUS_BY_RANK = (3, 2, 1)


def active_gameweek(status: dict) -> int | None:
    """The gameweek currently in play, or ``None`` between gameweeks.

    ``event-status/`` returns ``{"status": [ {day...}, ... ], "leagues": str}``,
    one entry per match day of the current event, each carrying ``event`` (the
    GW), ``points`` (``"r"`` once that day's scores are raw/confirmed) and
    ``bonus_added``. A gameweek is done when every listed day has its bonus
    added and its points confirmed *and* the league update has finished; until
    then it is still worth tracking. Anything unrecognisable — no days, no
    event id — is treated as "no gameweek in progress" rather than guessed at.
    """
    days = (status or {}).get("status") or []
    events = [d["event"] for d in days if isinstance(d.get("event"), int)]
    if not events:
        return None
    settled = all(d.get("bonus_added") and d.get("points") == "r"
                  for d in days)
    if settled and (status.get("leagues") or "").lower() == "updated":
        return None
    return max(events)


def _fixture_bps(element: dict) -> list[tuple[int, int]]:
    """[(fixture id, bps)] for one live element.

    The per-element ``explain`` list is the only place the live payload names
    a fixture (there is no team id on the element), so an element without one
    cannot be scored. ``explain[].stats`` normally carries a ``bps`` entry; if
    it does not, a single-fixture element can borrow its element-level total,
    but a double gameweek cannot be split and is left alone.
    """
    explain = element.get("explain") or []
    out = []
    for entry in explain:
        fixture = entry.get("fixture")
        if fixture is None:
            continue
        bps = None
        for stat in entry.get("stats") or []:
            if stat.get("identifier") == "bps":
                bps = stat.get("value")
        if bps is None:
            if len(explain) != 1:
                continue
            bps = (element.get("stats") or {}).get("bps", 0)
        out.append((fixture, int(bps or 0)))
    return out


def provisional_bonus(live_elements: list[dict],
                      fixtures_of_gw: list[dict]) -> dict[int, int]:
    """element id -> bonus it would get if its match ended now.

    Top three BPS per fixture, with FPL's real tie rule: ties share the higher
    award and consume the slots below it. ``[50, 50, 40]`` pays 3/3/1,
    ``[50, 40, 40]`` pays 3/2/2, and ``[50, 50, 50, 30]`` pays 3/3/3/0.

    Fixtures that have not kicked off are skipped, as are fixtures where FPL
    has already awarded real bonus (visible as a non-zero ``bonus`` stat) —
    that value is inside ``total_points`` already.
    """
    playable = {f["id"] for f in fixtures_of_gw if f.get("started")}
    by_fixture: dict[int, list[tuple[int, int]]] = {}
    awarded: set[int] = set()
    bonus = {int(e["id"]): 0 for e in live_elements}
    for element in live_elements:
        eid = int(element["id"])
        real = (element.get("stats") or {}).get("bonus") or 0
        for fixture, bps in _fixture_bps(element):
            if fixture not in playable:
                continue
            if real:
                awarded.add(fixture)
            by_fixture.setdefault(fixture, []).append((eid, bps))

    for fixture, entries in by_fixture.items():
        if fixture in awarded:
            continue
        ranked = sorted((e for e in entries if e[1] > 0),
                        key=lambda e: -e[1])
        slot = 0
        while slot < len(ranked) and slot < len(BONUS_BY_RANK):
            tied = [e for e in ranked if e[1] == ranked[slot][1]]
            for eid, _ in tied:
                bonus[eid] += BONUS_BY_RANK[slot]
            slot += len(tied)
    return bonus


def entry_live_points(picks: list[dict], points_of: dict[int, int],
                      bonus: dict[int, int]) -> int:
    """Live points for one entry: sum of multiplier x (points + bonus) over the XI.

    ``multiplier`` already encodes captaincy (2, or 3 under Triple Captain) and
    is 0 for the bench. No autosubs are applied: mid-gameweek there is no way
    to tell a starter who has not played yet from one who never will.
    """
    total = 0
    for pick in picks:
        mult = int(pick.get("multiplier", 0))
        if mult < 1:
            continue
        element = pick["element"]
        total += mult * (points_of.get(element, 0) + bonus.get(element, 0))
    return total


def league_live_table(rows: list[dict]) -> list[dict]:
    """Project the mini-league table forward, with the rank change so far.

    ``rows`` are ``{"name", "pre_total", "live"}``. Each returned row gains
    ``projected`` (pre_total + live) and ``delta``, the places gained (+) or
    lost (-) against the pre-gameweek order.
    """
    pre_order = [r["name"] for r in
                 sorted(rows, key=lambda r: -r["pre_total"])]
    pre_rank = {name: i for i, name in enumerate(pre_order)}
    out = [dict(r, projected=r["pre_total"] + r["live"]) for r in rows]
    out.sort(key=lambda r: -r["projected"])
    for i, row in enumerate(out):
        row["delta"] = pre_rank[row["name"]] - i
    return out


def _arrow(delta: int) -> str:
    if delta > 0:
        return f"▲{delta}"
    if delta < 0:
        return f"▼{-delta}"
    return "-"


def run_live(cfg, client) -> list[dict]:
    """Print the live gameweek: my points, then the projected league table."""
    from gaffer.data.league import fetch_rival_entries, fetch_rival_picks

    gw = active_gameweek(client.get_event_status())
    if gw is None:
        raise GafferError("no gameweek in progress — nothing to track")

    elements = client.get_event_live(gw)["elements"]
    fixtures = [f for f in client.get_fixtures() if f.get("event") == gw]
    bonus = provisional_bonus(elements, fixtures)
    points_of = {int(e["id"]): (e.get("stats") or {}).get("total_points", 0)
                 for e in elements}

    mine = client.get_entry_picks(cfg.entry_id, gw)
    my_live = entry_live_points(mine["picks"], points_of, bonus)
    history = mine.get("entry_history") or {}
    # entry_history.total_points already includes this gameweek's score, so
    # subtract it back out to get a pre-gameweek total comparable with the
    # league standings (which only refresh once the gameweek is scored).
    my_pre = history.get("total_points", 0) - history.get("points", 0)
    rows = [{"name": "You", "pre_total": my_pre, "live": my_live}]

    if cfg.league_id:
        rivals = fetch_rival_entries(client, cfg.league_id, cfg.entry_id)
        picks = fetch_rival_picks(client, rivals["entry"].tolist(), gw)
        for rival in rivals.itertuples():
            if rival.entry not in picks:
                continue        # picks not public (joined late) — skip
            rows.append({
                "name": str(rival.entry_name),
                "pre_total": int(rival.total),
                "live": entry_live_points(picks[rival.entry], points_of, bonus),
            })

    table = league_live_table(rows)
    live_fixtures = sum(1 for f in fixtures if f.get("started")
                        and not f.get("finished"))
    print(f"\n=== GW{gw} live — you: {my_live} pts "
          f"({live_fixtures} match(es) in play) ===")
    print("(bonus is provisional, from current BPS; no autosubs applied)\n")
    width = max(len(r["name"]) for r in table)
    print(f"{'TEAM':<{width}}  {'LIVE':>5}  {'PROJ':>6}  MOVE")
    for row in table:
        print(f"{row['name']:<{width}}  {row['live']:>5}  "
              f"{row['projected']:>6}  {_arrow(row['delta'])}")
    return table
