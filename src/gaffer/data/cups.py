"""Cup, European and EFL fixture dates — the half of congestion FPL does not
publish.

A player who played 120 minutes of a midweek EFL Cup tie is a different
rotation risk on Saturday, and nothing in the FPL feed says the tie happened:
``fixtures.parquet`` carries league matches only. FPL-Core-Insights publishes
per-tournament match files keyed by the stable FPL team *code* — Brentford is
94 there, not its 2025-26 season id of 5 — with a fallback through the
season's id table for anything that is not a code (see :func:`_team_code`).
Either way they join onto our own frames without a name table.

Only the *dates* are taken. Cup minutes, cup goals and cup xG are deliberately
left on the floor: they are a different competition against different
opposition, and the model is predicting FPL points. What congestion needs is
"did this club play on Wednesday", and that is one column.
"""

from __future__ import annotations

import io
from pathlib import Path

import httpx
import pandas as pd

from gaffer.data import store
from gaffer.io import atomic_write

CUPS_REPO = "olbauday/FPL-Core-Insights"
CUPS_RAW_BASE = f"https://raw.githubusercontent.com/{CUPS_REPO}/main"
CUPS_TREE_URL = (f"https://api.github.com/repos/{CUPS_REPO}/git/trees/"
                 "main?recursive=1")
CUPS_CACHE = Path("data/raw/cups")
CUPS_PATH = "history/cup_matches.parquet"

CUP_TOURNAMENTS = ("EFL Cup", "Champions League", "Europa League",
                   "Conference League")
"""Tournaments worth a congestion row.

``Premier League`` is deliberately absent: those fixtures are already in
``history/fixtures.parquet`` and counting them twice would double every
14-day count. Friendlies are absent because a pre-season friendly is not a
congestion event in any gameweek the model predicts.
"""

CUP_ROW_COLS = ["season", "season_idx", "tournament", "date", "team_code"]


def team_code_map(teams_csv: str,
                  names: dict[str, int] | None = None) -> dict[int, int]:
    """``{season team id: stable FPL team code}`` from a season ``teams.csv``.

    The published table normally carries both, in which case it is read
    straight off. When it carries only ids and names — the shape older season
    folders use — the caller's ``{bootstrap name: code}`` table supplies the
    codes, exactly as ``build_match_odds`` threads ``names_by_season`` through
    for football-data. A club neither route resolves is simply absent, and its
    matches drop rather than landing on the wrong club.
    """
    df = pd.read_csv(io.StringIO(teams_csv))
    if df.empty or "id" not in df.columns:
        return {}
    if "code" in df.columns:
        pairs = zip(pd.to_numeric(df["id"], errors="coerce"),
                    pd.to_numeric(df["code"], errors="coerce"))
        return {int(i): int(c) for i, c in pairs
                if pd.notna(i) and pd.notna(c)}
    table = names or {}
    out: dict[int, int] = {}
    for r in df.itertuples():
        code = table.get(str(getattr(r, "name", "")))
        if code is not None and pd.notna(r.id):
            out[int(r.id)] = int(code)
    return out


def _team_code(value, codes: dict[int, int],
               known: set[int]) -> int | None:
    """One ``home_team``/``away_team`` cell -> a stable FPL team code.

    The published cup files write the *code* (Brentford is 94 there, while its
    2025-26 season id is 5), so a value the season table already knows as a
    code is taken as one. A value that is not a code but is a season id is
    translated, which is what keeps the reader working if the archive ever
    switches to ids. Anything neither route resolves — a non-league club,
    which the file leaves blank — comes back ``None`` and its row drops.
    """
    if pd.isna(value):
        return None
    v = int(value)
    if v in known:
        return v
    return codes.get(v)


def cup_match_rows(matches_csv: str, season: str, season_idx: int,
                   codes: dict[int, int]) -> pd.DataFrame:
    """One ``matches.csv`` -> one row per *league* club per played match.

    Both sides are emitted independently, because a tie between a Premier
    League club and an EFL one is a congestion event for exactly one of them
    and the file writes a blank id for the other. A match with no kickoff time
    has not been scheduled yet and carries no date to count against.
    """
    df = pd.read_csv(io.StringIO(matches_csv))
    if df.empty or "kickoff_time" not in df.columns:
        return pd.DataFrame(columns=CUP_ROW_COLS)
    kt = pd.to_datetime(df["kickoff_time"], errors="coerce", utc=True)
    date = kt.dt.tz_convert("Europe/London").dt.date
    tournament = (df["tournament"] if "tournament" in df.columns
                  else pd.Series("", index=df.index))
    known = set(codes.values())
    rows = []
    for side in ("home_team", "away_team"):
        if side not in df.columns:
            continue
        ids = pd.to_numeric(df[side], errors="coerce")
        part = pd.DataFrame({
            "season": season, "season_idx": int(season_idx),
            "tournament": tournament.values, "date": date.values,
            "team_code": [_team_code(i, codes, known) for i in ids]})
        rows.append(part)
    if not rows:
        return pd.DataFrame(columns=CUP_ROW_COLS)
    out = pd.concat(rows, ignore_index=True)
    out = out[out["team_code"].notna() & out["date"].notna()]
    out["team_code"] = out["team_code"].astype(int)
    return out[CUP_ROW_COLS].reset_index(drop=True)


def cup_paths_from_tree(tree: dict, seasons: list[str]) -> list[str]:
    """Every ``matches.csv`` path in the repo tree for the wanted seasons.

    One request to the git-trees API answers what would otherwise be a
    404-probe per (tournament, gameweek) — roughly 150 requests per season
    against one. ``seasons`` are FPL-style ("2025-26"); the repo folders are
    ("2025-2026"), so they are translated here, in the one place that knows
    the repo's layout.
    """
    wanted = {repo_season(s) for s in seasons}
    out = []
    for node in (tree or {}).get("tree", []):
        path = node.get("path", "")
        if not path.endswith("/matches.csv") or "/By Tournament/" not in path:
            continue
        parts = path.split("/")
        if len(parts) < 6 or parts[0] != "data":
            continue
        if parts[1] in wanted and parts[3] in CUP_TOURNAMENTS:
            out.append(path)
    return sorted(out)


def repo_season(season: str) -> str:
    """``"2025-26"`` -> ``"2025-2026"``, the repo's folder naming."""
    start, end = season.split("-")
    return f"{start}-{start[:2]}{end}"


def _http(client: httpx.Client | None) -> httpx.Client:
    return client if client is not None else httpx.Client(
        timeout=60, follow_redirects=True,
        headers={"User-Agent": "gaffer/1.0 (FPL advisor; cup fixtures)"})


def _cached_get(http: httpx.Client, url: str, dest: Path) -> str | None:
    """One file, cached forever under ``dest``.

    A finished cup match never changes, and the ingest is a once-a-season job,
    so a file on disk is never re-fetched. A 404 or a dead connection returns
    ``None`` with a printed line: an ingest spanning four tournaments and two
    seasons must not die on one missing gameweek folder.
    """
    if dest.exists():
        return dest.read_text()
    try:
        resp = http.get(url)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"cups: skipping {url} ({exc})")
        return None
    # Atomically (v12 W1's house rule): the cache is what a re-run trusts
    # instead of the network, so a run killed mid-write must leave either the
    # whole previous file or no file, never half of one that parses.
    atomic_write(dest, resp.text)
    return resp.text


def download_cup_matches(seasons: list[str], season_indexes: dict[str, int],
                         cache_dir: Path = CUPS_CACHE,
                         client: httpx.Client | None = None,
                         names: dict[str, int] | None = None) -> pd.DataFrame:
    """Every cup match date for ``seasons`` -> ``history/cup_matches.parquet``.

    One tree listing, then one cached GET per ``matches.csv``. Seasons the
    repo does not publish simply contribute nothing — the archive starts at
    2024-25 while our training window starts earlier, and a season with no cup
    rows undercounts congestion rather than breaking it.
    """
    http = _http(client)
    try:
        tree = http.get(CUPS_TREE_URL).json()
    except (httpx.HTTPError, ValueError) as exc:
        print(f"cups: tree listing unavailable ({exc})")
        tree = {}
    codes_by_season: dict[str, dict[int, int]] = {}
    frames = []
    for path in cup_paths_from_tree(tree, seasons):
        folder = path.split("/")[1]
        season = next((s for s in seasons if repo_season(s) == folder), None)
        if season is None:
            continue
        if season not in codes_by_season:
            teams_path = f"data/{folder}/teams.csv"
            text = _cached_get(http, f"{CUPS_RAW_BASE}/{teams_path}",
                               Path(cache_dir) / teams_path)
            codes_by_season[season] = (team_code_map(text, names)
                                       if text else {})
        text = _cached_get(http, f"{CUPS_RAW_BASE}/{path}",
                           Path(cache_dir) / path)
        if not text:
            continue
        frames.append(cup_match_rows(
            text, season, season_indexes.get(season, 0),
            codes_by_season[season]))
    out = (pd.concat(frames, ignore_index=True) if frames
           else pd.DataFrame(columns=CUP_ROW_COLS))
    out = out.drop_duplicates(subset=["season_idx", "tournament", "date",
                                      "team_code"]).reset_index(drop=True)
    store.save(out, CUPS_PATH)
    return out


def load_cup_matches() -> pd.DataFrame | None:
    """The stored cup-date frame, or ``None`` when the ingest never ran.

    ``None`` rather than an empty frame, so ``add_congestion`` can tell
    "no cup data on this machine" from "this club played no cups": the first
    must produce the same feature everywhere, the second is a real zero.
    """
    if not store.exists(CUPS_PATH):
        return None
    return store.load(CUPS_PATH)
