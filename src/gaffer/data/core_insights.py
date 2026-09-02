"""FPL-Core-Insights: per-match detail, published cup fixtures, club Elo.

``cups.py`` (v8a) already reads this repository for one thing — the *dates*
league clubs played cup ties on — and deliberately leaves everything else on
the floor. This module takes the rest: per-player per-match defensive and
positional detail, the whole published fixture list including ties that have
not been played yet, and the Elo the archive carries per club and per match.

Three facts about the archive shape everything here, all measured 2026-09-02
and recorded in the W4 plan's Appendix A.

**There are two folder layouts, not one.** 2025-2026 and 2026-2027 publish
``data/<season>/By Gameweek/GW<n>/<table>.csv``; 2024-2025 publishes
``data/<season>/<table>/GW<n>/<table>.csv`` and hides its ``teams.csv`` a
folder deeper. So paths are **enumerated from the recursive git tree**, keyed
on basename and season folder, rather than built from a template. A template
would have to be edited every time the publisher reorganises; this does not.

**``By Gameweek`` already contains every tournament.** GW2 of 2026-27 holds
``prem`` and ``efl-cup`` rows in one file. Walking ``By Tournament`` as well
would count a cup tie twice, so it is never walked — which is also why this
module does not replace ``cups.py``: that one reads ``By Tournament``
``matches.csv`` for seasons this one may not cover, and the two parquets are
independent.

**There is no ClubElo file.** Elo is a column on ``teams.csv`` and a pair of
columns on every fixture row. ``elo.parquet`` is derived from both, and for a
season the publisher has not yet filled in — 2026-27, today — it is
legitimately empty. An empty Elo table is a fact about the archive, not a
failure of this collector, and the health line says which.

# v12 W4 §5.1 (specs/2026-09-01-gaffer-v12-program-design.md)
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pandas as pd

from gaffer.data import store
from gaffer.data.cups import (CUPS_RAW_BASE, CUPS_TREE_URL, _cached_get,
                              _http, repo_season)

__all__ = ["CI_CACHE", "SEASON_TABLES", "ci_paths_from_tree", "repo_season"]

CI_CACHE = Path("data/raw/core_insights")
"""Where fetched CSVs are cached. Same contract as ``cups.CUPS_CACHE``: a file
on disk is never re-fetched, so a killed run costs only what it had not
reached. A *finished* gameweek's files never change; an unfinished one's do,
and re-collecting those means deleting their cache entry — the cache is
deliberately dumber than a staleness rule it would have to get right."""

SEASON_TABLES = ("players", "teams", "fixtures", "playermatchstats")
"""The keys every bundle answers, present or absent. ``players`` and ``teams``
are one path or ``None``; ``fixtures`` and ``playermatchstats`` are
``{gw: path}`` and may be empty."""

_GW_RE = re.compile(r"^GW(\d+)$")


def _gw_of(part: str) -> int | None:
    """``"GW10"`` -> ``10``; anything else -> ``None``."""
    hit = _GW_RE.match(part)
    return int(hit.group(1)) if hit else None


def _empty_bundle() -> dict:
    return {"players": None, "teams": None, "fixtures": {},
            "playermatchstats": {}}


def ci_paths_from_tree(tree: dict, seasons: list[str]) -> dict[str, dict]:
    """``{fpl season: bundle}`` from one recursive git-trees payload.

    Layout-agnostic by construction: a path is claimed by what its *basename*
    is and which season folder it sits under, never by how deep it is. That is
    what lets 2024-2025's ``playermatchstats/GW1/playermatchstats.csv`` and
    2025-2026's ``By Gameweek/GW1/playermatchstats.csv`` land in the same slot
    with no branch.

    ``By Tournament`` is skipped outright (see the module docstring), and a
    gameweek that publishes both ``fixtures.csv`` and ``matches.csv`` resolves
    to ``fixtures.csv`` — they are the same bytes in the live archive, and
    picking one deterministically beats depending on the order the tree
    happened to list them in.

    ``players.csv`` and ``teams.csv`` are **the shallowest one wins**, not the
    first one seen. The archive publishes both at the season root *and* inside
    every ``By Gameweek/GW<n>`` folder, and git lists ``By Gameweek`` before
    ``players.csv``, so "first seen" would key an entire season off GW1's
    snapshot — an element map missing every player who signed after August.

    An empty or unreachable tree yields one empty bundle per requested season
    rather than raising: a collector that dies because GitHub is down is a
    collector that gets uninstalled.
    """
    folders = {repo_season(s): s for s in seasons}
    out: dict[str, dict] = {s: _empty_bundle() for s in seasons}
    depth: dict[tuple[str, str], int] = {}
    # ``matches.csv`` is only ever taken where no ``fixtures.csv`` shares the
    # folder, so the two passes cannot race: fixtures are claimed first.
    fallbacks: list[tuple[str, int, str]] = []
    for node in (tree or {}).get("tree", []):
        path = str(node.get("path") or "")
        parts = path.split("/")
        if len(parts) < 3 or parts[0] != "data":
            continue
        season = folders.get(parts[1])
        if season is None or "By Tournament" in parts:
            continue
        name = parts[-1]
        bundle = out[season]
        if name in ("players.csv", "teams.csv"):
            key = name[:-4]
            if depth.get((season, key), 1 << 30) > len(parts):
                bundle[key] = path
                depth[(season, key)] = len(parts)
            continue
        gw = _gw_of(parts[-2]) if len(parts) >= 3 else None
        if gw is None:
            continue
        if name == "playermatchstats.csv":
            bundle["playermatchstats"][gw] = path
        elif name == "fixtures.csv":
            bundle["fixtures"][gw] = path
        elif name == "matches.csv":
            fallbacks.append((season, gw, path))
    for season, gw, path in fallbacks:
        out[season]["fixtures"].setdefault(gw, path)
    return out


def fetch_tree(client: httpx.Client | None = None) -> dict:
    """The repository's recursive git tree, or ``{}`` when it is unreachable.

    One request answers what would otherwise be a listing per season per
    table. ``{}`` is the documented degradation and every caller treats it as
    "the archive published nothing", never as an error.
    """
    http = _http(client)
    try:
        return http.get(CUPS_TREE_URL).json()
    except (httpx.HTTPError, ValueError) as exc:
        print(f"core-insights: tree listing unavailable ({exc})")
        return {}


def fetch_csv(path: str, http: httpx.Client,
              cache_dir: Path | str = CI_CACHE) -> str | None:
    """One archive path -> its text, cached forever under ``cache_dir``.

    ``None`` with a printed line on a 404 or a dead connection: a run spanning
    three seasons and a hundred gameweeks must not die on one missing folder.
    """
    return _cached_get(http, f"{CUPS_RAW_BASE}/{path}", Path(cache_dir) / path)


# --- parsers -------------------------------------------------------------

PMS_KEY_COLS = ("player_id", "match_id")
"""Without both of these a player-match row cannot be placed. A file missing
either is dropped whole, because the alternative is inventing a key."""

PMS_STAT_COLS = ("minutes_played", "accurate_crosses",
                 "touches_opposition_box", "final_third_passes",
                 "tackles_won", "interceptions", "blocks", "clearances",
                 "recoveries", "start_min", "finish_min",
                 "defensive_contributions")
"""The columns kept out of the 54-to-64 the archive publishes.

Deliberately a short list. Everything here is either an input to §5.2's
wing-back rule (crosses, box touches, final-third passes, the two minute
bounds) or a component of the CBIT/defcon family (tackles, interceptions,
blocks, clearances, recoveries, and the published ``defensive_contributions``
where the season has it). Shot maps, sprint distances and duel percentages are
left on the floor for the same reason ``cups.py`` leaves cup goals there: they
are not what this collector exists to answer, and a column nobody reads is a
schema nobody can change.

``defensive_contributions`` is absent from the 2024-2025 layout (A3) and is
carried as an all-NaN column there, so one parquet schema serves every season
and a model sees a missing value rather than a missing column."""

CI_PLAYER_COLS = ["season", "season_idx", "gw", "code", "player_id",
                  "match_id"] + list(PMS_STAT_COLS)

CI_FIXTURE_COLS = ["season", "season_idx", "gw", "tournament", "match_id",
                   "kickoff", "team_code", "opponent_code", "is_home",
                   "finished"]

CI_ELO_COLS = ["season", "season_idx", "gw", "kickoff", "team_code", "elo"]


def _read_csv(text: str) -> pd.DataFrame:
    """One CSV blob -> a frame, or an empty one. Never raises.

    A truncated or non-CSV body is a fetch that went wrong, and one bad file
    must cost one file.
    """
    import io

    try:
        return pd.read_csv(io.StringIO(text or ""))
    except Exception as exc:  # noqa: BLE001 — one bad file is not the run
        print(f"core-insights: unreadable CSV ({exc})")
        return pd.DataFrame()


def player_code_map(players_csv: str) -> dict[int, int]:
    """``{season element id: stable FPL code}`` from the archive's own file.

    The archive ships the map we would otherwise have to rebuild by name:
    ``players.csv`` is ``player_code,player_id,…`` and ``player_code`` is
    exactly gaffer's ``code``. That is why nothing in this module does name
    matching, and why the element-id season guard is free — the map is read
    per season folder and never spans two.
    """
    df = _read_csv(players_csv)
    if df.empty or not {"player_id", "player_code"}.issubset(df.columns):
        return {}
    ids = pd.to_numeric(df["player_id"], errors="coerce")
    codes = pd.to_numeric(df["player_code"], errors="coerce")
    return {int(i): int(c) for i, c in zip(ids, codes)
            if pd.notna(i) and pd.notna(c)}


def player_match_rows(pms_csv: str, season: str, season_idx: int, gw: int,
                      codes: dict[int, int]) -> pd.DataFrame:
    """One ``playermatchstats.csv`` -> ``CI_PLAYER_COLS``.

    Three drift behaviours, one per kind of drift, and they are different on
    purpose:

    * an **unknown column** is ignored — the archive adds metrics, and a
      collector that fell over on a new one would break every time the
      publisher improved it;
    * a **missing optional column** becomes all-NaN with a printed line, so
      the parquet schema is constant across seasons and a model sees a missing
      value instead of a missing column (A3's ``defensive_contributions``);
    * a **missing key column** drops the file with a printed line, because a
      row that cannot be keyed cannot be joined and a guessed key is worse
      than no row.

    An element the season's map does not know drops rather than carrying a
    null ``code``: pandas merges null keys as equal, and one NaN-keyed row is
    how a whole club's stats end up on one player.
    """
    empty = pd.DataFrame(columns=CI_PLAYER_COLS)
    df = _read_csv(pms_csv)
    if df.empty:
        return empty
    missing_keys = [c for c in PMS_KEY_COLS if c not in df.columns]
    if missing_keys:
        print(f"core-insights: {season} gw{gw} playermatchstats has no "
              f"{', '.join(missing_keys)} — file dropped")
        return empty
    out = pd.DataFrame({
        "season": str(season), "season_idx": int(season_idx), "gw": int(gw),
        "player_id": pd.to_numeric(df["player_id"], errors="coerce"),
        "match_id": df["match_id"].astype("string")})
    absent = []
    for col in PMS_STAT_COLS:
        if col in df.columns:
            out[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            out[col] = float("nan")
            absent.append(col)
    if absent:
        print(f"core-insights: {season} gw{gw} playermatchstats does not "
              f"publish {', '.join(absent)} — carried as null")
    out["code"] = out["player_id"].map(
        lambda v: codes.get(int(v)) if pd.notna(v) else None)
    out = out[out["code"].notna() & out["player_id"].notna()]
    if out.empty:
        return empty
    out["code"] = out["code"].astype("int64")
    out["player_id"] = out["player_id"].astype("int64")
    return out[CI_PLAYER_COLS].reset_index(drop=True)


def _fixture_frame(fixtures_csv: str) -> pd.DataFrame | None:
    """Shared preamble of :func:`fixture_rows` and :func:`elo_rows`.

    ``None`` when the file cannot be read as a fixture list at all, which both
    callers turn into their own empty frame.
    """
    df = _read_csv(fixtures_csv)
    if df.empty or "kickoff_time" not in df.columns:
        return None
    if "home_team" not in df.columns or "away_team" not in df.columns:
        return None
    return df


def fixture_rows(fixtures_csv: str, season: str, season_idx: int,
                 gw: int) -> pd.DataFrame:
    """One ``fixtures.csv`` -> one row per *league* club per match.

    Both sides are emitted independently, ``cups.py::cup_match_rows``' rule
    and for its reason: a tie between a Premier League club and an EFL one is
    a fixture for exactly one of them, and the file writes a blank code for
    the other.

    **Unplayed matches are kept.** That is the whole difference between this
    table and the withdrawn cup-archive congestion arm: the archive publishes
    a fixture's kickoff time weeks before it is played (A2d), so a count of
    fixtures in the seven days before a deadline is available *at prediction
    time*. A row with no kickoff time has not been scheduled and carries
    nothing to count, so it drops.
    """
    empty = pd.DataFrame(columns=CI_FIXTURE_COLS)
    df = _fixture_frame(fixtures_csv)
    if df is None:
        print(f"core-insights: {season} gw{gw} fixtures has no kickoff_time "
              f"or no team columns — file dropped")
        return empty
    kickoff = pd.to_datetime(df["kickoff_time"], errors="coerce", utc=True)
    tournament = (df["tournament"].astype("string")
                  if "tournament" in df.columns
                  else pd.Series("", index=df.index, dtype="string"))
    match_id = (df["match_id"].astype("string") if "match_id" in df.columns
                else pd.Series("", index=df.index, dtype="string"))
    finished = (df["finished"].astype("string").str.lower().eq("true")
                if "finished" in df.columns
                else pd.Series(False, index=df.index))
    home = pd.to_numeric(df["home_team"], errors="coerce")
    away = pd.to_numeric(df["away_team"], errors="coerce")
    parts = []
    for side, other, is_home in ((home, away, True), (away, home, False)):
        parts.append(pd.DataFrame({
            "season": str(season), "season_idx": int(season_idx),
            "gw": int(gw), "tournament": tournament.values,
            "match_id": match_id.values, "kickoff": kickoff.values,
            "team_code": side.values, "opponent_code": other.values,
            "is_home": bool(is_home), "finished": finished.values}))
    out = pd.concat(parts, ignore_index=True)
    out = out[out["team_code"].notna() & out["kickoff"].notna()]
    if out.empty:
        return empty
    out["team_code"] = out["team_code"].astype("int64")
    return out[CI_FIXTURE_COLS].reset_index(drop=True)


def elo_rows(fixtures_csv: str, season: str, season_idx: int,
             gw: int) -> pd.DataFrame:
    """One ``fixtures.csv`` -> one Elo reading per club per match.

    The archive has no ClubElo file (see the module docstring): the readings
    live on the fixture rows as ``home_team_elo`` / ``away_team_elo``. A row
    whose Elo is blank yields nothing, which is why 2026-27 comes back empty
    today — the publisher has not filled the column in for the new season.
    Empty is the honest answer, and the health line says so rather than
    borrowing last season's number.
    """
    empty = pd.DataFrame(columns=CI_ELO_COLS)
    df = _fixture_frame(fixtures_csv)
    if df is None:
        return empty
    if not {"home_team_elo", "away_team_elo"}.issubset(df.columns):
        return empty
    kickoff = pd.to_datetime(df["kickoff_time"], errors="coerce", utc=True)
    parts = []
    for team_col, elo_col in (("home_team", "home_team_elo"),
                              ("away_team", "away_team_elo")):
        parts.append(pd.DataFrame({
            "season": str(season), "season_idx": int(season_idx),
            "gw": int(gw), "kickoff": kickoff.values,
            "team_code": pd.to_numeric(df[team_col], errors="coerce").values,
            "elo": pd.to_numeric(df[elo_col], errors="coerce").values}))
    out = pd.concat(parts, ignore_index=True)
    out = out[out["team_code"].notna() & out["elo"].notna()
              & out["kickoff"].notna()]
    if out.empty:
        return empty
    out["team_code"] = out["team_code"].astype("int64")
    return out[CI_ELO_COLS].reset_index(drop=True)


# --- the collector and its readers ---------------------------------------

CI_TABLES = {"players": CI_PLAYER_COLS, "fixtures": CI_FIXTURE_COLS,
             "elo": CI_ELO_COLS}
"""``table -> its column contract``. The three names spec §5.1 asks for."""


def ci_path(season: str, table: str) -> str:
    """``store``-relative path of one season's one table.

    Season-partitioned rather than one growing file, and that partition *is*
    the season guard: an element id means nothing without a season, and a
    reader that has to remember to filter is a reader that eventually forgets.
    ``load_core_insights`` takes the season as its first positional argument
    for the same reason.
    """
    return f"core_insights/{season}/{table}.parquet"


def load_core_insights(season: str, table: str) -> pd.DataFrame:
    """One season's one table, or an empty frame with the right columns.

    Never raises and never falls back to another season. "This machine has not
    collected 2024-25" and "2024-25 had no rows" are both an empty frame here,
    and the difference is recoverable from :func:`season_table_stats`, which
    is what the health line reads.
    """
    cols = CI_TABLES.get(table)
    if cols is None:
        raise ValueError(f"unknown core-insights table {table!r}")
    empty = pd.DataFrame(columns=cols)
    rel = ci_path(season, table)
    if not store.exists(rel):
        return empty
    try:
        frame = store.load(rel)
    except Exception as exc:  # noqa: BLE001 — a torn parquet is a missing one
        print(f"core-insights: {rel} unreadable ({exc})")
        return empty
    if "season" not in frame.columns:
        return empty
    # Belt and braces on top of the directory partition: a hand-copied file
    # from another machine must not smuggle another season's element ids in.
    return frame[frame["season"].astype(str) == str(season)]


def season_table_stats(season: str) -> dict[str, dict]:
    """``{table: {"rows": n, "latest": "YYYY-MM-DD" | None}}`` for the health
    line.

    ``rows`` of 0 with ``latest`` of ``None`` is what a machine that has never
    run the collector shows, and it is also what a season the archive publishes
    empty shows. The health line renders "never collected" for the first only
    because it can see the file is absent; both are honest, neither is a zero
    dressed as a measurement.
    """
    out: dict[str, dict] = {}
    for table in CI_TABLES:
        frame = load_core_insights(season, table)
        latest = None
        if not frame.empty:
            if "kickoff" in frame.columns:
                stamps = pd.to_datetime(frame["kickoff"], errors="coerce",
                                        utc=True).dropna()
                if not stamps.empty:
                    latest = str(stamps.max().date())
            elif "gw" in frame.columns:
                latest = f"GW{int(pd.to_numeric(frame['gw']).max())}"
        out[table] = {"rows": int(len(frame)), "latest": latest}
    return out


def download_core_insights(seasons: list[str],
                           season_indexes: dict[str, int],
                           *, tree: dict | None = None,
                           client: httpx.Client | None = None,
                           cache_dir: Path | str = CI_CACHE
                           ) -> dict[str, dict[str, int]]:
    """Collect every requested season -> ``data/core_insights/<season>/``.

    One tree listing, then one cached GET per file. Returns
    ``{season: {table: rows written}}``, which is what the CLI prints.

    A season the archive does not publish writes three empty tables rather
    than nothing at all: "we looked and there was nothing" and "we never
    looked" are different states, the health line distinguishes them by the
    file's existence, and only the first is a state a re-run will not change.

    An unreachable archive writes *nothing* — no empty tables, no truncation
    of what a previous run collected. A network blip must not delete a
    season's data, which is why the write is skipped entirely when the tree
    came back empty.
    """
    http = _http(client)
    tree = fetch_tree(http) if tree is None else tree
    bundles = ci_paths_from_tree(tree, seasons)
    out: dict[str, dict[str, int]] = {}
    for season in seasons:
        bundle = bundles[season]
        idx = int(season_indexes.get(season, 0))
        reachable = bool(bundle["players"] or bundle["teams"]
                         or bundle["fixtures"] or bundle["playermatchstats"])
        if not reachable:
            print(f"core-insights: {season} — the archive published nothing "
                  f"reachable; leaving any previous collection alone")
            out[season] = {t: 0 for t in CI_TABLES}
            continue
        codes: dict[int, int] = {}
        if bundle["players"]:
            text = fetch_csv(bundle["players"], http, cache_dir)
            codes = player_code_map(text or "")
        if not codes:
            print(f"core-insights: {season} has no element map — player rows "
                  f"cannot be joined to a code and are skipped")
        players, fixtures, elos = [], [], []
        for gw in sorted(bundle["playermatchstats"]):
            if not codes:
                break
            text = fetch_csv(bundle["playermatchstats"][gw], http, cache_dir)
            if not text:
                continue
            players.append(player_match_rows(text, season, idx, gw, codes))
        for gw in sorted(bundle["fixtures"]):
            text = fetch_csv(bundle["fixtures"][gw], http, cache_dir)
            if not text:
                continue
            fixtures.append(fixture_rows(text, season, idx, gw))
            elos.append(elo_rows(text, season, idx, gw))
        written: dict[str, int] = {}
        for table, frames in (("players", players), ("fixtures", fixtures),
                              ("elo", elos)):
            cols = CI_TABLES[table]
            kept = [f for f in frames if not f.empty]
            frame = (pd.concat(kept, ignore_index=True)[cols] if kept
                     else pd.DataFrame(columns=cols))
            store.save(frame, ci_path(season, table))
            written[table] = int(len(frame))
        print(f"core-insights: {season} — "
              + ", ".join(f"{n} {t}" for t, n in written.items()))
        out[season] = written
    return out
