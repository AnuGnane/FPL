"""Where the captain stands against the top 10k, joined onto an advice payload.

The fourth serve-time decoration, and it exists here for the reason
``web/identity.py`` exists here: ``gaffer.advise`` writes the payload and is a
protected file, so a field the pitch needs and the solve did not produce is
resolved on the way out. Every advice file already on disk gains the framing
without a re-solve, and the artifact's bytes never change.

**One key, ``captain_field``, and it is absent rather than null when there is
nothing to say.** A null on every payload on every clone that never ran a
scrape would make "the page is byte-identical without a field log" an assertion
with an exception in it, and an assertion with an exception in it is the one
that gets loosened next year.

**Nothing here raises**, exactly as in ``identity``: the worst case is the
payload handed back as it arrived.

**The id-space split is the hazard.** The payload speaks ``code``; the EO log
speaks ``element``, and ``data/field.py:49-52`` says why — *"a pick names a
season-scoped element"*. Three guards follow, and they are three different
failures, not three spellings of one:

1. the map is built from ``code`` and ``element`` **on the same snapshot row**
   (``league_sim.py:227``'s shape), so there is no positional fallback that
   could hand back a neighbour's number;
2. a code with no row, or an element the log does not carry, produces no
   framing — never ``0.0``, which ``schemas.py:411`` says a reader takes for a
   measured differential;
3. the log is read **for the current season** (``field.latest_field_eo``'s
   ``season`` keyword), because element ids are re-issued every August and the
   same integer is a different footballer on the other side of a rollover.

``league_sim._elements_by_code`` builds the same map and is deliberately not
imported: it is module-private to the router that models rival squads, and it
re-reads the snapshot on every call where this needs the mtime-keyed memo
``identity`` already owns. Two maps in one tree is a recorded residual, not an
oversight (plan A3).
"""

from __future__ import annotations

from typing import Any

from gaffer.data import store
from gaffer.data.field import latest_field_eo
from gaffer.web import identity
from gaffer.web.routers.players import field_class

NEW_KEYS = ("captain_field",)
"""What this module adds, and the complete list of it. Absent — not null —
whenever there is nothing to say."""

_ELEMENTS_SLOT = "live/players.parquet:code_element"
"""A memo slot of its own.

``identity._player_teams`` caches ``{code: team_code}`` under the bare
relative path, so reusing that string here would have the two maps evict and
answer for each other. Same file, same key, different slot — which is the
shape ``identity`` already uses for its per-gameweek fixture map."""

_BY_ELEMENT_SLOT = "live/players.parquet:element_player"
_EVENTS_SLOT = "live/events.parquet:most_captained"


def clear_cache() -> None:
    """Drop every memoised map, including identity's.

    Delegation rather than a second cache: one memo, one lock, one eviction
    policy, and a test that clears one clears both instead of learning two
    names for one thing.
    """
    identity.clear_cache()


def _elements_by_code() -> dict[int, int]:
    """``{player_code: element}``, or an empty map.

    Both ids come off the **same snapshot row** — guard 1. A missing
    ``element`` column is the older-bootstrap case and produces an empty map
    and a printed line, never a ``KeyError`` on the way out of a page.
    """
    def build() -> Any:
        try:
            players = store.load("live/players.parquet")
            if "element" not in players.columns:
                raise KeyError("players snapshot has no element column")
            pairs = players[["code", "element"]].dropna()
            return {int(c): int(e)
                    for c, e in zip(pairs["code"], pairs["element"])}
        except Exception as exc:  # noqa: BLE001 — a decoration is never fatal
            print(f"field_frame: player snapshot unreadable ({exc})")
            return identity._FAILED

    value = identity._memo(_ELEMENTS_SLOT,
                           identity._file_key("live/players.parquet"), build)
    return {} if value is identity._FAILED else value


def _players_by_element() -> dict[int, dict]:
    """``{element: {"code", "name"}}``, or an empty map.

    The other direction of the same one-row join, for §F1b: the bootstrap says
    which *element* the field is captaining and the page needs a code and a
    name. Same row, same guards, and a missing ``name`` column is a ``None``
    rather than a ``KeyError``.
    """
    def build() -> Any:
        try:
            players = store.load("live/players.parquet")
            if "element" not in players.columns:
                raise KeyError("players snapshot has no element column")
            named = "name" in players.columns
            pairs = players[["code", "element"]].dropna()
            names = players["name"] if named else None
            out: dict[int, dict] = {}
            for i, (c, e) in enumerate(zip(pairs["code"], pairs["element"])):
                out[int(e)] = {"code": int(c),
                               "name": (str(names.iloc[i]) if named else None)}
            return out
        except Exception as exc:  # noqa: BLE001 — a decoration is never fatal
            print(f"field_frame: player snapshot unreadable ({exc})")
            return identity._FAILED

    value = identity._memo(_BY_ELEMENT_SLOT,
                           identity._file_key("live/players.parquet"), build)
    return {} if value is identity._FAILED else value


def _modal_captain(gw: int) -> dict | None:
    """``{"code", "name", "gw"}`` for the gameweek's most-captained player.

    Plan A5: FPL publishes this **live** for the gameweek that is open and
    ``null`` for every gameweek after it, so it is joined on the advice
    gameweek and a miss is an absence. Last week's modal captain is not this
    week's, and printing it as if it were is the failure this join avoids.

    The column guard comes before the row access (``pen_tracker.py:42-52``): a
    parquet banked before this cycle has no such column and must read as
    absent rather than raise.
    """
    def build() -> Any:
        try:
            events = store.load("live/events.parquet")
            if "most_captained" not in events.columns:
                return {}
            pairs = events[["gw", "most_captained"]].dropna()
            return {int(g): int(e)
                    for g, e in zip(pairs["gw"], pairs["most_captained"])}
        except Exception as exc:  # noqa: BLE001
            print(f"field_frame: events snapshot unreadable ({exc})")
            return identity._FAILED

    value = identity._memo(_EVENTS_SLOT,
                           identity._file_key("live/events.parquet"), build)
    element = ({} if value is identity._FAILED else value).get(int(gw))
    if element is None:
        return None
    who = _players_by_element().get(int(element))
    if who is None:
        return None
    return {"code": who["code"], "name": who["name"], "gw": int(gw)}


def _field_table(gw: int) -> dict[int, dict]:
    """``{element: {"eo", "se", "n", "gw"}}`` for this season, or an empty map.

    The config read is *inside* the guard, and its failure falls back to the
    packaged default rather than to no season at all. ``load_config`` raises on
    a clone with no ``config.toml``, and dropping the ``season`` keyword there
    would quietly re-open guard 3 on exactly the machines least likely to
    notice. ``Config().current_season`` is a named season with the same
    meaning; what it cannot do is follow a user who set a different one.

    The default is read off the dataclass field rather than by constructing a
    ``Config``, which cannot be built without ``entry_id`` and ``league_id``.
    Deliberately *not* "the newest season in the log": that would frame from
    last season's rows on a clone whose log has not rolled over, which is the
    failure guard 3 exists to prevent.
    """
    try:
        from gaffer.config import Config, load_config

        try:
            season = load_config().current_season
        except Exception:  # noqa: BLE001 — an unconfigured clone still frames
            season = Config.__dataclass_fields__["current_season"].default
        return latest_field_eo(gw, season=season)
    except Exception as exc:  # noqa: BLE001
        print(f"field_frame: field EO log unreadable ({exc})")
        return {}


def captain_note(name: str, eo: float, se: float | None,
                 klass: str | None) -> str:
    """The sentence, worded in exactly one place.

    One decimal on the EO, because ``se`` is around two points at n=300 and a
    second decimal is a digit the sample does not have — the argument
    ``ThisWeek.tsx:231-235`` already makes about the captain-odds chip.

    ``None`` for the class is not a missing answer, it is the answer: the
    classifier says nothing between 15% and 40% (``routers/players.py:105``),
    and the honest reading of the middle is "neither, particularly" rather
    than a coin flip between cover and attack.
    """
    share = f"{eo:.1f}%" + (f" ± {se:.1f}" if se is not None else "")
    head = f"The top 10k have {share} of {name}"
    if klass == "shield":
        return f"{head} — he is cover, not attack."
    if klass == "sword":
        return f"{head} — he is attack, not cover."
    return f"{head} — neither cover nor attack, particularly."


def modal_note(modal: dict) -> str:
    """The §F1b sentence, for the weeks the tier sample cannot cover.

    Names the gameweek, because the claim is about *that* week and a sentence
    that did not name it would be read as standing. Carries no percentage: the
    bootstrap says who, not how many, and inventing a share here is the one
    thing this fallback must not do.
    """
    who = modal.get("name") or f"element {modal['code']}"
    return f"The top 10k are captaining {who} in GW{modal['gw']}."


def with_field_frame(payload: dict, gw: int) -> dict:
    """``payload`` plus ``captain_field``, or ``payload`` exactly as it came.

    ``gw`` comes from the caller rather than off the payload, for
    ``identity``'s reason: the route already knows which gameweek it is
    serving and a payload that disagreed with it would be the bug, not the
    source of truth.
    """
    try:
        captain = payload.get("captain")
        if not isinstance(captain, dict):
            return payload
        code = captain.get("code")
        if not isinstance(code, (int, float)) or isinstance(code, bool):
            return payload
        element = _elements_by_code().get(int(code))
        if element is None:
            return payload
        row = _field_table(gw).get(element)
        modal = _modal_captain(gw)
        if row is None and modal is None:
            return payload
        # The key is emitted with a null ``eo`` when only the bootstrap had
        # something to say. That is not an exception to Task 2's absent-not-
        # null rule: the rule is that the key is absent when there is *nothing*
        # to say, and "the field is captaining Salah this week" is something.
        if row is None:
            frame: dict[str, Any] = {
                "code": int(code), "eo": None, "se": None, "n": None,
                "gw": int(gw), "field_class": None, "note": modal_note(modal)}
        else:
            eo = float(row["eo"])
            klass = field_class(True, eo)
            se = float(row["se"]) if row.get("se") is not None else None
            frame = {
                "code": int(code), "eo": eo, "se": se,
                "n": int(row["n"]) if row.get("n") is not None else None,
                "gw": int(row.get("gw", gw)), "field_class": klass,
                "note": captain_note(str(captain.get("name", "your captain")),
                                     eo, se, klass)}
        # Only in the note when the EO is absent: when both are present the
        # measured share is the stronger statement and a second clause beside
        # it is noise.
        if modal is not None:
            frame["most_captained"] = modal
        return {**payload, "captain_field": frame}
    except Exception as exc:  # noqa: BLE001 — a decoration never 500s a page
        print(f"field_frame: framing skipped ({exc})")
        return payload
