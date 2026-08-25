"""Historical closing match odds from football-data.co.uk.

The-odds-api prices only *upcoming* fixtures, so nothing in the live feed can
ever be backfilled: there is no historical row anywhere in this codebase that
carries what the market thought before a match that has already been played.
Without one, the odds blend weight can only be guessed, and a Dixon-Coles fit
can never be scored against the market it is supposed to complement.
football-data.co.uk publishes exactly that record — one CSV per season, closing
averages across books — free, stable, and going back further than our history.

Finished seasons never change, so their files are cached permanently; the
current season's file grows weekly and is re-downloaded on every refresh.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pandas as pd

from gaffer.data import store
from gaffer.data.odds import NEUTRAL_P_OVER25, devig, shin_devig
from gaffer.errors import GafferError

BASE = "https://www.football-data.co.uk/mmz4281"
MATCH_ODDS_PATH = "history/match_odds.parquet"
CACHE_DIR = Path("data/raw/football-data")

PRICE_TRIPLES = [
    ("AvgCH", "AvgCD", "AvgCA"),    # closing average across books
    ("AvgH", "AvgD", "AvgA"),       # opening/period average
    ("B365CH", "B365CD", "B365CA"),  # single-book closing
    ("B365H", "B365D", "B365A"),    # single-book
]
"""1X2 column triples in preference order, closing averages first.

Closing prices are the sharpest number the market ever produces, and an
average across books strips one book's idiosyncratic lean. The chain exists
because coverage varies by season: the ``C`` (closing) columns only start in
2019-20, and a handful of early files carry Bet365 alone.
"""

TOTALS_PAIRS = [
    ("AvgC>2.5", "AvgC<2.5"),
    ("Avg>2.5", "Avg<2.5"),
    ("B365C>2.5", "B365C<2.5"),
    ("B365>2.5", "B365<2.5"),
]
"""Over/Under 2.5 pairs, same preference order and same reason."""

OUT_COLS = ["season", "season_idx", "date", "home_name", "away_name",
            "p_home", "p_draw", "p_away", "p_over25"]

# football-data uses its own short club names, which are neither The Odds
# API's official names nor FPL's bootstrap names. Values are FPL bootstrap
# names, so this table and TEAM_ALIASES land in the same vocabulary — which
# also scopes it, like TEAM_ALIASES, to the clubs the configured seasons can
# actually contain. Backfilling further back means adding the older clubs to
# both tables; resolve_fd_team says so by name when it hits one.
FOOTBALL_DATA_ALIASES = {
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
    "Man City": "Man City",
    "Man United": "Man Utd",
    "Newcastle": "Newcastle",
    "Nott'm Forest": "Nott'm Forest",
    "Sheffield United": "Sheffield Utd",
    "Southampton": "Southampton",
    "Sunderland": "Sunderland",
    "Tottenham": "Spurs",
    "West Ham": "West Ham",
    "Wolves": "Wolves",
}

_FPL_NAMES = set(FOOTBALL_DATA_ALIASES.values())


def resolve_fd_team(name: str) -> str:
    """football-data club name -> FPL bootstrap name.

    Same raise-on-unknown discipline as
    :func:`gaffer.data.odds.resolve_team`: guessing would attach one club's
    closing odds to another, and a silently wrong prior is worse than none.
    """
    if name in FOOTBALL_DATA_ALIASES:
        return FOOTBALL_DATA_ALIASES[name]
    if name in _FPL_NAMES:
        return name
    raise GafferError(
        f"unknown team name in the football-data file: {name!r} — add it to "
        "FOOTBALL_DATA_ALIASES in gaffer/data/match_odds.py")


def _first_complete(df: pd.DataFrame,
                    groups: list[tuple[str, ...]]) -> tuple[str, ...] | None:
    """First column group present *and* fully populated on every kept row.

    A half-filled preferred triple is not a market: taking it would devig two
    real prices against a NaN and produce a probability that looks fine and
    means nothing.
    """
    for group in groups:
        if not all(c in df.columns for c in group):
            continue
        block = df[list(group)].apply(pd.to_numeric, errors="coerce")
        if block.notna().all().all() and (block > 1.0).all().all():
            return group
    return None


def parse_football_data(raw: pd.DataFrame, season: str,
                        season_idx: int) -> pd.DataFrame:
    """One season's football-data CSV -> devigged match probabilities.

    Output ``[season, season_idx, date, home_name, away_name, p_home, p_draw,
    p_away, p_over25]``, one row per match, team names already in FPL's
    vocabulary and probabilities already devigged — the 1X2 triple by
    :func:`~gaffer.data.odds.shin_devig`, the totals pair by proportional
    :func:`~gaffer.data.odds.devig`.

    A file with no usable 1X2 triple yields an empty frame with the right
    columns rather than an exception: some early seasons in the archive are
    genuinely price-free, and one bad season must not fail a backfill.
    """
    df = raw[raw["HomeTeam"].notna() & raw["AwayTeam"].notna()].copy()
    df = df.reset_index(drop=True)
    empty = pd.DataFrame(columns=OUT_COLS)
    if df.empty:
        return empty
    triple = _first_complete(df, PRICE_TRIPLES)
    if triple is None:
        return empty

    prices = df[list(triple)].apply(pd.to_numeric, errors="coerce")
    devigged = [shin_devig([float(h), float(d), float(a)])
                for h, d, a in zip(prices[triple[0]], prices[triple[1]],
                                   prices[triple[2]])]
    pair = _first_complete(df, TOTALS_PAIRS)
    if pair is None:
        p_over = [NEUTRAL_P_OVER25] * len(df)
    else:
        totals = df[list(pair)].apply(pd.to_numeric, errors="coerce")
        p_over = [devig([float(o), float(u)])[0]
                  for o, u in zip(totals[pair[0]], totals[pair[1]])]

    # dayfirst covers both dd/mm/yy and dd/mm/yyyy, which the archive mixes
    # across seasons; a date is all we join on, so the time of day is noise.
    dates = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    out = pd.DataFrame({
        "season": season,
        "season_idx": int(season_idx),
        "date": dates.dt.date,
        "home_name": [resolve_fd_team(n) for n in df["HomeTeam"]],
        "away_name": [resolve_fd_team(n) for n in df["AwayTeam"]],
        "p_home": [p[0] for p in devigged],
        "p_draw": [p[1] for p in devigged],
        "p_away": [p[2] for p in devigged],
        "p_over25": p_over,
    })
    return out[out["date"].notna()].reset_index(drop=True)[OUT_COLS]


def season_slug(season: str) -> str:
    """``"2024-25"`` -> ``"2425"``, football-data's directory name."""
    return f"{season[2:4]}{season[5:7]}"


def download_season(season: str, cache_dir: Path = CACHE_DIR,
                    client: httpx.Client | None = None,
                    refresh: bool = False) -> pd.DataFrame | None:
    """One season's ``E0.csv``, cached under ``cache_dir/<season>/E0.csv``.

    A finished season's file never changes, so it is fetched once and read
    from disk forever after. ``refresh=True`` is for the running season, whose
    file grows every week. A season the archive does not carry (a 404, or a
    future season) returns ``None`` — a backfill spanning five seasons must
    not die on the one that is missing.
    """
    dest = Path(cache_dir) / season / "E0.csv"
    if refresh or not dest.exists():
        http = client if client is not None else httpx.Client(
            timeout=60, follow_redirects=True)
        try:
            resp = http.get(f"{BASE}/{season_slug(season)}/E0.csv")
            resp.raise_for_status()
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            print(f"football-data: no file for {season} ({exc})")
            return None
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
    try:
        return pd.read_csv(dest)
    except UnicodeDecodeError:      # a few seasons are latin-1
        return pd.read_csv(dest, encoding="latin-1")


JOIN_COLS = ["season_idx", "gw", "kickoff_time", "home_code", "away_code",
             "p_home", "p_draw", "p_away", "p_over25"]

FPL_RENAMES = {
    # canonical current bootstrap name -> names earlier season bootstraps used
    "Ipswich Town": ["Ipswich"],
}
"""FPL renames clubs between seasons, and our alias tables target the CURRENT
name.

``FOOTBALL_DATA_ALIASES`` and ``odds.TEAM_ALIASES`` are both written against
the live bootstrap's vocabulary, but a historical join looks a code up in the
*old* season's ``{name: code}`` table, where the club may still be spelled the
way it was then. Without this bridge every one of that club's fixtures misses
its code and drops silently as "unmatched"."""


def _code_for(name: str, name_to_code: dict[str, int]) -> int | float:
    """A season's code for a club, trying its earlier names before giving up."""
    if name in name_to_code:
        return name_to_code[name]
    for old in FPL_RENAMES.get(name, ()):
        if old in name_to_code:
            return name_to_code[old]
    return float("nan")


def join_to_fixtures(parsed: pd.DataFrame, fixtures: pd.DataFrame,
                     name_to_code: dict[str, int]
                     ) -> tuple[pd.DataFrame, dict[str, int]]:
    """Attach ``(season_idx, gw, kickoff_time)`` to each priced match.

    Keyed on ``(home_code, away_code, UK kickoff date)``. Date plus both
    codes is unique even in a double gameweek — the same pair does not meet
    twice in a week — where ``(gw, home_code)`` alone would not be. The date
    is compared in *UK local time* because that is the clock football-data
    stamps its files with; a 23:30 UTC kickoff is the next day in neither
    system's opinion but the previous day in ours if the conversion is
    skipped.

    Returns the joined frame and a count report. Unmatched rows are dropped
    and reported, never fatal: cup fixtures, postponements and clubs missing
    from a season's bootstrap all land here legitimately.
    """
    fx = fixtures.copy()
    kt = pd.to_datetime(fx["kickoff_time"], utc=True, format="mixed")
    fx["_date"] = kt.dt.tz_convert("Europe/London").dt.date
    left = parsed.copy()
    left["home_code"] = [_code_for(n, name_to_code) for n in left["home_name"]]
    left["away_code"] = [_code_for(n, name_to_code) for n in left["away_name"]]
    left["_date"] = left["date"]
    merged = left.merge(
        fx[["season_idx", "gw", "kickoff_time", "home_code", "away_code",
            "_date"]],
        on=["home_code", "away_code", "_date"], how="left",
        suffixes=("", "_fx"))
    ok = merged["gw"].notna()
    report = {"rows": int(len(left)), "matched": int(ok.sum()),
              "unmatched": int((~ok).sum())}
    out = merged[ok].copy()
    out["season_idx"] = out["season_idx"].astype(int)
    out["gw"] = out["gw"].astype(int)
    out["home_code"] = out["home_code"].astype(int)
    out["away_code"] = out["away_code"].astype(int)
    return out[JOIN_COLS].reset_index(drop=True), report


def build_match_odds(seasons: list[str], fixtures: pd.DataFrame,
                     names_by_season: dict[str, dict[str, int]],
                     cache_dir: Path = CACHE_DIR,
                     client: httpx.Client | None = None,
                     season_indexes: dict[str, int] | None = None,
                     current_season: str | None = None) -> pd.DataFrame:
    """Every season's closing odds -> ``data/history/match_odds.parquet``.

    ``names_by_season`` maps a season to its ``{bootstrap name: code}`` table,
    because a code is only meaningful next to the season whose bootstrap
    produced it. ``current_season``, if given and present in ``seasons``, is
    the only file re-downloaded.

    A season with no archive file, no usable prices or no name table is
    skipped with a printed line; the parquet is still written from what did
    resolve, and an entirely empty result writes an empty frame with the right
    columns so downstream ``store.load`` never sees a missing schema.
    """
    indexes = season_indexes or {s: i for i, s in enumerate(seasons)}
    frames, reports = [], {}
    for season in seasons:
        raw = download_season(season, cache_dir=cache_dir, client=client,
                              refresh=season == current_season)
        if raw is None:
            continue
        parsed = parse_football_data(raw, season, indexes[season])
        if parsed.empty:
            print(f"football-data: no usable price columns for {season}")
            continue
        names = names_by_season.get(season)
        if not names:
            print(f"football-data: no team name table for {season}")
            continue
        joined, report = join_to_fixtures(parsed, fixtures, names)
        reports[season] = report
        frames.append(joined)
    out = (pd.concat(frames, ignore_index=True) if frames
           else pd.DataFrame(columns=JOIN_COLS))
    for season, rep in reports.items():
        print(f"football-data {season}: {rep['matched']}/{rep['rows']} "
              f"matched, {rep['unmatched']} unmatched")
    store.save(out, MATCH_ODDS_PATH)
    return out
