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
from datetime import datetime
from pathlib import Path

import httpx
import pandas as pd

from gaffer.config import serving_config
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

    Three conditions, all necessary (spec §4). His club must have a parsed XI
    — no team sheet is not the same as a team sheet without him. He must not
    already be *named* by the page, in the XI or on any absence list, because
    that row is the sharper claim and damping it twice would double-count one
    source. And he must be a regular by :data:`ABSENCE_MIN_START_SHARE`, since
    half of every squad is out of every predicted XI and only a player the
    manager has been picking says something by being missing.

    The result is a *damp*, not a ceiling: an omission is weaker evidence than
    a printed "Out", and multiplying is how the model's own view survives it.
    """
    cols = ["code", "absence_damp"]
    if not covered or "starts" not in players.columns:
        return pd.DataFrame(columns=cols)
    frame = players[["code", "team_code", "starts"]].copy()
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
    frame = frame[~frame["code"].isin(claimed)]
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


def fetch_lineups(players: pd.DataFrame, teams: pd.DataFrame,
                  cache_dir: Path = NEWS_CACHE, cache_hours: int = 6,
                  client: httpx.Client | None = None,
                  min_coverage: float = NEWS_MIN_COVERAGE,
                  now: datetime | None = None,
                  absence: bool | None = None,
                  absence_damp: float | None = None) -> pd.DataFrame:
    """Predicted line-ups as ``[code, p_start_hint, absence_damp, …]``.

    ``absence``/``absence_damp`` default to the ``[news]`` config, read here
    rather than passed in: ``advise.py`` is protected and cannot learn to
    forward them. ``False`` reproduces the pre-v8a frame exactly, one extra
    all-null column aside.
    """
    cfg = serving_config()
    absence = cfg.news_lineup_absence if absence is None else bool(absence)
    absence_damp = (cfg.news_lineup_absence_damp if absence_damp is None
                    else float(absence_damp))
    dest = cache_path(cache_dir, "lineups", cache_hours, now)
    markup = cached_text(FFS_URL, dest, client)
    if not markup:
        return pd.DataFrame(columns=LINEUP_COLS)
    parsed = parse_lineups(markup)
    if parsed.empty:
        print("news: predicted line-ups parsed no rows — official flags only")
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
    if absence:
        # The clubs whose *pitch* parsed. An absence list on its own is not a
        # team sheet, and reading one as though it were would damp everybody
        # at a club whose XI the page never printed.
        covered = set(pd.to_numeric(
            club_codes[parsed["slot"] == "start"], errors="coerce")
            .dropna().astype(int))
        extra = notable_absences(players, covered, set(out["code"]),
                                 absence_damp)
        if not extra.empty:
            extra["p_start_hint"] = float("nan")
            extra["source"] = "lineups"
            extra["fetched_at"] = fetched_at(now)
            out = pd.concat([out, extra], ignore_index=True)
    return out[LINEUP_COLS].sort_values("code").reset_index(drop=True)
