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


def _bench_order(picks: list[dict]) -> list[int]:
    """Bench elements in the order FPL would bring them on.

    ``position`` 12-15 is the substitution order the manager set; sorting by
    it rather than trusting the payload's order is free insurance against a
    client that reordered the list.
    """
    bench = [p for p in picks if int(p.get("multiplier", 0)) < 1]
    bench.sort(key=lambda p: int(p.get("position", 0)))
    return [int(p["element"]) for p in bench]


def _starting_xi(picks: list[dict]) -> list[int]:
    return [int(p["element"]) for p in picks
            if int(p.get("multiplier", 0)) >= 1]


def projected_subs(picks: list[dict], minutes_of: dict[int, int],
                   finished_of: dict[int, bool],
                   positions: dict[int, str]) -> list[dict]:
    """The auto-subs FPL would make if the afternoon ended as it stands.

    ``finished_of`` is per *element*: True when every fixture that player's
    team has in this gameweek is over. That is the whole ambiguity the module
    docstring warns about, resolved: a starter on zero minutes whose matches
    are finished has blanked and will be substituted; a starter on zero
    minutes whose match is still to come is simply not on yet, and is left
    exactly where he is.

    The same rule decides the blank gameweek, one step out from the caller: a
    player whose team has *no* fixture at all has nothing that can finish, so
    he is only "finished" once every fixture in the gameweek is over. Until
    then he is left alone, because mid-afternoon a blank is indistinguishable
    from a match still to come and the page claims nothing it cannot see.

    The bench is walked in order and the first *legal* swap wins, under
    :func:`gaffer.backtest._formation_legal` — the same rule the replay scores
    with, imported rather than copied so the projected XI and the scored XI
    cannot drift apart. That rule is what keeps the bench keeper for the
    keeper: two GKPs in an eleven is not a formation, and neither is none.

    A bench player is eligible when he has minutes (he is definitely on) or
    when his own matches are unfinished (he may still play); the ``reason`` on
    each returned row says which, because those two are not equally certain
    and the UI should not pretend they are. A bench player who has finished on
    zero blanked too, and is skipped.

    Returns ``[{"out_element", "in_element", "reason"}]``, empty when the
    squad is not the usual eleven-and-four — a Bench Boost week has nobody
    left to bring on, and a half-read payload should not have a formation
    invented for it.
    """
    from gaffer.backtest import _formation_legal

    xi = _starting_xi(picks)
    bench = _bench_order(picks)
    if len(xi) != 11 or not bench:
        return []

    def blanked(element: int) -> bool:
        return (bool(finished_of.get(element, False))
                and int(minutes_of.get(element, 0) or 0) == 0)

    used = set(xi)
    subs: list[dict] = []
    for slot, starter in enumerate(list(xi)):
        if not blanked(starter):
            continue
        for sub in bench:
            if sub in used or blanked(sub):
                continue
            trial = list(xi)
            trial[slot] = sub
            if not _formation_legal([str(positions.get(c, "MID"))
                                     for c in trial]):
                continue
            xi = trial
            # ``used`` guards against one bench player filling two holes, so
            # the man coming off leaves it and the man coming on joins it.
            # The discard mirrors ``backtest``'s replay loop rather than
            # improving on it: a starter already substituted can never be
            # revisited (the outer loop moves on), so this only matters if
            # some later rule wants to reuse the slot, and the two paths stay
            # line-for-line comparable.
            used.discard(starter)
            used.add(sub)
            subs.append({
                "out_element": starter, "in_element": sub,
                "reason": ("played" if int(minutes_of.get(sub, 0) or 0) > 0
                           else "yet to play")})
            break
    return subs


def projected_multipliers(picks: list[dict], subs: list[dict],
                          minutes_of: dict[int, int],
                          finished_of: dict[int, bool]) -> dict[int, int]:
    """element -> the multiplier the projected eleven would score it at.

    Two edits to the picked multipliers. The substitutions from
    :func:`projected_subs` take the outgoing player to 0 and bring the
    incoming one on at 1 — never at the outgoing player's multiplier, because
    FPL hands a blanked captain's armband to the *vice*, not to whoever
    replaced him. Then the armband itself moves, if and only if the captain
    has finished on zero minutes and the vice is on the projected pitch: a
    vice left on the bench is not doubled in the real game either.

    The armband's size is read from the picks, so a Triple Captain week moves
    a 3 rather than a 2.
    """
    mult = {int(p["element"]): int(p.get("multiplier", 0)) for p in picks}
    # Read the armband off the picks, before the substitutions: a captain who
    # blanked is taken off the pitch below, and reading it afterwards would
    # see a squad with no captain in it and leave the armband where it fell.
    armband = max(mult.values(), default=0)
    for sub in subs:
        mult[int(sub["out_element"])] = 0
        mult[int(sub["in_element"])] = 1

    if armband < 2:
        return mult                      # no captaincy in this payload

    captain = next((int(p["element"]) for p in picks if p.get("is_captain")),
                   None)
    if captain is None:
        captain = next((int(p["element"]) for p in picks
                        if int(p.get("multiplier", 0)) == armband), None)
    vice = next((int(p["element"]) for p in picks
                 if p.get("is_vice_captain")), None)
    if captain is None:
        return mult
    # A captain sitting on the bench cannot reach here: ``armband`` is the
    # largest multiplier in the payload, so a benched captain would leave it
    # at 1 and the ``armband < 2`` return above would already have fired. The
    # ``min`` below is therefore always ``min(2 or 3, 1)``; it is written as a
    # clamp rather than a bare 1 so a future chip that benches an armband
    # degrades quietly instead of promoting him.
    if not (bool(finished_of.get(captain, False))
            and int(minutes_of.get(captain, 0) or 0) == 0):
        return mult

    # The captain blanked: he scores at most as an ordinary starter from here
    # (zero either way), and the armband goes to the vice if he is on.
    mult[captain] = min(mult.get(captain, 0), 1)
    if vice is not None and mult.get(vice, 0) >= 1:
        mult[vice] = armband
    return mult


def projected_points(points_of: dict[int, int], bonus: dict[int, int],
                     multipliers: dict[int, int]) -> int:
    """The projected eleven's live score, scored by ``entry_live_points``.

    The pinned function is handed a synthetic pick list rather than being
    changed: its no-autosub contract is exactly what its three callers want,
    and the projection is a different question asked of the same arithmetic.
    """
    return entry_live_points(
        [{"element": element, "multiplier": mult}
         for element, mult in multipliers.items()], points_of, bonus)


FULL_MATCH_MINUTES = 90


def remaining_fraction(minutes: int, started: bool, finished: bool,
                       fixtures: int = 1, unplayed: int = 0) -> float:
    """How much of a player's expectation is still to be earned, in [0, 1].

    Before kick-off he owes all of it; at full time none of it; in between,
    the share of ninety minutes not yet played.

    ``fixtures`` and ``unplayed`` carry the double gameweek. The banked EP a
    caller holds is the *sum* over a player's fixtures, so each fixture is
    worth ``1 / fixtures`` of it: a fixture not yet kicked off owes all of its
    share, and the one in play owes the share of its ninety minutes still to
    come. ``started``/``finished`` stay team-aggregate — any fixture under
    way, every fixture over — which is what the live payload can actually
    tell us. The defaults are the single gameweek, so every existing caller
    keeps exactly the arithmetic it had.

    Two known biases, in opposite directions, both left in the open:

    * **Overstated.** A player in the squad who never comes on reads as owing
      his fixture's whole share right up to the final whistle, because the
      live payload carries his minutes and not the match clock. That is the
      same optimism the pre-deadline EP already had, and it corrects itself
      the moment his fixture is marked finished.
    * **Understated.** Minutes are cumulative across a double gameweek's
      fixtures, so a man who played the first match in full reads as ninety
      minutes into the second and owes none of it. The unplayed fixtures are
      counted exactly; only the one in play is read this way, so the error is
      bounded by a single fixture's share.
    """
    if finished:
        return 0.0
    if not started:
        return 1.0
    played = int(minutes or 0)
    in_play = max(0.0, 1.0 - played / FULL_MATCH_MINUTES)
    total = max(1, int(fixtures or 1))
    return min(1.0, (int(unplayed or 0) + in_play) / total)


def remaining_ep_total(multipliers: dict[int, int], ep_of: dict[int, float],
                       minutes_of: dict[int, int],
                       started_of: dict[int, bool],
                       finished_of: dict[int, bool],
                       counts_of: dict[int, tuple[int, int]] | None = None
                       ) -> float:
    """Expected points still to come from a projected eleven.

    ``multipliers`` is :func:`projected_multipliers`' output, so a projected
    substitute contributes his own expectation and the man he replaced
    contributes none. Players with no banked EP — bought after the advice ran,
    or never in the candidate pool — contribute nothing rather than raising:
    an incomplete race is worth more on a Saturday than no race at all.

    ``counts_of`` is ``element -> (fixtures this gameweek, of them not yet
    kicked off)``, and is what makes a double gameweek spend down fixture by
    fixture rather than in one lump. Absent, every element is read as a single
    fixture, which is the pre-v8d behaviour exactly.
    """
    counts = counts_of or {}
    total = 0.0
    for element, mult in multipliers.items():
        if int(mult) < 1:
            continue
        ep = float(ep_of.get(element, 0.0) or 0.0)
        if not ep:
            continue
        fixtures, unplayed = counts.get(element, (1, 0))
        total += int(mult) * ep * remaining_fraction(
            int(minutes_of.get(element, 0) or 0),
            bool(started_of.get(element, False)),
            bool(finished_of.get(element, False)),
            fixtures=fixtures, unplayed=unplayed)
    return round(total, 2)


def race_value(projected: int, remaining: float) -> float:
    """Where a gameweek score is heading: what is banked plus what is owed.

    Gameweek-level, not cumulative — the pre-gameweek plan's ``expected_pts``
    is the reference line this is drawn against, and that is a one-week
    number.
    """
    return round(float(projected) + float(remaining), 2)


def league_live_table(rows: list[dict]) -> list[dict]:
    """Project the mini-league table forward, with the rank change so far.

    ``rows`` are ``{"entry", "name", "pre_total", "live"}``. Each returned row
    gains ``projected`` (pre_total + live) and ``delta``, the places gained
    (+) or lost (-) against the pre-gameweek order.

    Ranks are keyed by ``entry`` — the FPL entry id — because mini-league
    entry names are not unique: two rivals sharing a name would collapse into
    one pre-gameweek rank and both get the same wrong arrow. ``name`` is the
    fallback for callers that have no ids.

    A caller that has projected the auto-subs (``live_gw.projected_points``)
    may add ``projected_live`` to a row, and the projection is taken from
    that instead of from ``live``. It is a deliberate improvement to this
    column: ``live`` applies no auto-subs, so a table built from it
    understates every entry carrying a finished blank. The key is optional
    and the fallback is the old arithmetic exactly, so the CLI tracker and
    every caller that has no projection are unaffected.
    """
    def key(r: dict):
        return r.get("entry", r["name"])

    pre_order = sorted(rows, key=lambda r: -r["pre_total"])
    pre_rank = {key(r): i for i, r in enumerate(pre_order)}
    out = [dict(r, projected=int(r["pre_total"])
                + int(r.get("projected_live", r["live"]))) for r in rows]
    out.sort(key=lambda r: -r["projected"])
    for i, row in enumerate(out):
        row["delta"] = pre_rank[key(row)] - i
    return out


def safety_margins(table: list[dict], entry: int) -> list[dict]:
    """The three league places worth watching, from a projected table.

    ``table`` is :func:`league_live_table`'s output, already ordered by
    projected total. Returns at most three rows — the entry immediately
    above me, the one immediately below, and the leader — each carrying
    ``margin`` (their projected total minus mine, so positive means they are
    ahead) and ``need`` (the points I must add beyond my current projection
    to pass them, and 0 when I already have).

    Deduplicated by entry and ordered above, below, leader: when the leader
    *is* the man immediately above me he gets one row, labelled with the
    actionable role rather than the flattering one.

    League-relative only. An overall-rank safety score would need the whole
    field's live scores, and no public endpoint gives them; the card says so
    rather than implying this number is one.
    """
    order = [int(r.get("entry", -1)) for r in table]
    try:
        me = order.index(int(entry))
    except ValueError:
        return []

    mine = int(table[me]["projected"])
    wanted = []
    if me > 0:
        wanted.append(("above", me - 1))
    if me + 1 < len(table):
        wanted.append(("below", me + 1))
    if me != 0:
        wanted.append(("leader", 0))

    out, seen = [], set()
    for role, index in wanted:
        row = table[index]
        rival = int(row.get("entry", -1))
        if rival in seen:
            continue
        seen.add(rival)
        margin = int(row["projected"]) - mine
        out.append({"entry": rival, "name": str(row["name"]), "role": role,
                    "margin": margin, "need": max(margin + 1, 0)})
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
    rows = [{"entry": cfg.entry_id, "name": "You",
             "pre_total": my_pre, "live": my_live}]

    if cfg.league_id:
        rivals = fetch_rival_entries(client, cfg.league_id, cfg.entry_id)
        picks = fetch_rival_picks(client, rivals["entry"].tolist(), gw)
        for rival in rivals.itertuples():
            if rival.entry not in picks:
                continue        # picks not public (joined late) — skip
            rows.append({
                "entry": int(rival.entry),
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
