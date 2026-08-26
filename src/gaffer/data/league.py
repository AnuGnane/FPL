"""Mini-league rivals: who we're racing, and what they own.

Effective ownership (EO) inside the user's own league is what makes advice
"safe" or "differential" — a 90%-EO captain protects rank, a 5%-EO one
swings it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from gaffer.api.client import FPLClient

STANDINGS_COLS = ["entry", "entry_name", "player_name", "rank",
                  "last_rank", "total", "event_total"]

HISTORY_COLS = ["entry", "gw", "points"]

RAW_LEAGUE = Path("data/raw/league")
"""Where league payloads are cached, alongside the client's other raw JSON."""


def fetch_rival_entries(client: FPLClient, league_id: int,
                        exclude_entry: int, max_rivals: int = 50) -> pd.DataFrame:
    """Top ``max_rivals`` classic-league entries, minus the user's own."""
    rows, page = [], 1
    while True:
        data = client.get_league_standings(league_id, page)
        results = data["standings"]["results"]
        rows.extend(results)
        if not data["standings"].get("has_next") or len(rows) >= max_rivals:
            break
        page += 1
    if not rows:
        # A league with no standings yet (freshly created, or before GW1 is
        # scored) returns an empty results list; pd.DataFrame([])[COLS] would
        # KeyError on every column.
        return pd.DataFrame(columns=STANDINGS_COLS)
    df = pd.DataFrame(rows)[STANDINGS_COLS]
    return df[df["entry"] != exclude_entry].head(max_rivals)


def fetch_rival_picks(client: FPLClient, entries: list[int],
                      gw: int) -> dict[int, list[dict]]:
    """Picks for a finished/underway GW (public post-deadline; 404 pre-deadline)."""
    out = {}
    for entry in entries:
        try:
            out[entry] = client.get_entry_picks(entry, gw)["picks"]
        except Exception:
            continue        # rival joined late / endpoint 404 — skip
    return out


def effective_ownership(rival_picks: dict[int, list[dict]]) -> dict[int, float]:
    """element -> EO% across rivals (captain counts double, bench counts 0)."""
    if not rival_picks:
        return {}
    n = len(rival_picks)
    counts: dict[int, float] = {}
    for picks in rival_picks.values():
        for p in picks:
            counts[p["element"]] = counts.get(p["element"], 0) + p["multiplier"]
    return {el: round(c / n * 100, 1) for el, c in counts.items()}


def fetch_rival_history(client: FPLClient, entries: list[int], gw: int,
                        raw_dir: Path | str = RAW_LEAGUE) -> pd.DataFrame:
    """(entry, gw, points) for every entry, this season through ``gw``.

    Cached per gameweek: the completed weeks of a season are facts, and one
    HTTP call per rival per advise run is the most expensive thing league
    mode does. Weeks after ``gw`` are dropped — a gameweek still being played
    would put a half-scored margin into the sigma estimate. An entry whose
    history is not public is skipped, exactly as ``fetch_rival_picks`` skips
    an entry whose picks are not.
    """
    path = Path(raw_dir) / f"history-gw{int(gw)}.json"
    if path.exists():
        return pd.DataFrame(json.loads(path.read_text()), columns=HISTORY_COLS)
    rows: list[dict] = []
    for entry in entries:
        try:
            current = client.get_entry_history(int(entry)).get("current") or []
        except Exception:
            continue        # entry joined late / history private — skip
        for event in current:
            if int(event["event"]) > int(gw):
                continue
            rows.append({"entry": int(entry), "gw": int(event["event"]),
                         "points": int(event["points"])})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows))
    return pd.DataFrame(rows, columns=HISTORY_COLS)
