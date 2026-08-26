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

import html
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


_PROFILE = re.compile(r'href="/([a-z0-9\-]+)/profil/spieler/(\d+)"', re.I)
"""The squad page's player links.

Keyed on ``/profil/spieler/`` specifically: every row also links the same
player's market-value history under ``/marktwertverlauf/spieler/``, and the
same page links twenty other clubs under ``/startseite/verein/``.
"""


def squad_url(club_slug: str, club_id: int, season_year: int) -> str:
    """The club's squad list for one season."""
    return (f"{TM_BASE}/{club_slug}/kader/verein/{int(club_id)}"
            f"/saison_id/{int(season_year)}")


def player_url(player_slug: str, player_id: int) -> str:
    """One player's injury history — season, injury, from, until, days."""
    return f"{TM_BASE}/{player_slug}/verletzungen/spieler/{int(player_id)}"


def _cached_page(url: str, dest: Path,
                 client: httpx.Client | None = None) -> str | None:
    """The page at ``url``, from ``dest`` if it has ever been fetched.

    Permanently rather than per window, unlike the live news sources: this
    runs once a season from a CLI, over some six hundred pages, and a sweep
    that dies half way through must resume for free. Delete the cache
    directory to force a refresh.
    """
    if dest.exists():
        return dest.read_text(encoding="utf-8")
    http = news_client(client)
    try:
        resp = http.get(url)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"transfermarkt: {url} unavailable ({exc})")
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(resp.text, encoding="utf-8")
    return resp.text


def squad_player_ids(club_slug: str, club_id: int, season_year: int,
                     client: httpx.Client | None = None,
                     cache_dir: Path = NEWS_CACHE
                     ) -> list[tuple[str, int]]:
    """``[(player slug, player id)]`` for one club's season squad.

    In page order and deduplicated: a row prints its player twice on the
    responsive layout, and asking for the same injury history twice is two
    requests we do not have a reason to make.
    """
    dest = (Path(cache_dir) / "transfermarkt"
            / f"squad-{club_slug}-{int(club_id)}-{int(season_year)}.html")
    markup = _cached_page(squad_url(club_slug, club_id, season_year), dest,
                          client)
    if not markup:
        return []
    seen: dict[int, tuple[str, int]] = {}
    for slug, pid in _PROFILE.findall(markup):
        seen.setdefault(int(pid), (slug, int(pid)))
    return list(seen.values())


def parse_injury_spells(markup: str) -> pd.DataFrame:
    """The injury-history table -> ``[season, injury_type, days_out, games]``.

    A row with no parseable duration is dropped: the curve is a distribution
    over lengths, and a spell of unknown length is not a sample of it.
    """
    rows = []
    for block in _ROW.findall(markup or ""):
        cells = [html.unescape(_TAG.sub(" ", c)).replace("\xa0", " ").strip()
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


def fetch_player_spells(player_slug: str, player_id: int,
                        client: httpx.Client | None = None,
                        cache_dir: Path = NEWS_CACHE) -> pd.DataFrame:
    """One player's whole injury history, cached permanently by player.

    Per player rather than per club because the club-level history page the
    v5 design assumed does not exist: ``/verletztespieler/verein/`` 404s.
    Six hundred requests instead of twenty, which is why they are cached
    forever and paced by the caller.
    """
    dest = (Path(cache_dir) / "transfermarkt"
            / f"player-{player_slug}-{int(player_id)}.html")
    markup = _cached_page(player_url(player_slug, player_id), dest, client)
    if not markup:
        return pd.DataFrame(columns=SPELL_COLS)
    return parse_injury_spells(markup)
