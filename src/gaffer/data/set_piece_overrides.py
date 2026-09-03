"""Who really takes them: the hand-edited override over FPL's own orders.

FPL's bootstrap publishes ``penalties_order``, ``direct_freekicks_order`` and
``corners_and_indirect_freekicks_order``, and it is often days behind the
manager's press conference and occasionally simply wrong. This is the one
place a user can say so, and the only knowledge in this project that comes
from watching football rather than from a feed.

**TOML rather than the spec's YAML.** ``pyproject.toml`` ships no YAML parser
and ``data/manager_tenures.toml`` is the existing precedent for a hand-edited
override here. ``tomllib`` is stdlib; a dependency for one file is a cost with
no buyer.

**The file is untracked and the example is a package asset.** ``data/`` is
never staged, so the template lives in ``gaffer.assets`` where a fresh clone
and an installed wheel both carry it.

**Only penalties reach expected points.** Free kicks and corners are surfaced
in the UI as context and get no EP term — ``set_pieces.py``'s scope note says
why, and this module does not widen it. What the other two kinds buy is the
order the players endpoint *serves* and the "manual" badge beside it, so a
user who has corrected a corner taker can see that his correction took. No
number downstream of the screen moves.

Two read paths, and only two: ``set_pieces.pen_table`` (the penalties term in
expected points) and ``web.routers.players.set_piece_orders`` (the served
orders and the badge, all three kinds). Notably **not**
``pen_tracker.save_tracker_guarded``, which records what FPL published and
must keep doing so, nor the ``pen_taker`` feature in ``features/engineer.py``,
which is a training column built from history.

**The club header is decorative.** It is never matched against a club name;
the codes under it are the key, and each man's club is resolved from the frame
being served. A code filed under the club he left last summer therefore still
applies, and a header spelled wrongly costs the reader his bearings and
nothing else. What the header *must* be is valid TOML — quoted where the name
has a space or an apostrophe — because one bad header discards the whole file.

Nothing here raises. A missing file, a malformed file and a file naming a club
that does not exist are all "no override", because a hand-edited file is
exactly the kind of thing that is half-edited at 11pm on a Friday.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from gaffer.data import store

OVERRIDE_NAME = "set_pieces.toml"


def override_path() -> Path:
    """``store.DATA_DIR / "set_pieces.toml"``, resolved at call time.

    A function rather than a constant, and ``store.DATA_DIR`` rather than a
    literal ``"data"``: every other reader in this package goes through that
    attribute, so the monkeypatch idiom the suite already uses
    (``monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")``) redirects
    this file too. A module-level constant would have been bound at import and
    would have kept pointing at the real ``data/`` no matter what a test did.
    """
    return store.DATA_DIR / OVERRIDE_NAME

SET_PIECE_KINDS = ("penalties", "direct_free_kicks", "corners")
"""The three tables the file may carry, in the order the UI shows them.

The names are the *user's* vocabulary rather than FPL's column names
(``corners_and_indirect_freekicks_order``): this file is typed by a person,
and a person should not have to spell "indirect" to name a corner."""


def load_set_piece_overrides(path: Path | str | None = None
                             ) -> dict[str, dict[str, dict[int, int]]]:
    """``{club: {kind: {code: 1-based order}}}``, or ``{}``.

    The file lists takers **in order**::

        [Arsenal]
        penalties = [118748, 232413]   # Saka, then Eze

    which is turned into ``{223340: 1, 232413: 2}`` — the same 1-based
    ``*_order`` shape the bootstrap uses, so a reader can substitute one for
    the other without learning a second convention.

    **The club header is decorative; the codes are the key.** Nothing here or
    downstream matches the header against a club name. A player's club is read
    off the frame being priced, from the ``team_code`` of the codes the file
    names — so a code filed under a club he left last summer still applies,
    and a header spelled wrongly costs nothing but the reader's bearings. Two
    clubs' codes under one header are two queues.

    **Listing a queue demotes the men it leaves out.** For the club a listed
    code plays for, the file's list *is* the queue: a teammate it does not
    name is not a taker, whatever FPL published. That is what makes the line a
    user actually types — one new name — mean what he meant by it.

    **An empty list demotes nobody.** It names no code, so it identifies no
    club, so there is nothing for it to be the queue *of*: it records that you
    checked and found nobody. To demote a taker, list the club's replacement
    queue.

    A club header containing a space or an apostrophe must be quoted —
    ``["Man City"]``, ``["Nott'm Forest"]`` — because bare TOML keys allow
    neither, and one bad header discards the whole file rather than one table.
    An unknown kind, a non-integer entry and a repeated code are each dropped
    with a printed line, because a silent drop in a file somebody typed by
    hand is a correction that never took and never said so.
    """
    target = Path(path) if path is not None else override_path()
    if not target.is_file():
        return {}
    try:
        raw = tomllib.loads(target.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        # The position, spelled out, because TOML fails the *whole file* on
        # one bad line: a user whose Arsenal table is perfect still loses it
        # to a `[Man City]` three lines down, and "could not be read" would
        # leave him hunting. `exc` already names the line and column.
        print(f"set pieces: {target} is not valid TOML ({exc}) — the whole "
              f"file is discarded, so no overrides at all. A club header "
              f"with a space or an apostrophe has to be quoted: "
              f'["Man City"], ["Nott\'m Forest"].')
        return {}
    except (OSError, UnicodeDecodeError) as exc:
        print(f"set pieces: {target} could not be read ({exc}) — no overrides")
        return {}
    out: dict[str, dict[str, dict[int, int]]] = {}
    for club, tables in raw.items():
        if not isinstance(tables, dict):
            print(f"set pieces: {club!r} is not a club table — ignored")
            continue
        club_out: dict[str, dict[int, int]] = {k: {} for k in SET_PIECE_KINDS}
        for kind, takers in tables.items():
            if kind not in SET_PIECE_KINDS:
                print(f"set pieces: {club} names an unknown set piece "
                      f"{kind!r} — ignored (known: "
                      f"{', '.join(SET_PIECE_KINDS)})")
                continue
            if not isinstance(takers, list):
                print(f"set pieces: {club}.{kind} is not a list of player "
                      f"codes — ignored")
                continue
            order: dict[int, int] = {}
            for entry in takers:
                if not isinstance(entry, int) or isinstance(entry, bool):
                    print(f"set pieces: {club}.{kind} entry {entry!r} is not "
                          f"a player code — dropped")
                    continue
                if entry in order:
                    print(f"set pieces: {club}.{kind} names {entry} twice — "
                          f"keeping position {order[entry]}")
                    continue
                order[int(entry)] = len(order) + 1
            club_out[kind] = order
        out[str(club)] = club_out
    return out


def penalty_order_overrides(path: Path | str | None = None
                            ) -> dict[int, int]:
    """``{code: penalty order}`` across every club, for the EP term.

    Flattened across clubs because a player code is globally unique and the
    header is decorative anyway: ``pen_table`` resolves each man's club from
    the frame it is pricing, not from the table he was typed under, and it is
    that resolved club whose queue the file replaces. A code named by two
    clubs — a mid-window transfer typed into both — keeps the first, and the
    file is small enough that a user can see which.

    The ranks here are only half the answer. The other half is the demotion
    ``pen_table`` applies with them: a teammate of a listed code who is not
    himself listed loses his bootstrap order. That is not done here because
    this map has no way to know who a teammate is.
    """
    out: dict[int, int] = {}
    for club, tables in load_set_piece_overrides(path).items():
        for code, order in tables.get("penalties", {}).items():
            if code in out:
                print(f"set pieces: code {code} is named by more than one "
                      f"club ({club} is the later) — keeping the first")
                continue
            out[int(code)] = int(order)
    return out
