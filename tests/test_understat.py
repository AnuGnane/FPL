import json

import pandas as pd
import pytest

from gaffer.data.names import normalize_name
from gaffer.data.understat import (match_player_rows, parse_embedded_json,
                                   league_matches, team_match_rows)
from gaffer.errors import GafferError


def _embed(var: str, payload) -> str:
    """An understat page fragment: hex-escaped JSON inside JSON.parse('...')."""
    raw = json.dumps(payload)
    escaped = "".join(f"\\x{ord(c):02x}" if c in '"\'\\<>&' else c
                      for c in raw)
    return f"<script>var {var} = JSON.parse('{escaped}');</script>"


def test_normalize_name_strips_case_accents_and_punctuation():
    assert normalize_name("Ødegaard") == "odegaard"
    assert normalize_name("N'Golo Kanté") == "ngolo kante"
    assert normalize_name("  Heung-Min  Son ") == "heung min son"
    assert normalize_name("João Pedro") == "joao pedro"


def test_normalize_name_of_the_same_player_two_ways_agrees():
    assert normalize_name("Gabriel Martinelli") == normalize_name(
        "gabriel  martinelli")


def test_normalize_name_of_none_is_empty():
    assert normalize_name(None) == ""
    assert normalize_name(float("nan")) == ""


def test_parse_embedded_json_decodes_the_hex_escaped_blob():
    html = _embed("playersData", [{"id": "1", "player": "Kanté"}])
    assert parse_embedded_json(html, "playersData") == [
        {"id": "1", "player": "Kanté"}]


def test_parse_embedded_json_finds_the_right_variable_among_several():
    html = (_embed("teamsData", {"1": {"title": "Arsenal"}})
            + _embed("datesData", [{"id": "9"}]))
    assert parse_embedded_json(html, "datesData") == [{"id": "9"}]


def test_parse_embedded_json_raises_on_a_missing_variable():
    """A silent empty result would look exactly like a season with no data
    and would poison the cache with nothing."""
    with pytest.raises(GafferError) as exc:
        parse_embedded_json("<html></html>", "playersData")
    assert "playersData" in str(exc.value)


_DATES = [
    {"id": "18001", "isResult": True, "datetime": "2024-08-16 20:00:00",
     "h": {"id": "89", "title": "Manchester United"},
     "a": {"id": "76", "title": "Wolverhampton Wanderers"},
     "goals": {"h": "1", "a": "0"}},
    {"id": "18002", "isResult": False, "datetime": "2025-05-25 16:00:00",
     "h": {"id": "83", "title": "Arsenal"},
     "a": {"id": "89", "title": "Manchester United"},
     "goals": {"h": None, "a": None}},
]


def test_league_matches_lists_ids_dates_and_played_flags():
    out = league_matches(_embed("datesData", _DATES))
    assert list(out["match_id"]) == ["18001", "18002"]
    assert list(out["is_result"]) == [True, False]
    assert out.loc[0, "date"] == pd.Timestamp("2024-08-16").date()
    assert out.loc[0, "home_team"] == "Manchester United"


def test_league_matches_on_an_empty_season_is_an_empty_frame():
    out = league_matches(_embed("datesData", []))
    assert out.empty
    assert list(out.columns) == ["match_id", "date", "home_team", "away_team",
                                 "is_result"]


_TEAMS = {
    "83": {"id": "83", "title": "Arsenal", "history": [
        {"date": "2024-08-17 14:00:00", "xG": 1.8, "xGA": 0.6,
         "ppda": {"att": 240, "def": 22}, "deep": 9, "deep_allowed": 2},
        {"date": "2024-08-24 14:00:00", "xG": 2.1, "xGA": 1.4,
         "ppda": {"att": 200, "def": 25}, "deep": 11, "deep_allowed": 5},
    ]},
}


def test_team_match_rows_flattens_history_with_ppda():
    out = team_match_rows(_embed("teamsData", _TEAMS), season="2024-25",
                          season_idx=2)
    assert list(out.columns) == ["season", "season_idx", "team", "date",
                                 "us_xg", "us_xga", "ppda", "deep",
                                 "deep_allowed"]
    assert len(out) == 2
    assert out.loc[0, "team"] == "Arsenal"
    # PPDA is passes allowed per defensive action: att / def.
    assert abs(out.loc[0, "ppda"] - 240 / 22) < 1e-9
    assert out.loc[1, "us_xga"] == 1.4


def test_team_match_rows_with_a_zero_defensive_action_count_is_nan():
    """A division by zero here would ship an inf into a LightGBM split."""
    teams = {"83": {"id": "83", "title": "Arsenal", "history": [
        {"date": "2024-08-17 14:00:00", "xG": 1.0, "xGA": 1.0,
         "ppda": {"att": 100, "def": 0}, "deep": 1, "deep_allowed": 1}]}}
    out = team_match_rows(_embed("teamsData", teams), season="2024-25",
                          season_idx=2)
    assert pd.isna(out.loc[0, "ppda"])


_ROSTER = {
    "h": {"501": {"player_id": "1250", "player": "Bruno Fernandes",
                  "h_a": "h", "time": "90", "goals": "1", "assists": "0",
                  "shots": "4", "key_passes": "3", "xG": "0.85", "xA": "0.31",
                  "xGChain": "1.2", "xGBuildup": "0.4"}},
    "a": {"502": {"player_id": "3110", "player": "Matheus Cunha",
                  "h_a": "a", "time": "63", "goals": "0", "assists": "0",
                  "shots": "2", "key_passes": "1", "xG": "0.20", "xA": "0.05",
                  "xGChain": "0.5", "xGBuildup": "0.1"}},
}

_SHOTS = {
    "h": [{"player_id": "1250", "xG": "0.76", "situation": "Penalty"},
          {"player_id": "1250", "xG": "0.09", "situation": "OpenPlay"}],
    "a": [{"player_id": "3110", "xG": "0.20", "situation": "OpenPlay"}],
}


def _match_html() -> str:
    return _embed("rostersData", _ROSTER) + _embed("shotsData", _SHOTS)


def test_match_player_rows_carries_the_marginal_understat_stats():
    out = match_player_rows(_match_html(), match_id="18001",
                            date=pd.Timestamp("2024-08-16").date(),
                            home_team="Manchester United",
                            away_team="Wolverhampton Wanderers")
    assert list(out["understat_id"]) == ["1250", "3110"]
    assert list(out["team"]) == ["Manchester United",
                                 "Wolverhampton Wanderers"]
    assert list(out["minutes"]) == [90.0, 63.0]
    assert out.loc[0, "us_shots"] == 4.0
    assert out.loc[0, "us_key_passes"] == 3.0
    assert out.loc[0, "us_xgchain"] == 1.2
    assert out.loc[0, "us_xgbuildup"] == 0.4
    assert set(out["match_id"]) == {"18001"}
    assert set(out["date"]) == {pd.Timestamp("2024-08-16").date()}


def test_match_player_rows_derives_npxg_by_dropping_penalty_shots():
    """The roster blob has no npxG field; the shot list does, and a penalty
    is exactly the shot a per-90 shooting rate must not be credited with."""
    out = match_player_rows(_match_html(), match_id="18001",
                            date=pd.Timestamp("2024-08-16").date(),
                            home_team="Manchester United",
                            away_team="Wolverhampton Wanderers")
    assert abs(out.loc[0, "us_npxg"] - 0.09) < 1e-9
    assert abs(out.loc[1, "us_npxg"] - 0.20) < 1e-9


def test_match_player_rows_gives_a_player_with_no_shots_zero_npxg():
    roster = {"h": {"501": {"player_id": "77", "player": "Casemiro",
                            "h_a": "h", "time": "90", "goals": "0",
                            "assists": "0", "shots": "0", "key_passes": "2",
                            "xG": "0", "xA": "0.1", "xGChain": "0.3",
                            "xGBuildup": "0.3"}}, "a": {}}
    html = _embed("rostersData", roster) + _embed("shotsData", {"h": [], "a": []})
    out = match_player_rows(html, match_id="18001",
                            date=pd.Timestamp("2024-08-16").date(),
                            home_team="Manchester United",
                            away_team="Wolves")
    assert out.loc[0, "us_npxg"] == 0.0


def test_match_player_rows_on_an_empty_roster_is_an_empty_frame():
    html = _embed("rostersData", {"h": {}, "a": {}}) + _embed(
        "shotsData", {"h": [], "a": []})
    out = match_player_rows(html, match_id="18001",
                            date=pd.Timestamp("2024-08-16").date(),
                            home_team="A", away_team="B")
    assert out.empty
