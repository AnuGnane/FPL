"""Canonical tables built from the FPL ``bootstrap-static`` payload."""

from __future__ import annotations

import pandas as pd

from gaffer.api.parse import to_float, to_int
from gaffer.errors import GafferError

POS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
POSITIONS = ["GKP", "DEF", "MID", "FWD"]

FLOAT_FIELDS = [
    "form",
    "points_per_game",
    "ep_next",
    "ep_this",
    "selected_by_percent",
    "expected_goals",
    "expected_assists",
    "expected_goal_involvements",
    "expected_goals_conceded",
    "expected_goals_per_90",
    "expected_assists_per_90",
    "ict_index",
    "price_change_percent",
    "value_form",
    "value_season",
    "defensive_contribution_per_90",
]


def build_players(raw: dict) -> pd.DataFrame:
    rows = []
    for e in raw["elements"]:
        if e.get("element_type") not in POS:  # ignore legacy manager type 5
            continue
        row = {
            "code": e["code"],
            "element": e["id"],
            "name": e["web_name"],
            "position": POS[e["element_type"]],
            "team_id": e["team"],
            "team_code": e["team_code"],
            "now_cost": e["now_cost"],
            "cost_change_start": e.get("cost_change_start", 0),
            "status": e.get("status", "a"),
            "news": e.get("news", ""),
            "chance_of_playing": to_int(e.get("chance_of_playing_next_round")),
            "transfers_in_event": e.get("transfers_in_event", 0),
            "transfers_out_event": e.get("transfers_out_event", 0),
            "penalties_order": to_int(e.get("penalties_order")),
            "price_change_calibrating": bool(e.get("price_change_calibrating")),
            "price_change_locked_until": e.get("price_change_locked_until"),
            "price_change_projections": str(e.get("price_change_projections", "")),
        }
        for f in FLOAT_FIELDS:
            row[f] = to_float(e.get(f))
        row["xg90"] = row.pop("expected_goals_per_90")
        row["xa90"] = row.pop("expected_assists_per_90")
        rows.append(row)
    return pd.DataFrame(rows)


def build_teams(raw: dict) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "team_id": t["id"],
                "code": t["code"],
                "name": t["name"],
                "short_name": t["short_name"],
            }
            for t in raw["teams"]
        ]
    )


def build_events(raw: dict) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "gw": ev["id"],
                "deadline_time": ev["deadline_time"],
                "is_current": ev.get("is_current", False),
                "is_next": ev.get("is_next", False),
                "finished": ev.get("finished", False),
                "data_checked": ev.get("data_checked", False),
            }
            for ev in raw["events"]
        ]
    )


def next_gw(raw: dict) -> int:
    for ev in raw["events"]:
        if ev.get("is_next"):
            return ev["id"]
    raise GafferError(
        "no upcoming gameweek in the bootstrap — season may be over or not "
        "yet published")


# Scoring identifiers we assemble expected points from.
SCORING_KEYS = [
    "goals_scored",
    "assists",
    "clean_sheets",
    "goals_conceded",
    "saves",
    "penalties_saved",
    "penalties_missed",
    "yellow_cards",
    "red_cards",
    "own_goals",
    "defensive_contribution",
    "bonus",
    "minutes_0_59",
    "minutes_60_plus",
]

# Our identifier -> the API's name in game_config.scoring, where they differ.
ALIASES = {"minutes_0_59": "short_play", "minutes_60_plus": "long_play"}

# The API states some values with an implicit "per N events" convention
# (-1 point per 2 goals conceded, 1 point per 3 saves). Downstream expected
# points multiply these by expected goals conceded / expected saves directly,
# so convert them to per-event rates here.
RATE_DIVISORS = {"goals_conceded": 2, "saves": 3}


def scoring_table(raw: dict) -> dict[str, dict[str, float]]:
    """``{identifier: {position: points}}`` from the live rules, never hard-coded.

    ``game_config.scoring`` holds either a scalar (applies to every position) or
    a mapping keyed by the position short name (``"GKP"``/``"DEF"``/``"MID"``/
    ``"FWD"``). Positions absent from a mapping default to 0.
    """
    scoring = raw["game_config"]["scoring"]
    table: dict[str, dict[str, float]] = {}
    for key in SCORING_KEYS:
        api_key = ALIASES.get(key, key)
        val = scoring.get(api_key, 0)
        if isinstance(val, dict):
            per_pos = {p: float(val.get(p, 0)) for p in POSITIONS}
        else:
            per_pos = {p: float(val) for p in POSITIONS}
        divisor = RATE_DIVISORS.get(key)
        if divisor:
            per_pos = {p: v / divisor for p, v in per_pos.items()}
        table[key] = per_pos
    return table
