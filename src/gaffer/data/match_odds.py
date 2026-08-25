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
