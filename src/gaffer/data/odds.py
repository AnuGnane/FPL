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

    def get_player_goalscorer_odds(self, event_ids: list[str]) -> list | None:
        """Anytime-goalscorer prices for the given fixtures, best effort.

        One request per event — the-odds-api has no bulk player-props
        endpoint — so the caller passes only the *next* gameweek's fixtures
        and takes one snapshot per advise run; ten calls a week fits inside
        the free tier's monthly budget.

        Returns ``None`` on a missing key, an exhausted quota (401/402/429) or
        a transport failure, exactly like :meth:`get_epl_odds`: player props
        are the most optional signal in the model and must never be able to
        block a week's advice.
        """
        if not self.api_key:
            return None
        out = []
        for event_id in event_ids:
            try:
                data = self._get(
                    f"sports/soccer_epl/events/{event_id}/odds",
                    params={"regions": "eu", "markets": AGS_MARKET,
                            "oddsFormat": "decimal", "apiKey": self.api_key},
                    snapshot=f"ags-{event_id}")
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                print(f"player props unavailable ({exc})")
                return None
            if data:
                out.append(data)
        return out or None


GOAL_CAP = 10
GRID = [round(0.2 + 0.05 * i, 2) for i in range(int((4.0 - 0.2) / 0.05) + 1)]


def devig(prices: list[float]) -> list[float]:
    """Proportionally normalize implied probabilities (strip the vig)."""
    implied = [1.0 / p for p in prices]
    s = sum(implied)
    return [x / s for x in implied]


SHIN_MAX_Z = 0.4
"""Upper bracket for the insider proportion.

Real books sit well under 0.1; the bracket only has to contain the root, and
z -> 1 is where the closed form is singular.
"""

SHIN_TOL = 1e-13
SHIN_MAX_ITER = 300


def _shin_probs(implied: list[float], booksum: float, z: float) -> list[float]:
    """Shin's implied true probabilities for a given insider proportion."""
    return [(math.sqrt(z * z + 4.0 * (1.0 - z) * pi * pi / booksum) - z)
            / (2.0 * (1.0 - z)) for pi in implied]


def shin_devig(prices: list[float]) -> list[float]:
    """Strip the vig under Shin's insider-trading model, for n outcomes.

    Bookmakers pad longshots more heavily than favourites, because the loss
    they are insuring against is bigger there. :func:`devig` divides that pad
    away uniformly and so systematically under-prices big favourites — which
    in FPL are exactly the clean-sheet and goalscorer bets the model cares
    about (Strumbelj 2014). Shin instead assumes a proportion ``z`` of the
    money is informed and solves for the ``z`` that makes the implied
    probabilities sum to one.

    ``sum(p(z))`` is ``sqrt(booksum)`` at ``z = 0`` and decreases in ``z``, so
    a plain bisection on the bracket finds the root without a derivative. A
    book with no overround (``booksum <= 1``) has no pad to remove and comes
    back as the normalized implied probabilities, and a one-outcome market is
    a certainty.
    """
    implied = [1.0 / p for p in prices]
    booksum = sum(implied)
    if len(implied) < 2 or booksum <= 1.0:
        return [pi / booksum for pi in implied]
    lo, hi = 0.0, SHIN_MAX_Z
    for _ in range(SHIN_MAX_ITER):
        mid = 0.5 * (lo + hi)
        if sum(_shin_probs(implied, booksum, mid)) > 1.0:
            lo = mid
        else:
            hi = mid
        if hi - lo < SHIN_TOL:
            break
    out = _shin_probs(implied, booksum, 0.5 * (lo + hi))
    # The bisection lands within tolerance, not exactly; renormalize so the
    # caller can rely on the sum without carrying the solver's slack.
    total = sum(out)
    return [x / total for x in out]


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
    never by list position, and de-vigged with :func:`shin_devig` before
    inversion; the Over/Under pair keeps proportional :func:`devig` (a
    two-way total carries no favourite-longshot bias worth modelling, and
    ``invert_odds`` validates nothing). The resulting (mu_h, mu_a) become goals-for/against on the home row and the
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
        p_home, p_draw, p_away = shin_devig(triple)
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


AGS_MARKET = "player_goal_scorer_anytime"
AGS_EG_CAP = 2.0
"""Ceiling on odds-implied expected goals *per appearance*.

``lambda / p_play`` divides by a probability, so a fringe player with a
0.05 chance of playing and a long price would otherwise come out at an
absurd per-appearance rate. Nobody in this league is a two-goals-a-game
player; the cap is where the arithmetic stops being a signal.
"""

AGS_FRAME_COLS = ["code", "gw", "team_code", "opp_code", "lambda_ags"]


def next_gw_event_ids(raw_odds: list, events: pd.DataFrame,
                      gw: int) -> list[str]:
    """The-odds-api event ids whose kickoff falls in gameweek ``gw``.

    The free tier is metered per request, so only the gameweek being advised
    is worth spending calls on.
    """
    windows = _gw_windows(events)
    out = []
    for fixture in raw_odds or []:
        kickoff = pd.to_datetime(fixture["commence_time"], utc=True,
                                 format="mixed")
        found = next((g for start, end, g in windows
                      if start <= kickoff < end), None)
        if found == gw and fixture.get("id"):
            out.append(str(fixture["id"]))
    return out


def normalize_ags(prices: dict[str, float], mu: float) -> dict[str, float]:
    """One-sided anytime prices -> per-player expected goals summing to ``mu``.

    Anytime-scorer markets quote backs only, so there is no complementary
    price to devig against and neither Shin nor proportional normalization
    applies. What *is* available is a second, two-sided estimate of the same
    quantity: the devigged match odds already say how many goals this team is
    expected to score. Converting each price to a rate with
    ``lambda = -ln(1 - p)`` and scaling the lot so they sum to that ``mu`` is
    the market-consistent way to strip the one-sided overround — it keeps the
    market's *relative* view of who scores and takes the *level* from the
    market's own better-measured number.
    """
    raw = {}
    for name, price in prices.items():
        p = min(max(1.0 / float(price), 1e-9), 1.0 - 1e-9)
        raw[name] = -math.log(1.0 - p)
    total = sum(raw.values())
    if not raw or total <= 0.0:
        return {name: 0.0 for name in raw}
    scale = float(mu) / total
    return {name: value * scale for name, value in raw.items()}


def ags_frame(raw_ags: list | None, players: pd.DataFrame,
              teams: pd.DataFrame, events: pd.DataFrame,
              odds_df: pd.DataFrame) -> pd.DataFrame:
    """Player props -> ``[code, gw, team_code, opp_code, lambda_ags]``.

    Each fixture's priced players are split by club, normalized against that
    club's devigged ``odds_e_goals_for`` from :func:`odds_frame`, and matched
    to FPL codes by normalized name *and* club. A fixture with no match-odds
    row is skipped entirely: without a devigged mu there is nothing to
    normalize against, and an un-normalized one-sided book is an overround
    rather than a set of probabilities.

    Players the bootstrap does not carry are dropped; FPL players nobody
    priced simply get no row and keep pure model output downstream.
    """
    from gaffer.data.names import normalize_name

    if raw_ags is None or odds_df is None or odds_df.empty:
        return pd.DataFrame(columns=AGS_FRAME_COLS)
    code_of_team = dict(zip(teams["name"], teams["code"]))
    by_name_team = {(normalize_name(r.name), int(r.team_code)): int(r.code)
                    for r in players.itertuples()}
    mu_of = {(int(r.team_code), int(r.opp_code), int(r.gw)):
             float(r.odds_e_goals_for) for r in odds_df.itertuples()}
    windows = _gw_windows(events)

    rows = []
    for fixture in raw_ags:
        books = fixture.get("bookmakers") or []
        market = _market(books[0], AGS_MARKET) if books else None
        if market is None:
            continue
        try:
            home = resolve_team(fixture["home_team"])
            away = resolve_team(fixture["away_team"])
        except GafferError as exc:
            print(f"player props: {exc}")
            continue
        if home not in code_of_team or away not in code_of_team:
            continue
        home_code, away_code = code_of_team[home], code_of_team[away]
        kickoff = pd.to_datetime(fixture["commence_time"], utc=True,
                                 format="mixed")
        gw = next((g for start, end, g in windows
                   if start <= kickoff < end), None)
        if gw is None:
            continue

        # Split the book by the club each priced player actually plays for:
        # the market lists both sides together and normalization is per team.
        by_team: dict[int, dict[str, float]] = {home_code: {}, away_code: {}}
        matched: dict[str, int] = {}
        for outcome in market.get("outcomes", []):
            name = normalize_name(outcome.get("name"))
            for team_code in (home_code, away_code):
                code = by_name_team.get((name, int(team_code)))
                if code is not None:
                    by_team[team_code][str(outcome["name"])] = float(
                        outcome["price"])
                    matched[str(outcome["name"])] = code
                    break

        for team_code, opp_code in ((home_code, away_code),
                                    (away_code, home_code)):
            mu = mu_of.get((int(team_code), int(opp_code), int(gw)))
            if mu is None or not by_team[team_code]:
                continue
            for name, lam in normalize_ags(by_team[team_code], mu).items():
                rows.append({"code": matched[name], "gw": int(gw),
                             "team_code": int(team_code),
                             "opp_code": int(opp_code), "lambda_ags": lam})
    return pd.DataFrame(rows, columns=AGS_FRAME_COLS)
