"""Tier-resolved effective ownership: what the top 10k actually own.

League EO says what my rivals own; ``selected_by_percent`` says what the
whole game owns. Neither is what a good manager is measured against, which
is the top of the pyramid. This module samples it: 300 entries drawn
uniformly from the first 200 standings pages of the overall classic league
(50 entries a page = the top 10,000), each entry's live picks fetched once.

Display only — the live tracker renders it and nothing else reads it. Every
failure mode (rate limit, page shape change, a private entry) degrades to
fewer samples or to an empty table, never to an exception that would take
the tracker down.
"""

from __future__ import annotations

import json
import math
import random
import time
from pathlib import Path

TIER_LEAGUE = 314
"""The overall classic league every entry is in."""

PAGE_SIZE = 50
MAX_PAGE = 200
"""200 pages x 50 entries = the top 10,000."""

TIER_SAMPLE = 300
TIER_SEED = 20260826
RAW_TIER = Path("data/raw/tier_eo")

FETCH_PAUSE_S = 0.05
"""Slept between per-entry picks fetches, so a full 300-entry sample is a
15-second trickle rather than a burst the FPL API answers with a 429."""


def sample_slots(n: int, seed: int, max_page: int = MAX_PAGE,
                 page_size: int = PAGE_SIZE) -> list[tuple[int, int]]:
    """``n`` distinct (page, slot) pairs, uniform over the tier, sorted.

    Sorted so that the caller fetches each page once and reads every slot it
    sampled from it. At the default 300 slots over 200 pages that is about
    155 distinct pages touched — ~455 API calls all in, against the ~600 a
    page-per-slot walk would cost.
    """
    universe = [(page, slot) for page in range(1, max_page + 1)
                for slot in range(page_size)]
    return sorted(random.Random(seed).sample(universe, min(n, len(universe))))


def fetch_tier_entries(client, slots: list[tuple[int, int]]) -> list[int]:
    """Entry ids at those (page, slot) positions; each page fetched once."""
    by_page: dict[int, list[dict]] = {}
    entries: list[int] = []
    for page, slot in slots:
        if page not in by_page:
            try:
                data = client.get_league_standings(TIER_LEAGUE, page)
                by_page[page] = data["standings"]["results"]
            except Exception:
                by_page[page] = []      # a page that will not load is skipped
        results = by_page[page]
        if slot < len(results):
            entries.append(int(results[slot]["entry"]))
    return entries


def eo_se(total: float, sum_sq: float, n: int) -> float:
    """Standard error of the sampled EO itself, in percentage points.

    ``total`` and ``sum_sq`` are the sum and sum of squares of one element's
    per-entry contributions — the entry's multiplier for him, or 0 when the
    entry does not start him. The
    estimator is their mean, so its error bar is the sample standard
    deviation over root n. Ownership's binomial SE was the wrong bar: it
    ignores captaincy entirely, and captaincy is half of what EO measures.
    """
    if n < 2:
        return 0.0
    var = (sum_sq - total * total / n) / (n - 1)
    return math.sqrt(max(var, 0.0) / n) * 100


def tier_eo_table(client, gw: int, sample: int = TIER_SAMPLE,
                  seed: int = TIER_SEED,
                  raw_dir: Path | str = RAW_TIER) -> dict[int, dict]:
    """element -> {"eo", "se", "n"} for the sampled tier, cached per GW.

    ``eo`` is effective ownership in percent (captaincy counts double, the
    bench counts zero), so it can exceed 100. ``se`` is the standard error of
    that estimate at this sample size — see :func:`eo_se` — and is the reason
    the tracker prints it next to the number.

    An empty result is cached like any other: a gameweek where nobody's picks
    are readable is a fact about that gameweek, and re-sampling 300 entries
    on every tracker poll to rediscover it is the expensive way to learn it.
    """
    path = Path(raw_dir) / f"{int(gw)}.json"
    if path.exists():
        cached = json.loads(path.read_text())
        return {int(key): value for key, value in cached.items()}
    entries = fetch_tier_entries(client, sample_slots(sample, seed + int(gw)))
    totals: dict[int, float] = {}
    sum_sq: dict[int, float] = {}
    n = 0
    for i, entry in enumerate(entries):
        if i:
            time.sleep(FETCH_PAUSE_S)
        try:
            picks = client.get_entry_picks(int(entry), int(gw))["picks"]
        except Exception:
            continue        # private or missing entry — one fewer sample
        n += 1
        for pick in picks:
            multiplier = int(pick.get("multiplier", 0))
            if multiplier <= 0:
                continue
            element = int(pick["element"])
            totals[element] = totals.get(element, 0.0) + multiplier
            sum_sq[element] = sum_sq.get(element, 0.0) + multiplier ** 2
    out = {element: {"eo": round(total / n * 100, 1),
                     "se": round(eo_se(total, sum_sq[element], n), 1),
                     "n": n}
           for element, total in totals.items()} if n else {}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({str(k): v for k, v in out.items()}))
    return out
