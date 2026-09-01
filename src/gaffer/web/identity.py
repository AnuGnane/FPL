"""Team identity and the week's fixture, joined onto an advice payload.

The pitch needs three things the advice artifact does not carry: which club a
player belongs to, which shirt to draw for that club, and who he plays this
week. All three are already on disk — ``players.parquet`` knows every player's
``team_code``, ``teams.parquet`` turns that into a short name, and
``fixtures_all.parquet`` holds the week's games — and none of them is a number
the model produced. So nothing here computes: this module is three joins and a
lookup.

It resolves at **serve time** rather than at solve time, and that is a
constraint rather than a preference. ``gaffer.advise`` writes the payload's
player entries and is a protected file, so the fields cannot be added where
the payload is built. Serving is where ``routers/advice.py`` already backfills
``position`` onto payloads written before positions existed
(``with_positions``), for the same reason, and the same two benefits follow:
every advice file already on disk gains the fields without a re-solve, and the
artifact's own bytes never change.

**Nothing here raises.** This Week rendered its advice without any of these
fields yesterday; a decoration that can 500 the page it decorates is worse
than no decoration. Every read is wrapped, every failure prints, and the
worst case is the payload handed back exactly as it arrived.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

import pandas as pd

from gaffer.data import store

PLAYER_KEYS = ("xi", "bench", "buys", "sells", "captain", "vice")
"""The advice keys holding player dicts.

Deliberately the same tuple ``routers/advice.PLAYER_KEYS`` walks, and
deliberately wider than the pitch needs: enriching ``buys`` and ``sells``
costs one dict lookup each on a payload of about twenty entries, and it is
what lets v9b put a shirt beside a transfer without editing this function
(plan A3).
"""

NEW_FIELDS = ("team_short", "team_code", "next_fixture")
"""What this module adds, and the complete list of it. Anything already on an
entry is left exactly as it was."""


_CACHE: dict[str, tuple[tuple, Any]] = {}
"""One slot per relative path, keyed on the backing file's identity.

v9d §3a (specs/2026-09-01-gaffer-v9d-design.md). These three parquets are
re-read and re-projected into dicts on every advice request, on a machine that
rewrites them a few times a day. No TTL: a refreshed parquet has a new mtime
and misses naturally, which is both simpler and more correct than a clock.

The key resolves ``store.DATA_DIR`` **on every call** rather than at import.
The data directory is a module-level ``Path`` and the test suite changes the
process CWD constantly; a key on the relative string alone would serve one
tmpdir's teams file out of another's, and in production would survive a
``--data-dir`` change. One slot per path, so the cache holds three entries and
a changed file evicts its own — except the fixture map, whose slot carries the
gameweek too (a map built for GW9 is not GW10's), which is why the dict is
bounded rather than fixed at three: see :data:`_CACHE_MAX`.
"""

_CACHE_LOCK = threading.Lock()
"""Held across the whole of :func:`_memo` — lookup, build, store *and* evict.

The eviction loop reads ``next(iter(_CACHE))`` while another thread may be
storing into the same dict, and under a threadpool that is not a theoretical
race: it raises ``RuntimeError('dictionary changed size during iteration')``,
or ``KeyError`` when two threads pop the same oldest slot. Neither exception is
caught in ``_memo``; both escape into ``with_identity``'s blanket ``except``,
which returns the payload *undecorated*. A page silently losing every shirt
because two requests arrived together is exactly the failure this module's
"nothing here raises" contract exists to prevent.

**The build runs inside the lock**, so two threads missing the same slot at
once do the read twice in series rather than in parallel. That is deliberate.
The builds are three small parquet reads projected into dicts — the very cost
the memo exists to amortise, paid once per file rewrite — and holding the lock
across them also gives the cache a second property worth more than the
concurrency: a slot is built and stored atomically, so no thread ever observes
a half-populated map or evicts a slot another thread is about to store into.
Building outside the lock would need a per-slot in-flight marker to keep that,
and a marker is more moving parts than the parallelism buys back here.
"""

_CACHE_MAX = 16
"""Slots kept before the oldest is dropped, insertion-ordered.

The fixed slots plus one fixture slot per gameweek in flight. Traffic
alternating between two gameweeks — a live matchday page beside a planning one
— is the case this exists for: one slot per path would have each request evict
the other's map and re-read the parquet every time, which is the cost the memo
was added to remove.

Count the fixed slots, because the headroom is what is left over after them.
This module holds two (``live/teams.parquet``, ``live/players.parquet``) and
``web/field_frame`` shares the same cache for three more — code→element,
element→player and the most-captained events map — so five before a single
gameweek is looked at. At eight that left three gameweek slots, and v10b spent
the headroom the bound was chosen for: two pages on two gameweeks already
touch four. Sixteen leaves eleven, which restores the "any plausible number of
gameweeks at once" the original number stood for, and is still small enough
that the cache cannot grow into a leak on a long-running process."""


def _file_key(rel: str) -> tuple | None:
    """``(path, mtime_ns, size)``, or ``None`` when the file cannot be stat'd.

    ``None`` means "read it uncached", not "fail": this module's standing
    contract is that nothing here raises, and a missing snapshot is already
    handled by every caller below.
    """
    try:
        path = store.DATA_DIR / rel
        st = path.stat()
        return (str(path), st.st_mtime_ns, st.st_size)
    except OSError:
        return None


_FAILED = object()
"""What a reader's ``except`` branch hands :func:`_memo` instead of its empty
map, so a failed read is never cached: the file may be readable next call, and
an empty map banked under a live mtime would outlive the outage. Identity by
``is``; an empty map that is genuinely the file's content still caches."""


def _memo(slot: str, key: tuple | None, build: Callable[[], Any]) -> Any:
    """``build()``, memoised under ``slot`` while ``key`` holds.

    A build that returns :data:`_FAILED` is passed straight through and not
    stored.

    The whole path is under :data:`_CACHE_LOCK`, including ``build()``; see
    that docstring for why the read is serialised rather than the store alone.
    An unkeyed call (``key is None``, an unstattable file) builds outside the
    lock: it touches the cache neither to read nor to write, so it has nothing
    to serialise against.
    """
    if key is None:
        return build()
    with _CACHE_LOCK:
        hit = _CACHE.get(slot)
        if hit is not None and hit[0] == key:
            return hit[1]
        value = build()
        if value is not _FAILED:
            _CACHE[slot] = (key, value)
            while len(_CACHE) > _CACHE_MAX:
                # Insertion order, so the slot dropped is the one least
                # recently *stored*. Nothing here is expensive enough to
                # justify tracking reads, and the fixed three are re-read for
                # the price of one parquet if they ever do fall out.
                #
                # ``next(iter(...))`` walks a dict no other thread can be
                # mutating, because every writer holds this same lock.
                _CACHE.pop(next(iter(_CACHE)))
        return value


def clear_cache() -> None:
    """Drop every memoised map. For tests, and for a reader who wants one.

    Under the same lock as :func:`_memo`: clearing mid-eviction is the other
    way to make that loop's ``next(iter(...))`` chase a slot that is gone.
    """
    with _CACHE_LOCK:
        _CACHE.clear()


def _teams() -> tuple[dict[int, str], dict[int, int]]:
    """``({team_code: short_name}, {team_id: team_code})``, or two empty maps.

    Both directions come off one file read because both are needed on every
    call: the first names a club, the second turns a fixture's ``home_id``
    into the code the shirt endpoint and the identity field speak.

    Memoised on the snapshot's own identity (v9d §3a). A failure is *not*
    cached: the next call may find the file readable.
    """
    def build() -> tuple[dict[int, str], dict[int, int]]:
        try:
            teams = store.load("live/teams.parquet")
            return ({int(c): str(s)
                     for c, s in zip(teams["code"], teams["short_name"])},
                    {int(i): int(c)
                     for i, c in zip(teams["team_id"], teams["code"])})
        except Exception as exc:  # noqa: BLE001 — identity is never fatal
            print(f"identity: teams snapshot unreadable ({exc})")
            return _FAILED

    rel = "live/teams.parquet"
    value = _memo(rel, _file_key(rel), build)
    return ({}, {}) if value is _FAILED else value


def _player_teams() -> dict[int, int]:
    """``{player_code: team_code}``, or an empty map.

    A missing ``team_code`` column is the case G2 names explicitly: a bootstrap
    from an older cache must produce nulls and a printed line, not a
    ``KeyError`` on the way out of a page.

    Memoised on the snapshot's own identity (v9d §3a); a failure is not cached.
    """
    def build() -> Any:
        try:
            players = store.load("live/players.parquet")
            if "team_code" not in players.columns:
                raise KeyError("players snapshot has no team_code column")
            pairs = players[["code", "team_code"]].dropna()
            return {int(c): int(t)
                    for c, t in zip(pairs["code"], pairs["team_code"])}
        except Exception as exc:  # noqa: BLE001
            print(f"identity: player snapshot unreadable ({exc})")
            return _FAILED

    rel = "live/players.parquet"
    value = _memo(rel, _file_key(rel), build)
    return {} if value is _FAILED else value


def _fixture_by_team(gw: int, code_of: dict[int, int],
                     short_of: dict[int, str]) -> dict[int, dict]:
    """``{team_code: {opponent_short, home, kickoff_utc}}`` for one gameweek.

    The first **unfinished** fixture per team, by kickoff. Unfinished because a
    team that has already played this week has no next fixture in it, and
    first-by-kickoff because a double gameweek keeps only its opener this
    cycle (spec D2) and "the opener" has to mean the same thing on every
    reload.

    ``kickoff_utc`` is the banked string passed through unparsed. FPL
    publishes fixtures with a null kickoff while the date is TBC, and a chip
    reading "MUN (H) TBC" is true where an invented time would not be.
    Formatting belongs to the client, which knows the reader's timezone.

    Memoised on the fixture file's identity *plus* the teams file's and the
    gameweek (v9d §3a, plan A8): the output embeds short names read off
    ``teams.parquet``, and a map built for GW9 is not GW10's.
    """
    def build() -> Any:
        out: dict[int, dict] = {}
        try:
            if not store.exists("live/fixtures_all.parquet"):
                raise FileNotFoundError("data/live/fixtures_all.parquet")
            fixtures = store.load("live/fixtures_all.parquet")
            week = fixtures[(fixtures["gw"] == int(gw))
                            & (~fixtures["finished"].astype(bool))]
            week = week.sort_values("kickoff_time", na_position="last")
        except Exception as exc:  # noqa: BLE001
            print("identity: fixtures unreadable, no next-fixture chips "
                  f"({exc})")
            return _FAILED
        for fx in week.itertuples():
            home = code_of.get(int(fx.home_id))
            away = code_of.get(int(fx.away_id))
            if home is None or away is None:
                continue
            kickoff = getattr(fx, "kickoff_time", None)
            kickoff = (None if kickoff is None or pd.isna(kickoff)
                       else str(kickoff))
            for own, other, is_home in ((home, away, True),
                                        (away, home, False)):
                # setdefault, not assignment: the frame is sorted by kickoff,
                # so the first row a team appears in is its opener.
                out.setdefault(own, {"opponent_short": short_of.get(other),
                                     "home": is_home, "kickoff_utc": kickoff})
        return out

    rel = "live/fixtures_all.parquet"
    key = _file_key(rel)
    if key is not None:
        # The output embeds short names off teams.parquet, so that file's
        # identity belongs in the key. A renamed club is not the same map.
        key = key + (_file_key("live/teams.parquet"),)
    # The gameweek is in the *slot*, not only the key: a map built for GW9 is
    # not GW10's, and with one shared slot two gameweeks' traffic would take
    # turns evicting each other and re-reading the parquet every request.
    value = _memo(f"{rel}:{int(gw)}", key, build)
    return {} if value is _FAILED else value


def _difficulty_by_team(gws: list[int]) -> dict[tuple[int, int], float]:
    """``{(team_code, gw): difficulty}`` from the ticker's own rating.

    The ticker is *called*, not reimplemented (plan A4). Its odds lookup, its
    Elo fallback, its rate-the-fixture-once-from-the-home-side rule and its
    clamp are sixty lines inside ``routers/meta.ticker``, and a second copy
    beside them would be a second answer to "how hard is this fixture" drawn
    on the same page in the same colour scale — a disagreement nobody could
    see. ``weeks=2`` rather than 1 because ``ticker`` slices the first *n*
    unfinished gameweeks and a mid-week reload can find the advice gameweek
    second in that window.

    Every failure is an empty map, which means every chip renders without its
    tint and with everything else intact.
    """
    from gaffer.web.routers import meta

    try:
        table = meta.ticker(weeks=2)
    except Exception as exc:  # noqa: BLE001 — a tint is never fatal
        print(f"identity: no fixture difficulty available ({exc})")
        return {}
    wanted = {int(g) for g in gws}
    return {(int(team.code), int(cell.gw)): float(cell.difficulty)
            for team in table.teams for cell in team.cells
            if int(cell.gw) in wanted}


def with_identity(payload: dict, gw: int) -> dict:
    """Return ``payload`` with ``team_short``/``team_code``/``next_fixture``.

    Additive and non-mutating: the caller's dict is the one ``load_advice``
    returned, and a route that enriched it in place would leak the decoration
    into anything holding a reference. Pre-existing keys on every entry are
    passed through untouched, which is what makes the G2 byte-identity rail
    hold.

    ``gw`` is the advice gameweek, supplied by the caller rather than read off
    the payload: the router already knows it, and a payload whose ``gw`` field
    is missing should still get its shirts.
    """
    try:
        short_of, code_of = _teams()
        team_of = _player_teams()
        fixtures = _fixture_by_team(int(gw), code_of, short_of)
        difficulty = _difficulty_by_team([int(gw)])
    except Exception as exc:  # noqa: BLE001 — the whole join is decoration
        print(f"identity: not applied ({exc})")
        return payload

    def decorate(entry: Any) -> Any:
        if not isinstance(entry, dict) or "code" not in entry:
            return entry
        try:
            code = int(entry["code"])
        except (TypeError, ValueError):
            return entry
        team_code = team_of.get(code)
        fixture = None
        if team_code is not None and team_code in fixtures:
            fixture = dict(fixtures[team_code])
            fixture["difficulty"] = difficulty.get((team_code, int(gw)))
        return {**entry,
                "team_short": short_of.get(team_code)
                if team_code is not None else None,
                "team_code": team_code,
                "next_fixture": fixture}

    out = dict(payload)
    for key in PLAYER_KEYS:
        value = out.get(key)
        if isinstance(value, list):
            out[key] = [decorate(e) for e in value]
        elif isinstance(value, dict):
            out[key] = decorate(value)
    return out
