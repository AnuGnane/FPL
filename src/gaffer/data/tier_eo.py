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
from pathlib import Path

TIER_LEAGUE = 314
"""The overall classic league every entry is in."""

PAGE_SIZE = 50
MAX_PAGE = 200
"""200 pages x 50 entries = the top 10,000."""

TIER_SAMPLE = 300
TIER_SEED = 20260826
RAW_TIER = Path("data/raw/tier_eo")


def sample_slots(n: int, seed: int, max_page: int = MAX_PAGE,
                 page_size: int = PAGE_SIZE) -> list[tuple[int, int]]:
    """``n`` distinct (page, slot) pairs, uniform over the tier, sorted.

    Sorted so that the caller fetches each page once and reads every slot it
    sampled from it — the difference between ~306 API calls and ~600.
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


def binomial_se(p: float, n: int) -> float:
    """Standard error of an ownership proportion, in percentage points."""
    if n <= 0:
        return 0.0
    return math.sqrt(max(p * (1 - p), 0.0) / n) * 100


def tier_eo_table(client, gw: int, sample: int = TIER_SAMPLE,
                  seed: int = TIER_SEED,
                  raw_dir: Path | str = RAW_TIER) -> dict[int, dict]:
    """element -> {"eo", "se", "n"} for the sampled tier, cached per GW.

    ``eo`` is effective ownership in percent (captaincy counts double, the
    bench counts zero), so it can exceed 100. ``se`` is the binomial standard
    error of plain *ownership* at this sample size — the honest error bar for
    a sample, and the reason the tracker prints it next to the number.
    """
    path = Path(raw_dir) / f"{int(gw)}.json"
    if path.exists():
        cached = json.loads(path.read_text())
        return {int(key): value for key, value in cached.items()}
    entries = fetch_tier_entries(client, sample_slots(sample, seed + int(gw)))
    owners: dict[int, int] = {}
    multipliers: dict[int, int] = {}
    n = 0
    for entry in entries:
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
            owners[element] = owners.get(element, 0) + 1
            multipliers[element] = multipliers.get(element, 0) + multiplier
    if not n:
        return {}
    out = {element: {"eo": round(total / n * 100, 1),
                     "se": round(binomial_se(owners[element] / n, n), 1),
                     "n": n}
           for element, total in multipliers.items()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({str(k): v for k, v in out.items()}))
    return out
