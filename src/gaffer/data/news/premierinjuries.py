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
               "news_chance_pct", "source", "fetched_at"]

PARSE_COLS = ["name", "club", "injury_type", "status",
              "expected_return_date", "news_chance_pct"]

CELL_LABELS = ("Player", "Reason", "Further Detail", "Potential Return",
               "Condition", "Status")
"""The column labels the page prints *inside* every cell of every row.

The table has no club column and no header the parse can key on: each ``<td>``
reads "Player Bukayo Saka", "Reason Hamstring Injury", "Status Ruled Out". So
the label is the key — stripped off the front of the cell it names — and the
column order is only the fallback for a page that stops printing them.
"""

NO_RETURN = "no return date"
"""The site's literal text where a date would go. Unparseable either way, but
worth naming: it means "nobody knows", not "no injury"."""

INJURY_TYPES = {
    "hamstring": "hamstring", "knee": "knee", "ankle": "ankle",
    "groin": "groin", "calf": "calf", "thigh": "thigh", "back": "back",
    "foot": "foot", "toe": "foot", "shoulder": "shoulder", "hip": "hip",
    "achilles": "achilles", "knock": "knock", "illness": "illness",
    "virus": "illness", "concussion": "concussion", "muscle": "muscle",
    "fitness": "fitness", "suspend": "suspension",
}
"""Free-text injury description -> the vocabulary the return curves use.

Matched on the first keyword found in the string, so "Hamstring Injury",
"hamstring strain" and "tight hamstring" all land on ``hamstring``. Anything
unrecognised becomes ``unknown``, which the curve loader answers with the
pooled fallback — the point of having a pooled curve at all, and what the
site's own "Other" reason resolves to.

Read off the *Reason* column, which is this short vocabulary, and never off
the free-text detail beside it: that cell is a quote from a manager, and it
names body parts belonging to whatever else the sentence is about.
``suspend`` rather than ``suspension`` because the site writes "Suspended".
"""

UNKNOWN_INJURY = "unknown"

STATUS_WORDS = {"ruled out": "out", "out": "out", "doubtful": "doubtful",
                "doubt": "doubtful", "suspended": "out"}
"""Status column -> {out, doubtful}. Anything the table does not spell this
way reads as a doubt: the binding claims are the return date and the
percentage, and neither is in this word."""

_TAG = re.compile(r"<[^>]+>")
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
_PCT = re.compile(r"^(\d{1,3}(?:\.\d+)?)\s*%$")


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
    if not value or value.casefold() == NO_RETURN:
        return None
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    return None if pd.isna(parsed) else parsed.date()


def _strip_label(text: str, label: str) -> str:
    """A cell with its own column label peeled off the front."""
    value = str(text or "").strip()
    if value.casefold().startswith(label.casefold()):
        value = value[len(label):]
    return value.strip(" :–- ").strip()


def _labelled(cells: list[str]) -> dict[str, str]:
    """One row's cells -> ``{label: content}``, by prefix and then position.

    The prefix pass is the real reading and is order-free: whichever cell says
    "Potential Return …" is the return date wherever the site moves it. The
    positional pass only fills labels nothing claimed, so a page that stops
    printing them degrades to the old column-order reading rather than to an
    empty row.
    """
    out: dict[str, str] = {}
    used: set[int] = set()
    for label in CELL_LABELS:
        for i, cell in enumerate(cells):
            if i not in used and cell.casefold().startswith(label.casefold()):
                out[label] = _strip_label(cell, label)
                used.add(i)
                break
    for pos, label in enumerate(CELL_LABELS):
        if label not in out and pos < len(cells) and pos not in used:
            out[label] = cells[pos].strip()
    return out


def _status(text: str) -> tuple[str, float | None]:
    """The status cell -> ``(out|doubtful, chance the site printed)``.

    The column is either "Ruled Out" or a percentage. A percentage is a
    ``chance_of_playing`` handed over a day before FPL sets its own, so it is
    carried through as a number rather than flattened into "doubtful" — a 25%
    and a 75% are the same word and very different team sheets.
    """
    value = str(text or "").strip()
    pct = _PCT.match(value)
    if pct:
        return "doubtful", float(pct.group(1))
    return STATUS_WORDS.get(value.casefold(), "doubtful"), None


def parse_injury_table(html: str) -> pd.DataFrame:
    """The injury table -> ``[name, club, injury_type, status, date, pct]``.

    Every cell of every row prints the name of its own column in front of the
    value, and there is no club column at all, so the parse keys on those
    labels (:data:`CELL_LABELS`) rather than on positions. ``club`` comes out
    empty for that reason, which sends every row down
    :func:`~gaffer.data.news.normalize.match_codes`'s all-clubs path, where a
    name is taken only when exactly one unclaimed player in the league answers
    to it.

    Regex rather than a parser dependency: the failure mode that matters (the
    page was redesigned again) produces zero rows either way, which is exactly
    the degradation the rails want.
    """
    rows = []
    for block in _ROW.findall(html or ""):
        cells = [_cell_text(c) for c in _CELL.findall(block)]
        if len(cells) < 5:
            continue
        fields = _labelled(cells)
        name = fields.get("Player", "").strip()
        if not name or name.casefold() == "player":
            continue
        status, pct = _status(fields.get("Status", ""))
        rows.append({
            "name": name,
            "club": "",
            "injury_type": normalize_injury_type(fields.get("Reason", "")),
            "status": status,
            "expected_return_date": _return_date(
                fields.get("Potential Return", "")),
            "news_chance_pct": pct})
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
