"""Structured injury and line-up news — the half of minutes that cannot be
replayed.

Nothing here exists historically. There is no archive of what
premierinjuries.com said on a Friday in 2023, so none of it can be trained on
and none of it may ever reach the backtest: this package is a *prediction-time*
layer that sharpens the official flags behind
:func:`gaffer.models.availability.apply_availability`, and its value is
measured forward through the shadow log rather than backward through a replay
(spec §9, gate N2).

Every module here degrades to an empty frame — a dead host, a rewritten page, a
match rate below the floor — and an empty frame reproduces the official-flags
behaviour exactly. That is the contract ``tests/test_v5_degradation.py`` pins.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx

NEWS_CACHE = Path("data/raw/news")

NEWS_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
"""An honest browser User-Agent.

These are public pages read once every ``cache_hours``, at most a handful of
requests a week per source. The politeness that matters is the cache window,
not the string.
"""


def news_client(client: httpx.Client | None = None) -> httpx.Client:
    """The news package's own HTTP client.

    Deliberately *not* :class:`~gaffer.api.client.FPLClient`: that one is
    pinned to the FPL API's base URL, its snapshot conventions and its retry
    budget, and none of the three news hosts is that host. Same injectable
    ``transport`` seam, so every test runs through ``httpx.MockTransport``.
    """
    if client is not None:
        return client
    return httpx.Client(timeout=30, follow_redirects=True,
                        headers={"User-Agent": NEWS_UA})


def cache_path(cache_dir: Path, prefix: str, cache_hours: int,
               now: datetime | None = None) -> Path:
    """Where this fetch window's snapshot lives.

    The filename *is* the cache key: one file per ``cache_hours``-wide bucket
    of wall-clock time, so "have we already read this today" is an
    ``exists()`` rather than a stored timestamp, and yesterday's snapshot stays
    on disk for debugging rather than being overwritten.
    """
    now = now or datetime.now(timezone.utc)
    hours = max(int(cache_hours), 1)
    bucket = (now.hour // hours) * hours
    stamp = f"{now:%Y%m%d}T{bucket:02d}"
    return Path(cache_dir) / f"{prefix}-{stamp}.html"


def cached_text(url: str, dest: Path, client: httpx.Client | None = None
                ) -> str | None:
    """The page at ``url``, from ``dest`` if this window already fetched it.

    ``None`` on any failure, with a printed line. Every caller turns that into
    an empty frame; nothing in this package raises into the advise path.
    """
    if dest.exists():
        return dest.read_text(encoding="utf-8")
    http = news_client(client)
    try:
        resp = http.get(url)
        resp.raise_for_status()
    except (httpx.HTTPStatusError, httpx.TransportError) as exc:
        print(f"news: {url} unavailable ({exc})")
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(resp.text, encoding="utf-8")
    return resp.text


def fetched_at(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
