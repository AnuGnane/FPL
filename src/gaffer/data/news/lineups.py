"""Predicted line-ups — one source, one module, so swapping it is one diff.

Fantasy Football Scout publish a predicted XI, bench and unavailable list per
fixture the day before a deadline. That is a *gate*, not a signal: a predicted
starter is not more likely to play than the model already thinks, but a
predicted omission is strong evidence against, and the difference between
"benched" and "starting" is the difference between two points and eight.

Only ever the **next** fixture. A predicted line-up says nothing about GW+2,
and :func:`gaffer.data.news.normalize.availability_frame` plus
:func:`gaffer.models.availability.apply_availability` enforce that between them
by applying the hint to the horizon's first gameweek alone (spec §4 rule 3).
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx
import pandas as pd

from gaffer.config import lineup_providers, serving_config
from gaffer.data.news import NEWS_CACHE, cache_path, cached_text, fetched_at
from gaffer.data.news.normalize import (NEWS_MIN_COVERAGE, club_code,
                                        club_code_map, match_codes)

FFS_URL = "https://www.fantasyfootballscout.co.uk/team-news/"

P_START_HINT = {"start": 1.0, "doubt": 0.25, "out": 0.0}
"""Slot -> the ceiling this source puts on ``p_play`` for the first gameweek.

``0.25`` for a listed doubt rather than ``0`` because a 75%-rated doubt does
often play, and often from the bench. It is a *ceiling*, never a floor: a
fringe player the model already prices at 0.1 is left exactly where he is, and
the 1.0 a predicted starter earns is a no-op by construction.

Only the three explicit statuses the page prints get a hint. A player who is
merely absent from the predicted XI gets **no row**: the pitch is one
journalist's guess at eleven names, and reading the other fourteen as benched
would bench half a squad on nobody's say-so.
"""

LINEUP_COLS = ["code", "p_start_hint", "absence_damp", "source", "fetched_at"]
PARSE_COLS = ["name", "club", "slot", "code"]

ABSENCE_MIN_START_SHARE = 0.6
"""Share of his club's most-started player's starts, above which a player's
omission from a predicted XI is *news*.

Read as "he has started at least 60% as often as the club's most reliable
starter". The bootstrap carries season starts and no fixture count, so the
club's own maximum is the denominator that needs neither: it is the number of
matches a nailed-on starter has played. Below the threshold the omission is
one journalist declining to pick a squad player, which is not evidence about
anything.
"""

XI_SIZE = 11
"""Resolved predicted starters a club needs before its omissions are read.

An XI is eleven names. Fewer than that is a parse that fell short, and the
players it failed to reach are indistinguishable from the players the
journalist left out — so nothing at that club is news.
"""

ABSENCE_SLOTS = {"out": "out", "banned": "out", "suspended": "out",
                 "doubts": "doubt", "doubt": "doubt"}
"""The page's own labels -> our slots. A ban and an injury are both a zero
here; the *reason* is the injury feed's job, and this source only ever says
whether he is in the team."""

# One club per <h2>, its section running to the next heading. The page nests
# the heading inside a header/div/li tangle that has been rewritten twice this
# season; the heading itself has not moved.
_SECTION = re.compile(r"<h2[^>]*>(.*?)</h2>(.*?)(?=<h2[^>]*>|\Z)", re.S | re.I)
# The pitch: one <ul class="row-N"> per line of the formation.
_PITCH_LIST = re.compile(r'<ul class="row-\d+"[^>]*>(.*?)</ul>', re.S | re.I)
# "Out:" / "Doubts:" / "Banned:" and the <ul class="players"> that may follow
# it — the label is printed even when the list behind it is empty.
_ABSENCE_LIST = re.compile(
    r"<strong>\s*(Out|Doubts?|Banned|Suspended)\s*:?\s*</strong>\s*"
    r'(?:<ul class="players"[^>]*>(.*?)</ul>)?', re.S | re.I)
_ITEM = re.compile(r"(<li[^>]*>.*?</li>)", re.S | re.I)
"""Whole element, attributes included — the pitch keeps the player's name in
the ``title`` attribute rather than in the body."""
_TITLE = re.compile(r'title="([^"]*)"', re.I)
_PHOTO = re.compile(r"/photos/players/\d+x\d+/(\d+)\.png", re.I)
_SURNAME_FIRST = re.compile(r"^(.*?)\s*\(([^)]*)\)\s*$")
_PERCENT = re.compile(r"\d+\s*%")
_TAG = re.compile(r"<[^>]+>")


def _text(markup: str) -> str:
    """Tags out, entities in, whitespace collapsed.

    A scraped page is HTML on both axes: the club heading spells an ampersand
    ``&amp;``, which misses the alias table by a word nobody wrote, and a name
    carries ``&#039;`` where the bootstrap has an apostrophe.
    """
    return " ".join(html.unescape(_TAG.sub(" ", markup or "")).split())


def _pitch_name(title: str) -> str:
    """``"Raya Martin (David)"`` -> ``"David Raya Martin"``.

    The site prints the surname first with the forename in brackets. Put back
    in reading order it is the bootstrap's own full name, and the token sweeps
    in :func:`~gaffer.data.news.normalize.match_codes` do the rest. Only ever
    a fallback: an entry whose photo code is known never reaches a name.
    """
    m = _SURNAME_FIRST.match(title)
    if not m:
        return title
    return f"{m.group(2)} {m.group(1)}".strip()


def parse_lineups(markup: str) -> pd.DataFrame:
    """The predicted line-ups page -> ``[name, club, slot, code]``.

    ``code`` is the FPL player code lifted straight out of the photo URL of a
    predicted-XI entry, and ``NA`` for everyone on an absence list (those
    carry no photo). Same shallow-regex posture as the injury table, and the
    same failure mode: a redesign yields zero rows, which is the
    official-flags path.
    """
    rows = []
    for heading, block in _SECTION.findall(markup or ""):
        club = _text(heading)
        if not club:
            continue
        for body in _PITCH_LIST.findall(block):
            for item in _ITEM.findall(body):
                title = _TITLE.search(item)
                name = (_pitch_name(html.unescape(title.group(1)))
                        if title else _text(item))
                photo = _PHOTO.search(item)
                if not name and not photo:
                    continue
                rows.append({"name": name, "club": club, "slot": "start",
                             "code": int(photo.group(1)) if photo else None})
        for label, body in _ABSENCE_LIST.findall(block):
            slot = ABSENCE_SLOTS.get(label.strip().casefold())
            if slot is None or not body:
                continue
            for item in _ITEM.findall(body):
                # A doubt prints its percentage inside the same <li>; the
                # number is the injury feed's business, not a part of a name.
                name = _PERCENT.sub("", _text(item)).strip()
                if name:
                    rows.append({"name": name, "club": club, "slot": slot,
                                 "code": None})
    out = pd.DataFrame(rows, columns=PARSE_COLS)
    out["code"] = pd.to_numeric(out["code"], errors="coerce").astype("Int64")
    return out


def notable_absences(players: pd.DataFrame, covered: set[int],
                     claimed: set[int], damp: float,
                     min_share: float = ABSENCE_MIN_START_SHARE
                     ) -> pd.DataFrame:
    """Regulars a parsed XI silently left out, as ``[code, absence_damp]``.

    Four conditions, all necessary (spec §4). His club must have a parsed XI
    — no team sheet is not the same as a team sheet without him. He must not
    already be *named* by the page, in the XI or on any absence list, because
    that row is the sharper claim and damping it twice would double-count one
    source. He must not already be *flagged* by the official feed, for the
    same reason and a sharper one: ``apply_availability`` has already docked
    an ``i`` or a ``d``, and the predicted XI leaves him out *because* of that
    flag, so a second charge is not a second source. Only ``status = 'a'``
    with no chance percentage — the fit player nobody has docked — is
    eligible. And he must be a regular by :data:`ABSENCE_MIN_START_SHARE`,
    since half of every squad is out of every predicted XI and only a player
    the manager has been picking says something by being missing.

    A ``players`` frame carrying neither column is the pre-bootstrap caller
    and every row stays eligible: the flag filter can only ever remove rows,
    and its absence is the shipped behaviour.

    The result is a *damp*, not a ceiling: an omission is weaker evidence than
    a printed "Out", and multiplying is how the model's own view survives it.
    """
    cols = ["code", "absence_damp"]
    if not covered or "starts" not in players.columns:
        return pd.DataFrame(columns=cols)
    keep = ["code", "team_code", "starts"]
    keep += [c for c in ("status", "chance_of_playing")
             if c in players.columns]
    frame = players[keep].copy()
    frame["code"] = pd.to_numeric(frame["code"], errors="coerce")
    frame["team_code"] = pd.to_numeric(frame["team_code"], errors="coerce")
    frame["starts"] = pd.to_numeric(frame["starts"],
                                    errors="coerce").fillna(0.0)
    frame = frame[frame["team_code"].isin(covered)]
    if frame.empty:
        return pd.DataFrame(columns=cols)
    # The denominator is the club's most-started player, named or not: taking
    # it after the named codes are dropped would make the *least* regular
    # survivor his own benchmark and hand him a share of 1.0.
    best = frame.groupby("team_code")["starts"].transform("max")
    unflagged = pd.Series(True, index=frame.index)
    if "status" in frame.columns:
        status = frame["status"].astype("object")
        unflagged &= status.isna() | status.astype(str).str.strip().eq("a")
    if "chance_of_playing" in frame.columns:
        chance = pd.to_numeric(frame["chance_of_playing"], errors="coerce")
        unflagged &= chance.isna() | (chance >= 100)
    frame = frame[~frame["code"].isin(claimed) & unflagged]
    best = best.loc[frame.index]
    if frame.empty:
        return pd.DataFrame(columns=cols)
    share = frame["starts"] / best.where(best > 0)
    out = frame[share >= min_share].copy()
    if out.empty:
        return pd.DataFrame(columns=cols)
    out["absence_damp"] = float(damp)
    out["code"] = out["code"].astype("int64")
    return out[cols].sort_values("code").reset_index(drop=True)


ROTOWIRE_URL = "https://www.rotowire.com/soccer/lineups.php"

# One fixture per <div class="lineup__box">; each carries two <ul
# class="lineup__list is-home|is-visit"> team sheets and, above them, two
# <div class="lineup__mteam …"> club names in the same order. Verified against
# a live fetch on 2026-09-01 (plan A5): 200, 462KB, ten fixtures, the classes
# below on every one of them.
_RW_BOX = re.compile(
    r'<div class="lineup__box".*?(?=<div class="lineup__box"|\Z)', re.S | re.I)
_RW_MTEAM = re.compile(
    r'<div class="lineup__mteam is-(home|visit)"[^>]*>(.*?)<', re.S | re.I)
_RW_LIST = re.compile(
    r'<ul class="lineup__list is-(home|visit)"[^>]*>(.*?)</ul>', re.S | re.I)
_RW_TITLE = re.compile(
    r'<li class="lineup__title[^"]*">\s*Injuries\s*</li>', re.I)
_RW_PLAYER = re.compile(r'<li class="lineup__player">(.*?)</li>', re.S | re.I)
_RW_INJ = re.compile(r'<span class="lineup__inj">\s*([A-Za-z]+)\s*</span>',
                     re.I)

ROTOWIRE_TAGS = {"out": "out", "sus": "out", "ques": "doubt"}
"""RotoWire's own availability tags -> our slots.

Deliberately a second table rather than a reuse of :data:`ABSENCE_SLOTS`:
that one maps the *words* Fantasy Football Scout prints ("Doubts", "Banned")
and this one maps three uppercase codes. One table serving two vocabularies is
how a site rename becomes a silent mis-slot.
"""


def parse_rotowire(markup: str) -> pd.DataFrame:
    """RotoWire's line-ups page -> ``[name, club, slot, code]`` (v10 §F2a).

    Schema-identical to :func:`parse_lineups`, ``code`` an all-``NA`` ``Int64``
    column: this source carries no FPL photo codes, so every row goes through
    :func:`~gaffer.data.news.normalize.match_codes` and is subject to
    ``NEWS_MIN_COVERAGE``. That is the correct posture for a source that cannot
    self-identify, and it is why :class:`Provider` marks it not absence-capable
    (plan A7).

    Two structural facts do all the work. A fixture's two club headings and its
    two team sheets are each labelled ``is-home``/``is-visit``, so they pair by
    label rather than by order — a page that printed the visitors first would
    otherwise swap two squads. And a team sheet runs XI-first until an
    ``Injuries`` title, after which the same ``lineup__player`` markup means
    the opposite thing; a parser that read the whole ``<ul>`` as an XI would
    put an injured player in the team.

    Names come from the ``title`` attribute, which is the full name, rather
    than the anchor's abbreviated body text. ``_pitch_name`` is deliberately
    *not* applied — RotoWire prints forename-first already, and reversing a
    name that is already in reading order is how "Danny Welbeck" becomes
    "Welbeck Danny" and misses the matcher entirely.

    Same failure mode as every parser here: a redesign yields zero rows, which
    is the official-flags path.
    """
    rows = []
    for box in _RW_BOX.findall(markup or ""):
        clubs = {side: _text(name) for side, name in _RW_MTEAM.findall(box)}
        for side, body in _RW_LIST.findall(box):
            club = clubs.get(side)
            if not club:
                continue
            halves = _RW_TITLE.split(body, maxsplit=1)
            xi_part = halves[0]
            hurt_part = halves[1] if len(halves) > 1 else ""
            for item in _RW_PLAYER.findall(xi_part):
                name = _rw_name(item)
                if name:
                    rows.append({"name": name, "club": club,
                                 "slot": "start", "code": None})
            for item in _RW_PLAYER.findall(hurt_part):
                tag = _RW_INJ.search(item)
                slot = (ROTOWIRE_TAGS.get(tag.group(1).strip().casefold())
                        if tag else None)
                name = _rw_name(item)
                if slot and name:
                    rows.append({"name": name, "club": club, "slot": slot,
                                 "code": None})
    out = pd.DataFrame(rows, columns=PARSE_COLS)
    # A player can appear twice — on the pitch carrying a QUES tag, and again
    # under Injuries — and the pessimistic row is the one that matters. It is
    # resolved *here*, while the name is still the key, and not left to
    # ``fetch_lineups``' dedupe: ``match_codes`` claims a code once and drops
    # every later row that answers to it, so by then the XI row (emitted
    # first) would have won and the doubt would be gone. FFS never meets this
    # because its XI resolves by photo code on a separate path.
    if not out.empty:
        out = (out.assign(_rank=out["slot"].map(P_START_HINT))
               .sort_values("_rank", kind="stable")
               .groupby(["club", "name"], as_index=False, sort=False).head(1)
               .drop(columns="_rank")
               .sort_index()
               .reset_index(drop=True))
    out["code"] = pd.to_numeric(out["code"], errors="coerce").astype("Int64")
    return out[PARSE_COLS]


def _rw_name(item: str) -> str:
    """The player's full name out of one ``lineup__player`` element."""
    title = _TITLE.search(item)
    if title:
        return html.unescape(title.group(1)).strip()
    return _text(item)


@dataclass(frozen=True)
class Provider:
    """One predicted-XI source: where it lives, how it parses, what it may do.

    ``absence_capable`` is not a capability flag in the usual sense — every
    parser could in principle feed :func:`notable_absences`. It is a statement
    about *identification*. The absence rule's whole safety comes from
    :data:`XI_SIZE`: it only fires for a club whose eleven all came back
    resolved, because "the parser could not reach him" and "the journalist
    left him out" are otherwise the same observation. FFS resolves its XI from
    photo URLs, so a resolved eleven really is eleven identified players.
    RotoWire has no codes and resolves by name, where one miss drops a club
    below the threshold and one *wrong* match damps the starter it displaced.
    So RotoWire supplies hints and nothing else in v10 (plan A7).
    """
    name: str
    url: str
    parse: Callable[[str], pd.DataFrame]
    absence_capable: bool


PROVIDERS: dict[str, Provider] = {
    "ffs": Provider("ffs", FFS_URL, parse_lineups, absence_capable=True),
    # v10 §F2a (specs/2026-09-01-gaffer-v10-minutes-design.md). Not
    # absence-capable: RotoWire prints no FPL codes, so its XI resolves by
    # name, and one wrong match would both put a player in a team sheet he is
    # not in and damp the starter he displaced (plan A7).
    "rotowire": Provider("rotowire", ROTOWIRE_URL, parse_rotowire,
                         absence_capable=False),
}
"""Name -> provider. Keys are ``config.DEFAULT_LINEUP_PROVIDERS``' names, which
is what makes ``[news] lineup_providers`` able to name one (v10 §F2a)."""


def _resolve(provider: Provider, markup: str, players: pd.DataFrame,
             teams: pd.DataFrame, min_coverage: float,
             now: datetime | None, absence: bool,
             absence_damp: float) -> pd.DataFrame:
    """One provider's markup -> its own ``LINEUP_COLS`` frame.

    Lifted verbatim out of ``fetch_lineups`` (v10 §F2a) so that a second
    provider is an addition rather than a rewrite. With one provider named,
    the merge above this is the identity and the frame is byte-for-byte the
    pre-v10 one.
    """
    parsed = provider.parse(markup)
    if parsed.empty:
        print(f"news: predicted line-ups ({provider.name}) parsed no rows — "
              f"official flags only")
        return pd.DataFrame(columns=LINEUP_COLS)

    # Two joins, and only the second one can be wrong. The photo URL carries
    # the FPL code itself, so a predicted-XI entry resolves without a name
    # ever being read; the absence lists are bare text and go through the
    # matcher, scoped to the club their heading names.
    # The heading is the guard against everything on the page that is not
    # team news. The same site furniture — a "Scout Picks" widget, an
    # editorial XI — is built from the identical pitch markup under a heading
    # like "Follow us on social", and its eleven photo codes would otherwise
    # join straight through as predicted starters. A section whose heading is
    # not a club we carry contributes nothing.
    clubs = club_code_map(teams)
    club_codes = parsed["club"].map(lambda c: club_code(clubs, c))
    parsed = parsed[club_codes.notna()].reset_index(drop=True)
    club_codes = club_codes[club_codes.notna()].reset_index(drop=True)
    if parsed.empty:
        print("news: predicted line-ups named no club we carry — "
              "official flags only")
        return pd.DataFrame(columns=LINEUP_COLS)

    team_of = dict(zip(pd.to_numeric(players["code"], errors="coerce"),
                       pd.to_numeric(players["team_code"], errors="coerce")))
    codes = pd.to_numeric(parsed["code"], errors="coerce")
    # A code join is only safe where it agrees with the heading: the photo
    # says who, the <h2> says where, and a row where those two disagree is
    # furniture rather than a line-up.
    joined = pd.Series([c in team_of and team_of[c] == t
                        for c, t in zip(codes, club_codes)],
                       index=parsed.index)
    direct = parsed[joined].copy()
    direct["code"] = codes[joined].astype(int)

    rest = parsed[~joined].drop(columns=["code"])
    if rest.empty:
        matched = rest.assign(code=pd.Series(dtype="int64"))
    else:
        # A player already claimed by his photo cannot also be claimed by
        # somebody else's name, so he leaves the pool the matcher searches.
        taken = set(direct["code"])
        pool = players[~pd.to_numeric(players["code"],
                                      errors="coerce").isin(taken)]
        # The coverage floor guards *this* pass alone. Discarding code-joined
        # XI rows because an absence list was renamed would throw away the
        # half of the page that cannot mis-resolve.
        matched = match_codes(rest, pool, teams, label="lineups",
                              min_coverage=min_coverage)

    frames = [f for f in (direct, matched) if not f.empty]
    if not frames:
        return pd.DataFrame(columns=LINEUP_COLS)
    out = pd.concat(frames, ignore_index=True)
    out["p_start_hint"] = out["slot"].map(P_START_HINT).astype("float64")
    out["source"] = "lineups"
    out["fetched_at"] = fetched_at(now)
    out["absence_damp"] = float("nan")
    # A player named in two blocks (listed as a doubt and on the bench) takes
    # the most pessimistic hint — the same rule availability_frame applies
    # between sources.
    out = (out.sort_values("p_start_hint")
           .groupby("code", as_index=False).head(1))
    # v10 §F2a (specs/2026-09-01-gaffer-v10-minutes-design.md): the absence
    # rule is per provider and only for providers that can identify their XI
    # outright. See :class:`Provider` and plan A7 — a name-matched eleven is
    # not a resolved eleven, and the rule cannot tell the two apart.
    if absence and provider.absence_capable:
        # The clubs whose *whole* XI came back resolved. An absence list on
        # its own is not a team sheet, and neither is half a pitch: a
        # redesign, a truncated fetch or a photo URL we failed to read leaves
        # a handful of names, and damping everyone missing from those would
        # dock real starters for a bug on our side. Counted on the resolved
        # rows rather than the parsed ones, because a name that never reached
        # a code is exactly the failure this guards.
        starters = out.loc[out["p_start_hint"] == 1.0, "code"]
        per_club = (starters.map(team_of).dropna().astype(int).value_counts())
        covered = set(per_club[per_club >= XI_SIZE].index)
        extra = notable_absences(players, covered, set(out["code"]),
                                 absence_damp)
        if not extra.empty:
            extra["p_start_hint"] = float("nan")
            extra["source"] = "lineups"
            extra["fetched_at"] = fetched_at(now)
            out = pd.concat([out, extra], ignore_index=True)
    return out[LINEUP_COLS].sort_values("code").reset_index(drop=True)


def fetch_lineups(players: pd.DataFrame, teams: pd.DataFrame,
                  cache_dir: Path = NEWS_CACHE, cache_hours: int = 6,
                  client: httpx.Client | None = None,
                  min_coverage: float = NEWS_MIN_COVERAGE,
                  now: datetime | None = None,
                  absence: bool | None = None,
                  absence_damp: float | None = None,
                  providers: list[str] | None = None) -> pd.DataFrame:
    """Predicted line-ups as ``[code, p_start_hint, absence_damp, …]``.

    ``absence``/``absence_damp`` default to the ``[news]`` config, read here
    rather than passed in: ``advise.py`` is protected and cannot learn to
    forward them. ``False`` reproduces the pre-v8a frame exactly, one extra
    all-null column aside.

    ``providers`` defaults to the ``[news] lineup_providers`` config, read here
    for the same reason. Each provider degrades on its own — ``None`` markup,
    an empty parse, a coverage miss, a parser that raises — and a provider that
    says nothing leaves the others exactly where they were, which is today's
    single-source behaviour by construction. ``[]`` fetches nothing at all.
    """
    cfg = serving_config()
    absence = cfg.news_lineup_absence if absence is None else bool(absence)
    absence_damp = (cfg.news_lineup_absence_damp if absence_damp is None
                    else float(absence_damp))
    names = lineup_providers() if providers is None else [
        str(n).strip().casefold() for n in providers]

    # v10 §F2a (specs/2026-09-01-gaffer-v10-minutes-design.md): one source was
    # one point of failure. Each provider fetches into its own cache file —
    # sharing one would serve one site's markup to the other's parser — and
    # contributes an independent frame; the merge below is the only place they
    # meet.
    frames: list[pd.DataFrame] = []
    for name in names:
        provider = PROVIDERS.get(name)
        if provider is None:
            print(f"news: unknown predicted-XI provider {name!r} — ignored")
            continue
        try:
            dest = cache_path(cache_dir, f"lineups-{provider.name}",
                              cache_hours, now)
            markup = cached_text(provider.url, dest, client)
            if not markup:
                continue
            frame = _resolve(provider, markup, players, teams, min_coverage,
                             now, absence, absence_damp)
        except Exception as exc:  # noqa: BLE001 — one source is not the layer
            print(f"news: lineups/{provider.name} failed ({exc}) — "
                  f"the other providers stand")
            continue
        if frame.empty:
            continue
        hints = int(frame["p_start_hint"].notna().sum())
        damps = int(frame["absence_damp"].notna().sum())
        print(f"news: lineups/{provider.name}: {hints} hints, {damps} damps")
        frames.append(frame)

    if not frames:
        return pd.DataFrame(columns=LINEUP_COLS)
    return _merge(frames)


def _merge(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Per-provider frames -> one ``LINEUP_COLS`` frame (v10 §F2a).

    With one frame this is the identity, which is what makes the pre-v10
    behaviour provable rather than argued.
    """
    # v10 §F2a (specs/2026-09-01-gaffer-v10-minutes-design.md): two sources,
    # merged by pessimism. Concatenating and re-applying the module's own
    # existing rule — lowest hint per code — *is* the agreement logic the spec
    # asks for: agreement leaves the value alone, disagreement resolves down,
    # and a silent provider contributes no rows and therefore no opinion.
    # A damp is dropped for any code some provider named a starter, which is
    # the ``claimed`` rule inside one provider, said across two: an omission
    # from one XI is not news when another team sheet has him in it.
    all_rows = pd.concat(frames, ignore_index=True)
    # NaN sorts last under pandas' default, so a real hint beats a damp-only
    # row for the same code — the behaviour the single-provider path already
    # relies on.
    out = (all_rows.sort_values("p_start_hint")
           .groupby("code", as_index=False).head(1).copy())
    damps = all_rows.groupby("code")["absence_damp"].min()
    out["absence_damp"] = out["code"].map(damps)
    started = set(all_rows.loc[all_rows["p_start_hint"] == 1.0, "code"])
    out.loc[out["code"].isin(started), "absence_damp"] = float("nan")
    merged = out[LINEUP_COLS].sort_values("code").reset_index(drop=True)
    if len(frames) > 1:
        hints = int(merged["p_start_hint"].notna().sum())
        kept = int(merged["absence_damp"].notna().sum())
        print(f"news: lineups merged {len(frames)} providers -> "
              f"{hints} hints, {kept} damps")
    return merged
