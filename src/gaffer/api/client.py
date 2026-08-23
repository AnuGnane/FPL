from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE = "https://fantasy.premierleague.com/api"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")


class FPLClient:
    def __init__(self, raw_dir: Path | str = "data/raw", transport=None,
                 retries: int = 3, backoff: float = 2.0):
        self.raw_dir = Path(raw_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.retries = retries
        self.backoff = backoff
        self._http = httpx.Client(headers={"User-Agent": UA}, timeout=30,
                                  transport=transport)

    def _get(self, path: str, snapshot: str | None = None):
        last_exc = None
        for attempt in range(self.retries):
            try:
                resp = self._http.get(f"{BASE}/{path}")
                resp.raise_for_status()
                data = resp.json()
                if snapshot:
                    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
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

    def get_bootstrap(self):
        return self._get("bootstrap-static/", snapshot="bootstrap")

    def get_fixtures(self):
        return self._get("fixtures/", snapshot="fixtures")

    def get_element_summary(self, player_id: int):
        return self._get(f"element-summary/{player_id}/")

    def get_entry(self, entry_id: int):
        return self._get(f"entry/{entry_id}/", snapshot=f"entry-{entry_id}")

    def get_entry_history(self, entry_id: int):
        return self._get(f"entry/{entry_id}/history/")

    def get_entry_transfers(self, entry_id: int):
        return self._get(f"entry/{entry_id}/transfers/")

    def get_entry_picks(self, entry_id: int, gw: int):
        return self._get(f"entry/{entry_id}/event/{gw}/picks/")

    def get_league_standings(self, league_id: int, page: int = 1):
        return self._get(
            f"leagues-classic/{league_id}/standings/?page_standings={page}")

    def get_event_live(self, gw: int):
        return self._get(f"event/{gw}/live/")

    def get_event_status(self):
        return self._get("event-status/")
