"""The Odds API client for bookmaker prices on EPL fixtures.

Odds are an optional signal: with no API key configured the client stays
silent (returns None) rather than raising, so callers can treat bookmaker
features as best-effort.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from gaffer.data import store

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
