"""The Odds API client for bookmaker prices on EPL fixtures.

Odds are an optional signal: with no API key configured the client stays
silent (returns None) rather than raising, so callers can treat bookmaker
features as best-effort.
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

from gaffer.data import store
from gaffer.errors import GafferError

BASE = "https://api.the-odds-api.com/v4"


class OddsClient:
    def __init__(self, api_key: str, client: httpx.Client | None = None,
                 raw_dir: Path | str | None = None,
                 retries: int = 3, backoff: float = 2.0):
        self.api_key = api_key or ""
        self.retries = retries
        self.backoff = backoff
        self._raw_dir = Path(raw_dir) if raw_dir is not None else None
        self._http = client if client is not None else httpx.Client(timeout=30)

    @property
    def raw_dir(self) -> Path:
        # Resolved lazily so tests can monkeypatch store.DATA_DIR.
        return self._raw_dir if self._raw_dir is not None else store.DATA_DIR / "raw"

    def _get(self, path: str, params: dict, snapshot: str | None = None):
        last_exc = None
        for attempt in range(self.retries):
            try:
                resp = self._http.get(f"{BASE}/{path}", params=params)
                resp.raise_for_status()
                data = resp.json()
                if snapshot:
                    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                    self.raw_dir.mkdir(parents=True, exist_ok=True)
                    (self.raw_dir / f"{snapshot}-{ts}.json").write_text(
                        json.dumps(data))
                return data
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                # Client errors (except rate limiting) will not fix themselves:
                # fail fast rather than burning the retry budget on backoff.
                if isinstance(exc, httpx.HTTPStatusError):
                    status = exc.response.status_code
                    if 400 <= status < 500 and status != 429:
                        raise
                last_exc = exc
                if attempt < self.retries - 1:
                    time.sleep(self.backoff ** attempt if self.backoff else 0)
        raise last_exc

    def get_epl_odds(self) -> list | None:
        """Match winner and over/under odds for upcoming EPL fixtures.

        Returns None when no API key is configured (no request is made).
        """
        if not self.api_key:
            return None
        return self._get(
            "sports/soccer_epl/odds",
            params={"regions": "eu", "markets": "h2h,totals",
                    "apiKey": self.api_key},
            snapshot="odds",
        )


GOAL_CAP = 10
GRID = [round(0.2 + 0.05 * i, 2) for i in range(int((4.0 - 0.2) / 0.05) + 1)]


def devig(prices: list[float]) -> list[float]:
    """Proportionally normalize implied probabilities (strip the vig)."""
    implied = [1.0 / p for p in prices]
    s = sum(implied)
    return [x / s for x in implied]


def invert_odds(p_home: float, p_draw: float, p_away: float,
                p_over25: float) -> tuple[float, float]:
    """Least-squares grid search for independent-Poisson (mu_h, mu_a)."""
    from math import exp, factorial

    def pmf(mu):
        return [exp(-mu) * mu**k / factorial(k) for k in range(GOAL_CAP + 1)]

    pmfs = {mu: pmf(mu) for mu in GRID}
    best, best_err = (1.3, 1.3), float("inf")
    for mh in GRID:
        ph_ = pmfs[mh]
        for ma in GRID:
            pa_ = pmfs[ma]
            win = draw = over = 0.0
            for h in range(GOAL_CAP + 1):
                for a in range(GOAL_CAP + 1):
                    pr = ph_[h] * pa_[a]
                    if h > a:
                        win += pr
                    elif h == a:
                        draw += pr
                    if h + a >= 3:
                        over += pr
            err = ((win - p_home) ** 2 + (draw - p_draw) ** 2
                   + 0.5 * (over - p_over25) ** 2)
            if err < best_err:
                best_err, best = err, (mh, ma)
    return best


# The Odds API uses long official club names; the FPL bootstrap uses short
# ones. Season-agnostic on purpose: recently-relegated clubs stay in the table
# so a promotion does not need a code change. Keys that already match an FPL
# name are listed too, so a bookmaker that shortens a name still resolves.
TEAM_ALIASES = {
    "Arsenal": "Arsenal",
    "Aston Villa": "Aston Villa",
    "AFC Bournemouth": "Bournemouth",
    "Bournemouth": "Bournemouth",
    "Brentford": "Brentford",
    "Brighton and Hove Albion": "Brighton",
    "Brighton & Hove Albion": "Brighton",
    "Brighton": "Brighton",
    "Burnley": "Burnley",
    "Chelsea": "Chelsea",
    "Coventry City": "Coventry City",
    "Coventry": "Coventry City",
    "Crystal Palace": "Crystal Palace",
    "Everton": "Everton",
    "Fulham": "Fulham",
    "Hull City": "Hull City",
    "Hull": "Hull City",
    "Ipswich Town": "Ipswich Town",
    "Ipswich": "Ipswich Town",
    "Leeds United": "Leeds",
    "Leeds": "Leeds",
    "Leicester City": "Leicester",
    "Leicester": "Leicester",
    "Liverpool": "Liverpool",
    "Luton Town": "Luton",
    "Luton": "Luton",
    "Manchester City": "Man City",
    "Manchester United": "Man Utd",
    "Newcastle United": "Newcastle",
    "Nottingham Forest": "Nott'm Forest",
    "Sheffield United": "Sheffield Utd",
    "Southampton": "Southampton",
    "Sunderland": "Sunderland",
    "Tottenham Hotspur": "Spurs",
    "West Ham United": "West Ham",
    "Wolverhampton Wanderers": "Wolves",
    "Wolves": "Wolves",
}

# Every FPL-side name the table can produce, so an already-short name passed
# in resolves to itself rather than falling through to the error.
_FPL_NAMES = set(TEAM_ALIASES.values())

NEUTRAL_P_OVER25 = 0.55
"""Stand-in when a fixture carries no totals market at all — roughly the
long-run EPL rate of 3+ goals, so the inversion leans on h2h alone."""


def resolve_team(name: str) -> str:
    """The Odds API club name -> FPL bootstrap name.

    Raises :class:`GafferError` on an unknown name rather than guessing: a
    silently mismatched club would attach one team's odds to another, which
    is far worse than losing the odds signal for a week. ``run_advise``
    catches this so the weekly run survives a bookmaker renaming a club.
    """
    if name in TEAM_ALIASES:
        return TEAM_ALIASES[name]
    if name in _FPL_NAMES:
        return name
    raise GafferError(
        f"unknown team name from the odds feed: {name!r} — add it to "
        "TEAM_ALIASES in gaffer/data/odds.py")


ODDS_FRAME_COLS = ["team_code", "opp_code", "gw", "odds_e_goals_for",
                   "odds_e_goals_against"]


def _gw_windows(events: pd.DataFrame) -> list[tuple[pd.Timestamp, pd.Timestamp, int]]:
    """[(start, end, gw)] half-open deadline windows, ordered by gw."""
    ev = events[["gw", "deadline_time"]].copy()
    ev["deadline_time"] = pd.to_datetime(ev["deadline_time"], utc=True,
                                         format="mixed")
    ev = ev.sort_values("gw").reset_index(drop=True)
    starts = ev["deadline_time"].tolist()
    ends = starts[1:] + [pd.Timestamp.max.tz_localize("UTC")]
    return list(zip(starts, ends, ev["gw"].astype(int).tolist()))


def _market(bookmaker: dict, key: str) -> dict | None:
    for m in bookmaker.get("markets", []):
        if m.get("key") == key:
            return m
    return None


def _p_over25(bookmaker: dict) -> float:
    """De-vigged P(3+ goals) from the totals market.

    Prefers the 2.5 line; if the bookmaker only quotes other points (a 3.0
    line on a lopsided fixture, say) the closest point is used, which biases
    the total slightly but keeps the fixture. With no totals market at all,
    ``NEUTRAL_P_OVER25``.
    """
    market = _market(bookmaker, "totals")
    if market is None:
        return NEUTRAL_P_OVER25
    by_point: dict[float, dict[str, float]] = {}
    for o in market.get("outcomes", []):
        point, name = o.get("point"), str(o.get("name", "")).lower()
        if point is None or name not in ("over", "under"):
            continue
        by_point.setdefault(float(point), {})[name] = float(o["price"])
    pairs = {p: v for p, v in by_point.items() if {"over", "under"} <= set(v)}
    if not pairs:
        return NEUTRAL_P_OVER25
    point = min(pairs, key=lambda p: (abs(p - 2.5), p))
    return devig([pairs[point]["over"], pairs[point]["under"]])[0]


def odds_frame(raw_odds: list, teams: pd.DataFrame,
               events: pd.DataFrame) -> pd.DataFrame:
    """Bookmaker odds -> ``[team_code, opp_code, gw, odds_e_goals_for,
    odds_e_goals_against]``, two rows per fixture.

    ``opp_code`` is part of the output, not decoration: in a double gameweek
    one team has two fixtures under the same ``gw``, and the opponent is the
    only thing that tells them apart. Without it the join onto the team-future
    frame either fans out or has to throw one fixture away.

    The **first** bookmaker listed for a fixture is used — The Odds API
    returns them in its own order and averaging across books with different
    market coverage would mix vig structures.

    h2h outcomes are matched by *name* (home team / away team / ``Draw``),
    never by list position, and de-vigged before inversion; the Over/Under
    pair is de-vigged separately (``invert_odds`` validates nothing). The
    resulting (mu_h, mu_a) become goals-for/against on the home row and the
    same pair swapped on the away row.

    A fixture whose ``commence_time`` falls in no gameweek window
    (``deadline_time <= commence_time`` < the next deadline) is skipped —
    it belongs to no gameweek we can join on. So is a fixture missing its
    h2h market. An unmapped club name raises :class:`GafferError`.
    """
    code_of = dict(zip(teams["name"], teams["code"]))
    windows = _gw_windows(events)
    rows = []
    for fixture in raw_odds or []:
        books = fixture.get("bookmakers") or []
        if not books:
            continue
        home_raw, away_raw = fixture["home_team"], fixture["away_team"]
        home, away = resolve_team(home_raw), resolve_team(away_raw)
        if home not in code_of or away not in code_of:
            continue        # not a club in this season's bootstrap

        kickoff = pd.to_datetime(fixture["commence_time"], utc=True,
                                 format="mixed")
        gw = next((g for start, end, g in windows if start <= kickoff < end),
                  None)
        if gw is None:
            continue

        h2h = _market(books[0], "h2h")
        if h2h is None:
            continue
        prices = {str(o.get("name")): float(o["price"])
                  for o in h2h.get("outcomes", [])}
        try:
            triple = [prices[home_raw], prices["Draw"], prices[away_raw]]
        except KeyError:
            continue        # incomplete h2h market
        p_home, p_draw, p_away = devig(triple)
        mu_h, mu_a = invert_odds(p_home, p_draw, p_away, _p_over25(books[0]))

        rows.append({"team_code": code_of[home], "opp_code": code_of[away],
                     "gw": gw,
                     "odds_e_goals_for": mu_h, "odds_e_goals_against": mu_a})
        rows.append({"team_code": code_of[away], "opp_code": code_of[home],
                     "gw": gw,
                     "odds_e_goals_for": mu_a, "odds_e_goals_against": mu_h})
    return pd.DataFrame(rows, columns=ODDS_FRAME_COLS)


def poisson_win_prob(mu_for: float, mu_against: float,
                     max_goals: int = 10) -> float:
    """P(win) under independent Poisson scorelines.

    The same independence assumption :func:`invert_odds` used to recover the
    two means, so the fixture ticker's difficulty and the clean-sheet blend
    are telling the same story about the same fixture.
    """
    def pmf(mu: float, k: int) -> float:
        return math.exp(-mu) * mu ** k / math.factorial(k)

    home = [pmf(max(mu_for, 1e-9), k) for k in range(max_goals + 1)]
    away = [pmf(max(mu_against, 1e-9), k) for k in range(max_goals + 1)]
    return sum(home[h] * sum(away[:h]) for h in range(1, max_goals + 1))
