"""premierinjuries.com — the injury table, roughly a day ahead of the flag.

The whole reason this source is worth a scraper: FPL sets ``status`` and
``chance_of_playing`` when the club confirms, which is often Friday afternoon
for a Saturday deadline. The injury press reports it on Thursday. That one-day
head start is the entire edge, and it is why this layer is applied at
prediction time rather than trained on — there is no historical record of what
this page said, so it can only ever be measured forward (spec §9, gate N2).

The parse is deliberately shallow: five columns off one table. A page rewrite
yields an empty frame, and an empty frame is the official-flags path.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import httpx
import pandas as pd

from gaffer.data.news import NEWS_CACHE, cache_path, cached_text, fetched_at
from gaffer.data.news.normalize import NEWS_MIN_COVERAGE, match_codes

PI_URL = "https://www.premierinjuries.com/injury-table.php"

INJURY_COLS = ["code", "injury_type", "news_status", "expected_return_date",
               "source", "fetched_at"]

PARSE_COLS = ["name", "club", "injury_type", "status", "expected_return_date"]

INJURY_TYPES = {
    "hamstring": "hamstring", "knee": "knee", "ankle": "ankle",
    "groin": "groin", "calf": "calf", "thigh": "thigh", "back": "back",
    "foot": "foot", "toe": "foot", "shoulder": "shoulder", "hip": "hip",
    "achilles": "achilles", "knock": "knock", "illness": "illness",
    "virus": "illness", "concussion": "concussion", "muscle": "muscle",
    "fitness": "fitness", "suspension": "suspension",
}
"""Free-text injury description -> the vocabulary the return curves use.

Matched on the first keyword found in the string, so "Hamstring Injury",
"hamstring strain" and "tight hamstring" all land on ``hamstring``. Anything
unrecognised becomes ``unknown``, which the curve loader answers with the
pooled fallback — the point of having a pooled curve at all.
"""

UNKNOWN_INJURY = "unknown"

STATUS_WORDS = {"out": "out", "doubtful": "doubtful", "doubt": "doubtful",
                "suspended": "out"}
"""Status column -> {out, doubtful}. Anything else reads as a doubt: the
column is prose, and the binding claim is the return date."""

_TAG = re.compile(r"<[^>]+>")
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)


def normalize_injury_type(text: str) -> str:
    """The first recognised keyword in a free-text description."""
    low = str(text or "").casefold()
    for key, value in INJURY_TYPES.items():
        if key in low:
            return value
    return UNKNOWN_INJURY


def _cell_text(html: str) -> str:
    return _TAG.sub(" ", html).replace("&nbsp;", " ").strip()


def _return_date(text: str):
    """``dd/mm/yyyy`` (the site's format) -> a plain date, or ``None``.

    ``dayfirst`` explicitly: 05/09/2026 is September the 5th on a British site
    and May the 9th to pandas' default, and that difference is three gameweeks
    of expected return.
    """
    value = str(text or "").strip()
    if not value:
        return None
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    return None if pd.isna(parsed) else parsed.date()


def parse_injury_table(html: str) -> pd.DataFrame:
    """The injury table -> ``[name, club, injury_type, status, return date]``.

    Regex rather than a parser dependency: this is one table of five columns,
    and the failure mode that matters (the page was redesigned) produces zero
    rows either way, which is exactly the degradation the rails want.
    """
    rows = []
    for block in _ROW.findall(html or ""):
        cells = [_cell_text(c) for c in _CELL.findall(block)]
        if len(cells) < 5 or not cells[0] or cells[0].casefold() == "player":
            continue
        rows.append({
            "name": cells[0], "club": cells[1],
            "injury_type": normalize_injury_type(cells[2]),
            "status": STATUS_WORDS.get(cells[3].casefold(), "doubtful"),
            "expected_return_date": _return_date(cells[4])})
    return pd.DataFrame(rows, columns=PARSE_COLS)


def fetch_injuries(players: pd.DataFrame, teams: pd.DataFrame,
                   cache_dir: Path = NEWS_CACHE, cache_hours: int = 6,
                   client: httpx.Client | None = None,
                   min_coverage: float = NEWS_MIN_COVERAGE,
                   now: datetime | None = None) -> pd.DataFrame:
    """The injury table as ``[code, injury_type, news_status, …]``.

    Empty on every failure — dead host, rewritten page, match rate below the
    floor — and an empty frame is what makes the whole layer inert.
    """
    dest = cache_path(cache_dir, "premierinjuries", cache_hours, now)
    html = cached_text(PI_URL, dest, client)
    if not html:
        return pd.DataFrame(columns=INJURY_COLS)
    parsed = parse_injury_table(html)
    if parsed.empty:
        print("news: premierinjuries parsed no rows — official flags only")
        return pd.DataFrame(columns=INJURY_COLS)
    matched = match_codes(parsed, players, teams, label="premierinjuries",
                          min_coverage=min_coverage)
    if matched.empty:
        return pd.DataFrame(columns=INJURY_COLS)
    out = matched.rename(columns={"status": "news_status"})
    out["source"] = "premierinjuries"
    out["fetched_at"] = fetched_at(now)
    # One row per player: the table can list a knock and a long-term injury
    # for the same man, and the later return date is the binding one.
    out = (out.sort_values("expected_return_date", na_position="first")
           .groupby("code", as_index=False).tail(1))
    return out[INJURY_COLS].sort_values("code").reset_index(drop=True)
