"""Live-season per-GW ingestion into the canonical ``player_gw`` table.

``CANONICAL_COLS`` is the contract shared by history ingestion, feature
engineering, and every model; ``RENAME``/``XG_FIELDS`` are reused by the
historical loader.
"""

from __future__ import annotations

import time

import pandas as pd

from gaffer.api.client import FPLClient
from gaffer.api.parse import to_float
from gaffer.data import store
from gaffer.data.bootstrap import build_players, build_teams

CANONICAL_COLS = [
    "season",
    "season_idx",
    "gw",
    "code",
    "element",
    "name",
    "position",
    "team_code",
    "opp_code",
    "was_home",
    "kickoff_time",
    "minutes",
    "starts",
    "total_points",
    "goals",
    "assists",
    "xg",
    "xa",
    "xgi",
    "xgc",
    "cs",
    "gc",
    "saves",
    "bonus",
    "bps",
    "yc",
    "rc",
    "og",
    "pens_missed",
    "pens_saved",
    "defcon",
    "tackles",
    "cbi",
    "recoveries",
    "value",
    "selected",
    # Set-piece duty as recorded AT SNAPSHOT TIME — the live table is the only
    # place this is ever observed, so history rows backfill to NA.
    "penalties_order",
    "direct_freekicks_order",
    "corners_and_indirect_freekicks_order",
]

SET_PIECE_COLS = [
    "penalties_order",
    "direct_freekicks_order",
    "corners_and_indirect_freekicks_order",
]

RENAME = {
    "round": "gw",
    "goals_scored": "goals",
    "clean_sheets": "cs",
    "goals_conceded": "gc",
    "yellow_cards": "yc",
    "red_cards": "rc",
    "own_goals": "og",
    "penalties_missed": "pens_missed",
    "penalties_saved": "pens_saved",
    "defensive_contribution": "defcon",
    "clearances_blocks_interceptions": "cbi",
}

XG_FIELDS = {
    "expected_goals": "xg",
    "expected_assists": "xa",
    "expected_goal_involvements": "xgi",
    "expected_goals_conceded": "xgc",
}


def history_to_rows(
    summary: dict,
    player_meta: dict,
    team_id_to_code: dict,
    season: str,
    season_idx: int,
) -> list[dict]:
    """Map one element-summary payload to canonical ``player_gw`` rows."""
    rows = []
    for h in summary.get("history", []):
        row = {RENAME.get(k, k): v for k, v in h.items()}
        for api_key, col in XG_FIELDS.items():
            row[col] = to_float(h.get(api_key), default=0.0)
        row.update(player_meta)
        row["season"], row["season_idx"] = season, season_idx
        row["opp_code"] = team_id_to_code.get(h.get("opponent_team"))
        rows.append({c: row.get(c) for c in CANONICAL_COLS})
    return rows


def _carry_setpiece_orders(df: pd.DataFrame,
                           players: pd.DataFrame) -> pd.DataFrame:
    """Set-piece orders that accumulate instead of being retro-stamped.

    Element summaries carry no set-piece info, and the bootstrap reports only
    *today's* assignment. ``refresh_live`` rebuilds the whole parquet on every
    run, so stamping the current orders onto every row would rewrite history
    each week — a player who lost the penalties in GW12 would look as though
    he never took them, and the promised accumulation of snapshots would never
    happen.

    So: a (element, gw) pair the stored parquet already holds keeps whatever
    was recorded for it then, and only rows for a gameweek the parquet has
    never seen get today's bootstrap orders.
    """
    prev = (store.load("live/player_gw.parquet")
            if store.exists("live/player_gw.parquet") else None)
    seen_gws = set() if prev is None else set(prev["gw"].dropna())
    fresh = ~df["gw"].isin(seen_gws)
    for col in SET_PIECE_COLS:
        by_element = dict(zip(players["element"], players[col]))
        today = pd.to_numeric(df["element"].map(by_element), errors="coerce")
        if prev is None or col not in prev.columns:
            df[col] = today
            continue
        stored = dict(zip(zip(prev["element"], prev["gw"]), prev[col]))
        kept = pd.to_numeric(
            pd.Series(list(zip(df["element"], df["gw"])),
                      index=df.index).map(stored),
            errors="coerce")
        df[col] = kept.where(~fresh, today)
    return df


def refresh_live(
    client: FPLClient,
    season: str,
    season_idx: int,
    sleep_s: float = 0.05,
) -> pd.DataFrame:
    """Fetch element-summary for every current player -> data/live/player_gw.parquet.

    Spec: provisional data never enters training — rows for any GW that is
    not yet data_checked (bonus can still change until ~09:00 the morning
    after the last match) are dropped before saving.
    """
    raw = client.get_bootstrap()
    unchecked = {ev["id"] for ev in raw["events"] if not ev.get("data_checked", False)}
    players = build_players(raw)
    teams = build_teams(raw)
    team_id_to_code = dict(zip(teams["team_id"], teams["code"]))
    all_rows: list[dict] = []
    for p in players.itertuples():
        summary = client.get_element_summary(p.element)
        meta = {
            "code": p.code,
            "element": p.element,
            "name": p.name,
            "position": p.position,
            "team_code": p.team_code,
        }
        all_rows.extend(
            history_to_rows(summary, meta, team_id_to_code, season, season_idx)
        )
        time.sleep(sleep_s)  # politeness: ~600 calls
    df = pd.DataFrame(all_rows, columns=CANONICAL_COLS)
    df = df[~df["gw"].isin(unchecked)]
    df = _carry_setpiece_orders(df, players)
    store.save(df, "live/player_gw.parquet")
    return df
