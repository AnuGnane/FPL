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
"manual" badge, so a user who has corrected a corner taker can see that his
correction took.

Nothing here raises. A missing file, a malformed file and a file naming a club
that does not exist are all "no override", because a hand-edited file is
exactly the kind of thing that is half-edited at 11pm on a Friday.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

OVERRIDE_PATH = Path("data/set_pieces.toml")
"""Relative on purpose: read at call time against the working directory, the
way ``store.DATA_DIR`` is, so a test that redirects the data directory
redirects this too."""

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

    which is turned into ``{118748: 1, 232413: 2}`` — the same 1-based
    ``*_order`` shape the bootstrap uses, so a reader can substitute one for
    the other without learning a second convention.

    An empty list is a *statement* and is kept: it is how a user says "the
    published taker has left and nobody has replaced him". An unknown kind, a
    non-integer entry and a repeated code are each dropped with a printed
    line, because a silent drop in a file somebody typed by hand is a
    correction that never took and never said so.
    """
    target = Path(path) if path is not None else OVERRIDE_PATH
    if not target.is_file():
        return {}
    try:
        raw = tomllib.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
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

    Flattened across clubs because a player code is globally unique and the EP
    term never asks which club a code belongs to. A code named by two clubs —
    a mid-window transfer typed into both — keeps the first, and the file is
    small enough that a user can see which.
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
