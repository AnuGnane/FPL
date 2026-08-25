"""Understat ingestion: the marginal xG signal FPL's own feed does not carry.

FPL publishes expected goals and expected assists, and ``ATTACK_FEATURES``
already uses them, so Understat is *not* worth scraping for xG. What it has
that nothing else does is the shape underneath: shot counts, key passes,
non-penalty xG, xGChain and xGBuildup per player-match, and per-team xGA,
PPDA and deep completions. Those separate a striker on two big chances from
one on six half-chances — the same xG, very different next week.

There is no documented API, but the site's own pages fetch their data over
ajax, and those endpoints — ``getLeagueData/EPL/<year>`` and
``getMatchData/<id>`` — answer plain JSON to anyone who asks like a browser
does. Match data never changes once played, so it is cached forever by id and
only a running season ever re-fetches.
"""

from __future__ import annotations

import html
import json
import os
import time
from pathlib import Path

import httpx
import pandas as pd

from gaffer.data.names import normalize_name
from gaffer.errors import GafferError

UNDERSTAT_BASE = "https://understat.com"

TEAM_COLS = ["season", "season_idx", "team", "date", "us_xg", "us_xga",
             "ppda", "deep", "deep_allowed"]
PLAYER_COLS = ["match_id", "date", "understat_id", "player_name", "team",
               "minutes", "us_shots", "us_key_passes", "us_npxg",
               "us_xgchain", "us_xgbuildup"]
MATCH_COLS = ["match_id", "date", "home_team", "away_team", "is_result"]


def _require(payload, key: str, url: str):
    """One key out of a JSON payload, or a loud failure.

    Understat answering without the key it has always carried means the
    endpoint changed shape, and that must never be mistaken for a season with
    nothing in it — an empty list is data, a missing key is a broken scraper.
    """
    if not isinstance(payload, dict) or key not in payload:
        raise GafferError(
            f"understat response from {url} carries no {key!r} key — the "
            "endpoint changed, or the URL was wrong")
    return payload[key]


def _text(value):
    """Understat's own text, HTML-unescaped.

    The JSON endpoints serve the site's HTML-escaped strings verbatim, so an
    apostrophe arrives as ``&#039;`` — "N&#039;Golo Kant&eacute;". Left alone
    that normalizes to an "039" token and the player matches nothing, so
    every name and club title that lands in a frame is unescaped on the way
    in, once, at the edge.
    """
    return html.unescape(value) if isinstance(value, str) else value


def _num(value) -> float:
    """Understat ships every number as a string, and ``None`` for absent."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def league_matches(dates: list) -> pd.DataFrame:
    """``dates`` -> ``[match_id, date, home_team, away_team, is_result]``.

    ``is_result`` is what makes an incremental refresh cheap: a fixture that
    has not been played has nothing to cache and must be re-checked next week.
    """
    rows = []
    for m in dates or []:
        rows.append({
            "match_id": str(m["id"]),
            "date": pd.to_datetime(m["datetime"], errors="coerce").date()
            if m.get("datetime") else None,
            "home_team": _text(m["h"]["title"]),
            "away_team": _text(m["a"]["title"]),
            "is_result": bool(m.get("isResult")),
        })
    return pd.DataFrame(rows, columns=MATCH_COLS)


def team_match_rows(teams: dict, season: str, season_idx: int) -> pd.DataFrame:
    """``teams`` -> one row per team per match.

    PPDA is passes allowed per defensive action, which understat reports as
    the two counts rather than the ratio. A zero denominator (never seen in
    practice, cheap to guard) yields NaN, because an infinity in a feature
    column is a crash somewhere downstream rather than a signal.
    """
    rows = []
    for team in (teams or {}).values():
        for h in team.get("history", []):
            ppda = h.get("ppda") or {}
            att, dfn = _num(ppda.get("att")), _num(ppda.get("def"))
            rows.append({
                "season": season, "season_idx": int(season_idx),
                "team": _text(team["title"]),
                "date": pd.to_datetime(h["date"], errors="coerce").date()
                if h.get("date") else None,
                "us_xg": _num(h.get("xG")), "us_xga": _num(h.get("xGA")),
                "ppda": att / dfn if dfn else float("nan"),
                "deep": _num(h.get("deep")),
                "deep_allowed": _num(h.get("deep_allowed")),
            })
    return pd.DataFrame(rows, columns=TEAM_COLS)


def match_player_rows(match: dict, match_id: str, date, home_team: str,
                      away_team: str) -> pd.DataFrame:
    """One ``getMatchData`` payload -> one row per player who appeared.

    ``rosters`` carries minutes, shots, key passes, xGChain and xGBuildup but
    *not* non-penalty xG, so npxG is summed off ``shots`` with the penalties
    dropped. A penalty is worth ~0.76 xG and says nothing about how a player
    creates chances from open play, which is the whole reason the non-penalty
    split is the one worth rolling.
    """
    rosters = match.get("rosters") or {}
    shots = match.get("shots") or {}
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
                "understat_id": pid,
                "player_name": _text(entry.get("player")),
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
    """Fetches understat's JSON endpoints, caches every match forever.

    A played match can never change, so it is written to
    ``data/raw/understat/match/<id>.json`` on first read and served from disk
    afterwards. That is what makes the backfill resumable: a run killed
    halfway costs only the matches it had not reached. Failures are per
    request — a 503 costs that one match and returns an empty frame — and
    nothing failed is ever cached, so the next run retries it.

    The league document holds fixtures *and* team history, so it is memoized
    per season for the life of the client: a backfill that wants both pays
    for one download, not two.
    """

    HEADERS = {
        "User-Agent": "gaffer/1.0 (personal FPL research)",
        # The endpoints exist to serve understat's own in-page ajax; without
        # this header the site answers with HTML instead of the payload.
        "X-Requested-With": "XMLHttpRequest",
    }

    def __init__(self, client: httpx.Client | None = None,
                 cache_dir: Path | str | None = None,
                 sleep: float = SLEEP_SECONDS, retries: int = 3):
        self._http = client if client is not None else httpx.Client(
            timeout=30, follow_redirects=True, headers=dict(self.HEADERS))
        self.cache_dir = Path(cache_dir) if cache_dir is not None else CACHE_DIR
        self.sleep = float(sleep)
        self.retries = int(retries)
        self._league: dict[str, dict] = {}

    def _get_json(self, url: str):
        """Decoded JSON, or ``None`` after exhausting the retries.

        Understat labels these responses ``text/javascript``, so the decode is
        forced rather than content-type driven; a body that is not JSON at all
        is treated like any other bad response and retried.
        """
        for attempt in range(self.retries):
            if self.sleep:
                time.sleep(self.sleep)
            try:
                resp = self._http.get(url, headers=self.HEADERS)
                resp.raise_for_status()
                return json.loads(resp.text)
            except (httpx.HTTPStatusError, httpx.TransportError,
                    ValueError) as exc:
                if attempt == self.retries - 1:
                    print(f"understat: giving up on {url} ({exc})")
        return None

    def _league_data(self, season: str) -> tuple[dict | None, str]:
        """The season's league document, downloaded at most once."""
        url = f"{UNDERSTAT_BASE}/getLeagueData/EPL/{season_year(season)}"
        if season not in self._league:
            payload = self._get_json(url)
            if payload is None:
                return None, url
            self._league[season] = payload
        return self._league[season], url

    def league_matches(self, season: str) -> pd.DataFrame:
        """Every fixture id understat knows for a season."""
        payload, url = self._league_data(season)
        if payload is None:
            return pd.DataFrame(columns=MATCH_COLS)
        return league_matches(_require(payload, "dates", url))

    def team_history(self, season: str, season_idx: int) -> pd.DataFrame:
        """Per-team per-match xG/xGA/PPDA/deep from the league document."""
        payload, url = self._league_data(season)
        if payload is None:
            return pd.DataFrame(columns=TEAM_COLS)
        return team_match_rows(_require(payload, "teams", url), season,
                               season_idx)

    def match_players(self, match_id: str, date, home_team: str,
                      away_team: str) -> pd.DataFrame:
        """One match's player rows, from cache where possible.

        The cache is permanent — a played match never changes — which makes
        every way of writing the wrong thing into it unrecoverable without
        hand-deleting files. So: an empty roster (understat has not processed
        the match yet) is returned but never written, the write goes through
        a temp file and :func:`os.replace` so a killed scrape leaves either
        the old file or the new one, and a file that will not parse is
        treated as absent and re-fetched rather than raising through the
        whole backfill.
        """
        path = self.cache_dir / "match" / f"{match_id}.json"
        cached = None
        if path.exists():
            try:
                cached = json.loads(path.read_text())
            except (json.JSONDecodeError, UnicodeDecodeError):
                cached = None  # torn or truncated: re-fetch over the top
        if cached is not None:
            frame = pd.DataFrame(cached, columns=PLAYER_COLS)
            frame["date"] = date
            # Caches written before names were unescaped still hold the raw
            # ``&#039;``, and those files are never re-fetched — so the
            # unescape is applied on the way out as well as on the way in.
            for col in ("player_name", "team"):
                frame[col] = frame[col].map(_text)
            return frame
        url = f"{UNDERSTAT_BASE}/getMatchData/{match_id}"
        payload = self._get_json(url)
        if payload is None:
            return pd.DataFrame(columns=PLAYER_COLS)
        _require(payload, "rosters", url)
        rows = match_player_rows(payload, match_id, date, home_team, away_team)
        if rows.empty:
            return rows
        path.parent.mkdir(parents=True, exist_ok=True)
        # The date is re-applied on read rather than stored: it is a date
        # object, JSON has no such type, and the caller always knows it.
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(rows.drop(columns=["date"]).to_json(orient="records"))
        os.replace(tmp, path)
        return rows


def load_overrides() -> dict[str, int]:
    """Manual id mappings, documentation keys stripped."""
    from gaffer.assets import load_understat_overrides

    return {k: int(v) for k, v in load_understat_overrides().items()
            if not k.startswith("_")}


def _prefix_kin(a: str, b: str) -> bool:
    """True when one first name is a shortening of the other.

    "ben"/"benjamin", "joe"/"joseph", "alex"/"alexander" — the display name
    keeps the stem and drops the tail, so a prefix test in either direction
    catches them while "louis"/"jordan" is refused outright.
    """
    return bool(a) and bool(b) and (a.startswith(b) or b.startswith(a))


def map_understat_players(us_players: pd.DataFrame, fpl_players: pd.DataFrame,
                          team_aliases: dict[str, str],
                          overrides: dict[str, int] | None = None
                          ) -> tuple[pd.DataFrame, dict]:
    """``understat_id -> code`` lookup, plus a report of how each id resolved.

    Five passes, most conservative first, each one a full sweep over every
    understat id before the next begins:

    1. ``exact`` — a normalized full-name match at the *same club*.
    2. ``cross_club`` — a normalized full-name match that is unique across the
       whole league. That is the transfer case, where the two sources disagree
       about the club but only one player can be meant.
    3. ``token_subset`` — the two sources disagree about how much of the legal
       name to print. vaastav writes "Gabriel Martinelli Silva", "Alisson
       Ramses Becker", "Darwin Núñez Ribeiro"; understat writes the display
       name. When one side's normalized tokens are a subset of the other's and
       exactly one *same-club* FPL player qualifies, they are the same man.
    4. ``surname_club`` — the shortened first name, which no subset test
       reaches: "Ben White" against "Benjamin White". The rule is a shared
       token (the surname, in practice) *plus* first names that are prefix kin
       — both halves are required, because a shared surname alone puts Louis
       Beyer on Jordan Beyer, and a shared first name alone puts any two
       club-mates together. Again exactly one same-club candidate, or refuse.
    5. ``override`` — the manual file, for names no rule can bridge
       ("Fabinho" against "Fabio Henrique Tavares").

    Whatever survives is logged by name and dropped: an unmapped player
    contributes NaN features, which LightGBM handles natively, where a wrong
    mapping would attach one player's shot volume to another.

    Passes 3 and 4 are same-club only — never cross-club — because their
    matches are loose enough that the club is the only thing keeping them
    honest, and they claim each code at most once: understat carries a second
    id for some players ("Joe Gomez" *and* "Joseph Gomez"), and the second one
    must not re-claim a code an earlier pass already took. Sweeping rather
    than cascading is also what lets a bare "Gabriel" resolve — pass 3 first
    claims the two unambiguous Arsenal Gabriels, which leaves pass 4 exactly
    one candidate for the third.

    ``team_aliases`` maps understat club names to FPL bootstrap names; a club
    missing from it simply never matches on a same-club pass and falls through
    to the cross-club one.
    """
    overrides = load_overrides() if overrides is None else overrides
    us = us_players[["understat_id", "player_name", "team"]].drop_duplicates(
        subset=["understat_id"]).copy()
    # Not ``_name``: DataFrame.itertuples renames any column starting with an
    # underscore to a positional ``_1``, and the attribute access below would
    # silently read the wrong field.
    us["norm_name"] = us["player_name"].map(normalize_name)
    us["norm_club"] = us["team"].map(lambda t: team_aliases.get(t, t))

    fpl = fpl_players[["code", "name", "team_name"]].copy()
    fpl["norm_name"] = fpl["name"].map(normalize_name)
    by_name_club = {(r.norm_name, r.team_name): int(r.code)
                    for r in fpl.itertuples()}
    # ``fpl`` carries one row per club a code ever played for, so every count
    # below is over distinct *codes*: a player with three clubs is still one
    # player, and counting his rows would make his own name look contested.
    codes_by_name: dict[str, set[int]] = {}
    by_club: dict[object, dict[int, tuple[str, ...]]] = {}
    for r in fpl.itertuples():
        codes_by_name.setdefault(r.norm_name, set()).add(int(r.code))
        by_club.setdefault(r.team_name, {}).setdefault(
            int(r.code), tuple(r.norm_name.split()))
    unique_names = {name: next(iter(codes))
                    for name, codes in codes_by_name.items()
                    if len(codes) == 1}

    resolved: dict[str, tuple[str, int]] = {}
    claimed: set[int] = set()

    def take(understat_id, bucket: str, code: int) -> None:
        resolved[str(understat_id)] = (bucket, int(code))
        claimed.add(int(code))

    for r in us.itertuples():
        code = by_name_club.get((r.norm_name, r.norm_club))
        if code is not None:
            take(r.understat_id, "exact", code)
    for r in us.itertuples():
        if str(r.understat_id) in resolved:
            continue
        code = unique_names.get(r.norm_name)
        if code is not None:
            take(r.understat_id, "cross_club", code)

    def candidates(norm_club) -> list[tuple[int, tuple[str, ...]]]:
        """Same-club FPL players no pass has claimed yet, one per code."""
        return [(code, toks)
                for code, toks in by_club.get(norm_club, {}).items()
                if code not in claimed]

    def sweep(bucket: str, rule) -> None:
        """One pass: ``rule(us_tokens, fpl_tokens)`` on unclaimed club-mates,
        taken only when exactly one candidate says yes."""
        for r in us.itertuples():
            if str(r.understat_id) in resolved:
                continue
            us_toks = tuple(r.norm_name.split())
            if not us_toks:
                continue
            hits = [code for code, toks in candidates(r.norm_club)
                    if toks and rule(us_toks, toks)]
            if len(hits) == 1:
                take(r.understat_id, bucket, hits[0])

    sweep("token_subset",
          lambda a, b: set(a) <= set(b) or set(b) <= set(a))
    sweep("surname_club",
          lambda a, b: bool(set(a) & set(b)) and _prefix_kin(a[0], b[0]))

    for r in us.itertuples():
        if str(r.understat_id) in resolved:
            continue
        code = overrides.get(str(r.understat_id))
        if code is not None:
            take(r.understat_id, "override", code)

    rows, report = [], {"rows": int(len(us)), "exact": 0, "cross_club": 0,
                        "token_subset": 0, "surname_club": 0, "override": 0,
                        "unmatched": 0}
    unmatched_names = []
    for r in us.itertuples():
        hit = resolved.get(str(r.understat_id))
        if hit is None:
            report["unmatched"] += 1
            unmatched_names.append(f"{r.player_name} ({r.team}, "
                                   f"id {r.understat_id})")
            continue
        bucket, code = hit
        report[bucket] += 1
        rows.append({"understat_id": str(r.understat_id), "code": int(code)})
    report["unmatched_names"] = unmatched_names
    print(f"understat id mapping: {report['exact']} exact, "
          f"{report['cross_club']} cross-club, "
          f"{report['token_subset']} token-subset, "
          f"{report['surname_club']} surname-club, "
          f"{report['override']} override, "
          f"{report['unmatched']} unmatched")
    for name in unmatched_names[:20]:
        print(f"  unmatched: {name}")
    return pd.DataFrame(rows, columns=["understat_id", "code"]), report


UNDERSTAT_PLAYER_PATH = "history/understat_player.parquet"
UNDERSTAT_TEAM_PATH = "history/understat_team.parquet"

PLAYER_PARQUET_COLS = ["season", "season_idx", "understat_id", "code",
                       "player_name", "team", "date", "minutes", "us_shots",
                       "us_key_passes", "us_npxg", "us_xgchain",
                       "us_xgbuildup"]
TEAM_PARQUET_COLS = ["season", "season_idx", "team", "team_code", "date",
                     "us_xg", "us_xga", "ppda", "deep", "deep_allowed"]

# Understat's own club titles -> FPL bootstrap names. Values are FPL bootstrap
# names, so this table lands in the same vocabulary as TEAM_ALIASES and
# FOOTBALL_DATA_ALIASES — which also scopes it, like those two, to the clubs
# the configured seasons can actually contain. Relegated clubs stay, so a
# promotion needs no code change; going further back than the odds tables
# reach means adding the older clubs to all three at once.
UNDERSTAT_TEAM_ALIASES = {
    "Arsenal": "Arsenal",
    "Aston Villa": "Aston Villa",
    "Bournemouth": "Bournemouth",
    "Brentford": "Brentford",
    "Brighton": "Brighton",
    "Burnley": "Burnley",
    "Chelsea": "Chelsea",
    "Coventry": "Coventry City",
    "Crystal Palace": "Crystal Palace",
    "Everton": "Everton",
    "Fulham": "Fulham",
    "Hull": "Hull City",
    "Ipswich": "Ipswich Town",
    "Leeds": "Leeds",
    "Leicester": "Leicester",
    "Liverpool": "Liverpool",
    "Luton": "Luton",
    "Manchester City": "Man City",
    "Manchester United": "Man Utd",
    "Newcastle United": "Newcastle",
    "Nottingham Forest": "Nott'm Forest",
    "Sheffield United": "Sheffield Utd",
    "Southampton": "Southampton",
    "Sunderland": "Sunderland",
    "Tottenham": "Spurs",
    "West Ham": "West Ham",
    "Wolverhampton Wanderers": "Wolves",
}


def build_understat_player(seasons: list[str],
                           season_indexes: dict[str, int],
                           fpl_players: pd.DataFrame,
                           client: UnderstatClient | None = None,
                           store_result: bool = True) -> pd.DataFrame:
    """Scrape every played match of every season -> the player parquet.

    ``fpl_players`` is ``[code, name, team_name]`` — the FPL side of the id
    mapping. Rows for players the mapping could not resolve are dropped, so
    the parquet only ever carries stats that belong to a code we can join on;
    the ``code`` column is why this frame is usable at all and is why it is
    stored alongside the ``understat_id`` the spec lists.

    Cached matches cost nothing, so re-running after a killed backfill is
    cheap and only the running season ever adds pages.
    """
    from gaffer.data import store

    client = client or UnderstatClient()
    frames = []
    for season in seasons:
        idx = season_indexes[season]
        fixtures = client.league_matches(season)
        played = fixtures[fixtures["is_result"]]
        print(f"understat {season}: {len(played)} played matches")
        for m in played.itertuples():
            rows = client.match_players(m.match_id, m.date, m.home_team,
                                        m.away_team)
            if rows.empty:
                continue
            rows = rows.copy()
            rows["season"] = season
            rows["season_idx"] = int(idx)
            frames.append(rows)
    if not frames:
        out = pd.DataFrame(columns=PLAYER_PARQUET_COLS)
        if store_result:
            store.save(out, UNDERSTAT_PLAYER_PATH)
        return out
    us = pd.concat(frames, ignore_index=True)
    mapping, _report = map_understat_players(us, fpl_players,
                                             UNDERSTAT_TEAM_ALIASES)
    out = us.merge(mapping, on="understat_id", how="inner")
    out = out[PLAYER_PARQUET_COLS]
    if store_result:
        store.save(out, UNDERSTAT_PLAYER_PATH)
    return out


def build_understat_team(seasons: list[str], season_indexes: dict[str, int],
                         name_to_code: dict[str, int],
                         client: UnderstatClient | None = None,
                         store_result: bool = True) -> pd.DataFrame:
    """Per-team per-match xG/xGA/PPDA/deep -> the team parquet.

    ``name_to_code`` maps FPL bootstrap names to team codes. A club with no
    code — a season the bootstrap tables do not cover — is dropped rather than
    carried with a NaN key that would silently never join. The dropped names
    are printed per season: silence here is how a whole promoted club goes
    missing from a season's features without anyone noticing.

    The lookup goes through :func:`gaffer.data.match_odds._code_for` rather
    than a plain dict hit, because ``UNDERSTAT_TEAM_ALIASES`` targets the
    *current* bootstrap spelling ("Ipswich Town") while an older season's
    table still carries the one it used then ("Ipswich").
    """
    from gaffer.data import store
    from gaffer.data.match_odds import _code_for

    client = client or UnderstatClient()
    frames = []
    for season in seasons:
        rows = client.team_history(season, season_indexes[season])
        if rows.empty:
            continue
        rows = rows.copy()
        fpl_names = rows["team"].map(lambda t: UNDERSTAT_TEAM_ALIASES.get(t, t))
        rows["team_code"] = [_code_for(n, name_to_code) for n in fpl_names]
        keep = rows["team_code"].notna()
        dropped = sorted(set(fpl_names[~keep]))
        if dropped:
            print(f"understat teams: no FPL code in {season} for "
                  f"{', '.join(dropped)}")
        frames.append(rows[keep])
    if not frames:
        out = pd.DataFrame(columns=TEAM_PARQUET_COLS)
    else:
        out = pd.concat(frames, ignore_index=True)
        out["team_code"] = out["team_code"].astype(int)
        out = out[TEAM_PARQUET_COLS]
    if store_result:
        store.save(out, UNDERSTAT_TEAM_PATH)
    return out


def history_player_index(seasons: list[str]) -> pd.DataFrame:
    """``[code, name, team_name]``, one row per club a code ever played for.

    The FPL side of the id mapping, built offline from what is already on
    disk: a scrape must not need a live bootstrap call, and history covers
    seasons the current bootstrap has forgotten.

    A code gets a row for *every* club it appeared for across ``seasons``, not
    just its newest one, because understat's rows span the same seasons: the
    2022-23 half of the scrape has Solanke at Bournemouth, and pinning his
    code to Spurs would lose the same-club match for him and for every other
    player who has since transferred. Multiple rows per code are therefore
    expected downstream, and :func:`map_understat_players` dedupes its
    candidate sets by code so two routes to one club never read as two rival
    players.

    The *name* still comes from the newest row per code — one spelling per
    player, the current one — and a club whose code has no bootstrap name in
    any of the seasons is dropped rather than carried as a null that would
    silently never match.
    """
    from gaffer.data import store
    from gaffer.data.history import season_name_codes

    player_gw = store.load("history/player_gw.parquet")
    # A club's bootstrap name is per season, and the odd rename means one
    # team code can carry two: keep both, so either spelling matches.
    code_to_names: dict[int, set[str]] = {}
    for _season, table in season_name_codes(seasons).items():
        for name, code in table.items():
            code_to_names.setdefault(int(code), set()).add(name)

    ordered = player_gw.sort_values(["season_idx", "gw"])
    latest_name = {int(r.code): r.name for r
                   in ordered.groupby("code", as_index=False).tail(1)
                   .itertuples()}
    pairs = ordered[["code", "team_code"]].dropna().drop_duplicates()
    rows = []
    for r in pairs.itertuples():
        code = int(r.code)
        for club in sorted(code_to_names.get(int(r.team_code), ())):
            rows.append({"code": code, "name": latest_name[code],
                         "team_name": club})
    return pd.DataFrame(rows, columns=["code", "name", "team_name"])
