"""Transfermarkt injury spells — a calibration input, never a live feed.

The question the flat ``RECOVERY = 0.7`` constant answers badly: how long is a
hamstring, actually? Transfermarkt records every spell's start, end and days
out per player, which is the empirical distribution the return curves are
fitted from.

Fetched by ``gaffer calibrate-injuries`` and by nothing else. Live code reads
``src/gaffer/assets/injury_return_curves.json`` and never this module — a
weekly advise run must not depend on a scrape of a site that has no reason to
be up on a Friday afternoon.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pandas as pd

from gaffer.data.news import NEWS_CACHE, news_client
from gaffer.data.news.premierinjuries import normalize_injury_type

TM_BASE = "https://www.transfermarkt.co.uk"

SPELL_COLS = ["season", "injury_type", "days_out", "games_missed"]

_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_DAYS = re.compile(r"(\d+)\s*days?", re.I)


def club_url(club_slug: str, club_id: int) -> str:
    """The club's injury-history page.

    One page per club rather than one per player: the same spells, two orders
    of magnitude fewer requests, and the curves are fitted pooled anyway.
    """
    return (f"{TM_BASE}/{club_slug}/verletztespieler/verein/{int(club_id)}"
            "/plus/1")


def parse_injury_spells(html: str) -> pd.DataFrame:
    """The injury-history table -> ``[season, injury_type, days_out, games]``.

    A row with no parseable duration is dropped: the curve is a distribution
    over lengths, and a spell of unknown length is not a sample of it.
    """
    rows = []
    for block in _ROW.findall(html or ""):
        cells = [_TAG.sub(" ", c).replace("&nbsp;", " ").strip()
                 for c in _CELL.findall(block)]
        if len(cells) < 5 or cells[0].casefold() == "season":
            continue
        days = _DAYS.search(cells[4])
        if not days:
            continue
        games = re.sub(r"[^0-9]", "", cells[5]) if len(cells) > 5 else ""
        rows.append({"season": cells[0],
                     "injury_type": normalize_injury_type(cells[1]),
                     "days_out": float(days.group(1)),
                     "games_missed": float(games or 0)})
    return pd.DataFrame(rows, columns=SPELL_COLS)


def fetch_club_spells(club_slug: str, club_id: int,
                      cache_dir: Path = NEWS_CACHE,
                      client: httpx.Client | None = None) -> pd.DataFrame:
    """One club's injury history, cached permanently by club.

    Permanently rather than per window: this runs once a season from a CLI,
    and a re-run inside the same season should cost nothing. Delete the cache
    directory to force a refresh.
    """
    dest = Path(cache_dir) / "transfermarkt" / f"{club_slug}-{club_id}.html"
    if dest.exists():
        return parse_injury_spells(dest.read_text(encoding="utf-8"))
    http = news_client(client)
    try:
        resp = http.get(club_url(club_slug, club_id))
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"transfermarkt: {club_slug} unavailable ({exc})")
        return pd.DataFrame(columns=SPELL_COLS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(resp.text, encoding="utf-8")
    return parse_injury_spells(resp.text)
