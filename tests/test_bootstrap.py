import json
from pathlib import Path

from gaffer.data.bootstrap import (
    build_events,
    build_players,
    build_teams,
    next_gw,
    scoring_table,
)

RAW = json.loads(Path("tests/fixtures/bootstrap_sample.json").read_text())


def test_build_players_parses_numerics():
    players = build_players(RAW)
    assert {
        "code",
        "element",
        "name",
        "position",
        "team_code",
        "now_cost",
        "selected_by_percent",
        "xg90",
        "status",
        "price_change_percent",
    } <= set(players.columns)
    assert players["selected_by_percent"].dtype == "float64"
    assert players["position"].isin(["GKP", "DEF", "MID", "FWD"]).all()


def test_build_teams_and_events():
    teams = build_teams(RAW)
    assert {"team_id", "code", "name"} <= set(teams.columns)
    events = build_events(RAW)
    assert {"gw", "deadline_time", "is_next", "finished"} <= set(events.columns)


def test_scoring_table_has_position_values():
    s = scoring_table(RAW)
    assert s["goals_scored"]["MID"] == 5
    assert s["assists"]["MID"] == 3  # flat values broadcast to all positions
    assert s["clean_sheets"]["DEF"] == 4
    assert s["defensive_contribution"]["DEF"] == 2
    assert s["defensive_contribution"]["GKP"] == 0
    assert s["goals_conceded"]["DEF"] == -0.5  # per-GOAL rate
    assert abs(s["saves"]["GKP"] - 1 / 3) < 1e-9  # per-SAVE rate
    assert s["minutes_60_plus"]["MID"] == 2
    assert s["minutes_0_59"]["MID"] == 1
    # every identifier covers all four positions
    for key, per_pos in s.items():
        assert set(per_pos) == {"GKP", "DEF", "MID", "FWD"}, key


def test_next_gw():
    assert next_gw(RAW) in {ev["id"] for ev in RAW["events"]}
