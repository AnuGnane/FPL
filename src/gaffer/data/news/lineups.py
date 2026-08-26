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

from gaffer.data.news import NEWS_CACHE, cache_path, cached_text, fetched_at
from gaffer.data.news.normalize import NEWS_MIN_COVERAGE, match_codes

FFS_URL = "https://www.fantasyfootballscout.co.uk/team-news/"

P_START_HINT = {"start": 1.0, "bench": 0.25, "out": 0.0}
"""Slot -> the ceiling this source puts on ``p_play`` for the first gameweek.

``0.25`` for a bench candidate rather than ``0`` because named substitutes do
come on. It is a *ceiling*, never a floor: a fringe player the model already
prices at 0.1 is left exactly where he is, and a 1.0 for a predicted starter
is a no-op by construction.
"""

LINEUP_COLS = ["code", "p_start_hint", "source", "fetched_at"]
PARSE_COLS = ["name", "club", "slot"]

SLOT_CLASSES = {"starting-xi": "start", "subs": "bench",
                "unavailable": "out"}

_TEAM = re.compile(r'data-club="([^"]+)"(.*?)(?=data-club="|\Z)', re.S)
_LIST = re.compile(r'<ul class="([a-z\-]+)"[^>]*>(.*?)</ul>', re.S | re.I)
_ITEM = re.compile(r"<li[^>]*>(.*?)</li>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")


def parse_lineups(markup: str) -> pd.DataFrame:
    """The predicted line-ups page -> ``[name, club, slot]``.

    Same shallow-regex posture as the injury table, and the same failure mode:
    a redesign yields zero rows, which is the official-flags path.
    """
    rows = []
    for club, block in _TEAM.findall(markup or ""):
        # Both sides are HTML: the club lives in an attribute that spells
        # "Brighton &amp; Hove Albion", which misses the alias table, and the
        # names carry "&#039;" where the bootstrap has an apostrophe.
        club = html.unescape(club).strip()
        for cls, body in _LIST.findall(block):
            slot = SLOT_CLASSES.get(cls)
            if slot is None:
                continue
            for item in _ITEM.findall(body):
                name = html.unescape(_TAG.sub(" ", item)).strip()
                if name:
                    rows.append({"name": name, "club": club, "slot": slot})
    return pd.DataFrame(rows, columns=PARSE_COLS)


def fetch_lineups(players: pd.DataFrame, teams: pd.DataFrame,
                  cache_dir: Path = NEWS_CACHE, cache_hours: int = 6,
                  client: httpx.Client | None = None,
                  min_coverage: float = NEWS_MIN_COVERAGE,
                  now: datetime | None = None) -> pd.DataFrame:
    """Predicted line-ups as ``[code, p_start_hint, source, fetched_at]``."""
    dest = cache_path(cache_dir, "lineups", cache_hours, now)
    markup = cached_text(FFS_URL, dest, client)
    if not markup:
        return pd.DataFrame(columns=LINEUP_COLS)
    parsed = parse_lineups(markup)
    if parsed.empty:
        print("news: predicted line-ups parsed no rows — official flags only")
        return pd.DataFrame(columns=LINEUP_COLS)
    matched = match_codes(parsed, players, teams, label="lineups",
                          min_coverage=min_coverage)
    if matched.empty:
        return pd.DataFrame(columns=LINEUP_COLS)
    out = matched.copy()
    out["p_start_hint"] = out["slot"].map(P_START_HINT).astype("float64")
    out["source"] = "lineups"
    out["fetched_at"] = fetched_at(now)
    # A player named in two blocks (listed as a doubt and on the bench) takes
    # the most pessimistic hint — the same rule availability_frame applies
    # between sources.
    out = (out.sort_values("p_start_hint")
           .groupby("code", as_index=False).head(1))
    return out[LINEUP_COLS].sort_values("code").reset_index(drop=True)
