"""Understat ingestion: the marginal xG signal FPL's own feed does not carry.

FPL publishes expected goals and expected assists, and ``ATTACK_FEATURES``
already uses them, so Understat is *not* worth scraping for xG. What it has
that nothing else does is the shape underneath: shot counts, key passes,
non-penalty xG, xGChain and xGBuildup per player-match, and per-team xGA,
PPDA and deep completions. Those separate a striker on two big chances from
one on six half-chances — the same xG, very different next week.

There is no API. Every page ships its data as hex-escaped JSON inside a
``JSON.parse('...')`` call, which is what :func:`parse_embedded_json` picks
apart. Match pages never change once played, so they are cached forever by id
and only a running season ever re-fetches.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx
import pandas as pd

from gaffer.errors import GafferError

UNDERSTAT_BASE = "https://understat.com"

TEAM_COLS = ["season", "season_idx", "team", "date", "us_xg", "us_xga",
             "ppda", "deep", "deep_allowed"]
PLAYER_COLS = ["match_id", "date", "understat_id", "player_name", "team",
               "minutes", "us_shots", "us_key_passes", "us_npxg",
               "us_xgchain", "us_xgbuildup"]
MATCH_COLS = ["match_id", "date", "home_team", "away_team", "is_result"]


def parse_embedded_json(html: str, var_name: str):
    """The payload of ``var <var_name> = JSON.parse('...')``.

    The blob is hex-escaped ASCII, so ``unicode_escape`` undoes the escaping;
    that decoder works byte-wise, though, so any real UTF-8 in the page comes
    back mojibake and has to be re-encoded through latin-1 to recover. A page
    without the variable raises rather than returning empty: "the season has
    no data" and "understat changed its markup" must not look the same.
    """
    match = re.search(var_name + r"\s*=\s*JSON\.parse\('(.*?)'\)", html,
                      re.DOTALL)
    if match is None:
        raise GafferError(
            f"understat page carries no {var_name} blob — the markup changed, "
            "or the URL was wrong")
    decoded = match.group(1).encode("utf-8").decode("unicode_escape")
    try:
        decoded = decoded.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass        # already clean ASCII
    return json.loads(decoded)


def _num(value) -> float:
    """Understat ships every number as a string, and ``None`` for absent."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def league_matches(html: str) -> pd.DataFrame:
    """``datesData`` -> ``[match_id, date, home_team, away_team, is_result]``.

    ``is_result`` is what makes an incremental refresh cheap: a fixture that
    has not been played has nothing to cache and must be re-checked next week.
    """
    rows = []
    for m in parse_embedded_json(html, "datesData") or []:
        rows.append({
            "match_id": str(m["id"]),
            "date": pd.to_datetime(m["datetime"], errors="coerce").date()
            if m.get("datetime") else None,
            "home_team": m["h"]["title"],
            "away_team": m["a"]["title"],
            "is_result": bool(m.get("isResult")),
        })
    return pd.DataFrame(rows, columns=MATCH_COLS)


def team_match_rows(html: str, season: str, season_idx: int) -> pd.DataFrame:
    """``teamsData`` -> one row per team per match.

    PPDA is passes allowed per defensive action, which understat reports as
    the two counts rather than the ratio. A zero denominator (never seen in
    practice, cheap to guard) yields NaN, because an infinity in a feature
    column is a crash somewhere downstream rather than a signal.
    """
    rows = []
    for team in (parse_embedded_json(html, "teamsData") or {}).values():
        for h in team.get("history", []):
            ppda = h.get("ppda") or {}
            att, dfn = _num(ppda.get("att")), _num(ppda.get("def"))
            rows.append({
                "season": season, "season_idx": int(season_idx),
                "team": team["title"],
                "date": pd.to_datetime(h["date"], errors="coerce").date()
                if h.get("date") else None,
                "us_xg": _num(h.get("xG")), "us_xga": _num(h.get("xGA")),
                "ppda": att / dfn if dfn else float("nan"),
                "deep": _num(h.get("deep")),
                "deep_allowed": _num(h.get("deep_allowed")),
            })
    return pd.DataFrame(rows, columns=TEAM_COLS)


def match_player_rows(html: str, match_id: str, date, home_team: str,
                      away_team: str) -> pd.DataFrame:
    """One match page -> one row per player who appeared.

    ``rostersData`` carries minutes, shots, key passes, xGChain and xGBuildup
    but *not* non-penalty xG, so npxG is summed off ``shotsData`` with the
    penalties dropped. A penalty is worth ~0.76 xG and says nothing about how
    a player creates chances from open play, which is the whole reason the
    non-penalty split is the one worth rolling.
    """
    rosters = parse_embedded_json(html, "rostersData") or {}
    shots = parse_embedded_json(html, "shotsData") or {}
    npxg: dict[str, float] = {}
    for side in ("h", "a"):
        for shot in shots.get(side, []) or []:
            if str(shot.get("situation")) == "Penalty":
                continue
            pid = str(shot.get("player_id"))
            npxg[pid] = npxg.get(pid, 0.0) + _num(shot.get("xG"))
    rows = []
    for side, team in (("h", home_team), ("a", away_team)):
        for entry in (rosters.get(side) or {}).values():
            pid = str(entry["player_id"])
            rows.append({
                "match_id": str(match_id), "date": date,
                "understat_id": pid, "player_name": entry.get("player"),
                "team": team,
                "minutes": _num(entry.get("time")),
                "us_shots": _num(entry.get("shots")),
                "us_key_passes": _num(entry.get("key_passes")),
                "us_npxg": npxg.get(pid, 0.0),
                "us_xgchain": _num(entry.get("xGChain")),
                "us_xgbuildup": _num(entry.get("xGBuildup")),
            })
    return pd.DataFrame(rows, columns=PLAYER_COLS)


CACHE_DIR = Path("data/raw/understat")
SLEEP_SECONDS = 1.0
"""Minimum gap between uncached requests.

Understat is a free site with no API and no rate-limit documentation. One
second is what a person browsing looks like, and a five-season backfill is
~1900 pages — half an hour, once, and cached forever after.
"""


def season_year(season: str) -> str:
    """``"2024-25"`` -> ``"2024"``, understat's season key."""
    return season[:4]


class UnderstatClient:
    """Fetches understat pages, caches every match forever.

    A played match's page can never change, so it is written to
    ``data/raw/understat/match/<id>.json`` on first read and served from disk
    afterwards. That is what makes the backfill resumable: a run killed
    halfway costs only the pages it had not reached. Failures are per page —
    a 503 costs that one match and returns an empty frame — and nothing
    failed is ever cached, so the next run retries it.
    """

    def __init__(self, client: httpx.Client | None = None,
                 cache_dir: Path | str | None = None,
                 sleep: float = SLEEP_SECONDS, retries: int = 3):
        self._http = client if client is not None else httpx.Client(
            timeout=30, follow_redirects=True,
            headers={"User-Agent": "gaffer/1.0 (personal FPL research)"})
        self.cache_dir = Path(cache_dir) if cache_dir is not None else CACHE_DIR
        self.sleep = float(sleep)
        self.retries = int(retries)

    def _get(self, url: str) -> str | None:
        """Page text, or ``None`` after exhausting the retries."""
        for attempt in range(self.retries):
            if self.sleep:
                time.sleep(self.sleep)
            try:
                resp = self._http.get(url)
                resp.raise_for_status()
                return resp.text
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                if attempt == self.retries - 1:
                    print(f"understat: giving up on {url} ({exc})")
        return None

    def league_matches(self, season: str) -> pd.DataFrame:
        """Every fixture id understat knows for a season."""
        html = self._get(f"{UNDERSTAT_BASE}/league/EPL/{season_year(season)}")
        if html is None:
            return pd.DataFrame(columns=MATCH_COLS)
        return league_matches(html)

    def team_history(self, season: str, season_idx: int) -> pd.DataFrame:
        """Per-team per-match xG/xGA/PPDA/deep from the league page."""
        html = self._get(f"{UNDERSTAT_BASE}/league/EPL/{season_year(season)}")
        if html is None:
            return pd.DataFrame(columns=TEAM_COLS)
        return team_match_rows(html, season, season_idx)

    def match_players(self, match_id: str, date, home_team: str,
                      away_team: str) -> pd.DataFrame:
        """One match's player rows, from cache where possible."""
        path = self.cache_dir / "match" / f"{match_id}.json"
        if path.exists():
            cached = json.loads(path.read_text())
            frame = pd.DataFrame(cached, columns=PLAYER_COLS)
            frame["date"] = date
            return frame
        html = self._get(f"{UNDERSTAT_BASE}/match/{match_id}")
        if html is None:
            return pd.DataFrame(columns=PLAYER_COLS)
        try:
            rows = match_player_rows(html, match_id, date, home_team,
                                     away_team)
        except GafferError as exc:
            print(f"understat: unparseable match {match_id} ({exc})")
            return pd.DataFrame(columns=PLAYER_COLS)
        path.parent.mkdir(parents=True, exist_ok=True)
        # The date is re-applied on read rather than stored: it is a date
        # object, JSON has no such type, and the caller always knows it.
        path.write_text(rows.drop(columns=["date"]).to_json(orient="records"))
        return rows
