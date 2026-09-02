"""The watchlist: players the manager is keeping an eye on.

The tool has always had an implicit watchlist — the squad, plus whoever this
week's solve wants to buy — and that is the set ``gaffer prices`` and the
advice payload's alerts have watched. It is the wrong set for the question a
manager actually asks on a Wednesday, which is about the player he is
*thinking* about and the optimizer has not recommended yet. There was nowhere
to write that player down.

This is that place, and it is deliberately the smallest thing that could be:
a code, an optional note, and a timestamp. It is :mod:`gaffer.overrides`'s
store with the two numbers taken out, and taking them out removes the entire
reason that module validates as hard as it does. An override is a claim the
model must obey. A star claims nothing — it widens the price-alert watch set
(:mod:`gaffer.web.routers.prices`) and it adds a section to the Friday digest,
and that is the complete list of things it can do.

Nothing here is read by anything that solves, trains, or scores, and nothing
here is ever a feature. A star is a bookmark.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from gaffer import artifacts
from gaffer.errors import GafferError
from gaffer.io import atomic_write

MAX_WATCHED = 100
"""Stars beyond which this stopped being a shortlist.

A hundred where :data:`gaffer.overrides.MAX_OVERRIDES` is fifty, and the
difference is the point. Fifty pins is a second model; a hundred bookmarks is
two squads' worth of candidates, which is what a manager comparing options
across a wildcard actually has open.
"""

NOTE_MAX = 200
"""Characters. Refused rather than truncated, for ``overrides.py``'s reason: a
silently halved note is a sentence the user did not write."""


def watchlist_path() -> Path:
    """``reports/watchlist.json``, resolved at call time.

    ``artifacts.REPORTS`` is relative, so a test that changes directory
    changes this with it — the trade every other report store makes.
    """
    return artifacts.REPORTS / "watchlist.json"


def load_watchlist() -> dict[int, dict]:
    """``{code: {note, set_at}}``. Never raises.

    An absent file, a hand-edited one, a half-written one and a file whose
    top-level shape has drifted all come back as ``{}``. The print is what
    makes the difference between "nothing is starred" and "the store is
    broken" visible, because a silently empty watchlist is a card that looks
    like it is working.
    """
    path = watchlist_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
        rows = raw.get("watchlist") if isinstance(raw, dict) else None
        if not isinstance(rows, dict):
            return {}
        out: dict[int, dict] = {}
        for code, row in rows.items():
            if not isinstance(row, dict):
                continue
            out[int(code)] = {"note": str(row.get("note") or ""),
                              "set_at": str(row.get("set_at") or "")}
        return out
    except Exception as exc:  # noqa: BLE001 — a bad store is an empty one
        print(f"watchlist store unreadable, ignoring it: {exc}")
        return {}


def save_watchlist(rows: dict[int, dict]) -> Path:
    """Write the whole store atomically.

    ``overrides.save_overrides``'s idiom. An empty store is written as an
    empty object rather than deleted: a reader cannot tell an absent file from
    a half-written one, and unstarring the last player should not put the
    store into the state a crash would. Two saves can race in from concurrent
    HTTP handlers, which is what the atomic write is for.
    """
    payload = {"watchlist": {str(code): dict(row)
                             for code, row in sorted(rows.items())}}
    artifacts.REPORTS.mkdir(parents=True, exist_ok=True)
    path = watchlist_path()
    atomic_write(path, json.dumps(payload, indent=1, allow_nan=False))
    return path


def watched_codes() -> list[int]:
    """Every starred code, ascending. The one thing most callers want."""
    return sorted(load_watchlist())


def watch(code: int, *, note: str = "", known_codes=None) -> dict:
    """Star ``code``. Re-starring replaces the note and the timestamp.

    ``known_codes`` is the universe the star has to belong to, supplied by the
    caller so this module needs no data layer; omitting it skips the check,
    which is for tests and for callers that have already validated.

    The cap is checked only for a code that is not already starred, so a user
    at exactly the cap can still edit every note he has.
    """
    code = int(code)
    if known_codes is not None and code not in {int(c) for c in known_codes}:
        raise GafferError(
            f"player {code} is not in the current player list — star a code "
            f"the tool knows about")
    if len(str(note or "")) > NOTE_MAX:
        raise GafferError(f"note is longer than {NOTE_MAX} characters")
    rows = load_watchlist()
    if code not in rows and len(rows) >= MAX_WATCHED:
        raise GafferError(
            f"{MAX_WATCHED} starred players is the cap — unstar one first")
    row = {"note": str(note or ""),
           "set_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    rows[code] = row
    save_watchlist(rows)
    return row


def unwatch(code: int) -> bool:
    """Remove one star. ``False`` when there was nothing to remove."""
    rows = load_watchlist()
    if int(code) not in rows:
        return False
    rows.pop(int(code))
    save_watchlist(rows)
    return True


def watch_targets() -> dict[int, str]:
    """``{code: source}`` over squad, plan and watchlist, in that order.

    Everyone the manager is watching, explicit and implicit. The stars are
    this module's own store; the squad and the plan are read off the newest
    banked solve state and advice payload, which is why the imports are local
    — a module the CLI touches to print ``--help`` should not pull in the
    artifact layer, and neither should the store's own tests.

    A resolution order rather than a set union, so every row can say *why* it
    is there. A starred player who is also in the squad reads as ``squad``:
    the strongest reason is the true one, and "you own him" is a better answer
    to "why am I being told about this?" than "you bookmarked him".

    Never raises, and every read degrades on its own. A clone that has never
    solved has no squad and no plan and still has its stars; a clone with a
    solve state but no advice file has a squad and no plan. Two callers share
    it — the movers endpoint and the Friday digest — and two copies of this
    would be two different answers to "who am I watching?".
    """
    from gaffer.artifacts import latest_gw, load_advice, load_solve_state

    out: dict[int, str] = {}
    gw = None
    try:
        gw = latest_gw()
    except Exception as exc:  # noqa: BLE001 — a watch set is never fatal
        print(f"watch set: no advice on disk ({exc})")
    if gw is not None:
        try:
            for code in load_solve_state(int(gw)).owned_codes:
                out.setdefault(int(code), "squad")
        except Exception as exc:  # noqa: BLE001
            print(f"watch set: no solve state for GW{gw} ({exc})")
        try:
            advice = load_advice(int(gw))
            for key in ("buys", "sells"):
                for player in advice.get(key) or []:
                    code = (player or {}).get("code")
                    if code is not None:
                        out.setdefault(int(code), "plan")
        except Exception as exc:  # noqa: BLE001
            print(f"watch set: no advice payload for GW{gw} ({exc})")
    for code in watched_codes():
        out.setdefault(int(code), "watchlist")
    return out
