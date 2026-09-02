"""FPL-Core-Insights: path discovery, parsing, and what the archive really is.

Every fixture in this file is a transcription of the live archive, measured
2026-09-02 and recorded in the W4 plan's Appendix A. Where a header looks
arbitrary it is because it is copied, not invented.
"""

from __future__ import annotations

import pandas as pd

from gaffer.data.core_insights import (SEASON_TABLES, ci_paths_from_tree,
                                       repo_season)


def _tree(paths: list[str]) -> dict:
    """The shape ``git/trees?recursive=1`` answers with."""
    return {"tree": [{"path": p, "type": "blob"} for p in paths]}


TREE = _tree([
    # 2024-2025: the flat, one-folder-per-table layout.
    "data/2024-2025/matches/GW1/matches.csv",
    "data/2024-2025/matches/GW2/matches.csv",
    "data/2024-2025/playermatchstats/GW1/playermatchstats.csv",
    "data/2024-2025/playermatchstats/GW2/playermatchstats.csv",
    "data/2024-2025/players/players.csv",
    "data/2024-2025/teams/teams.csv",
    # 2025-2026: the By Gameweek layout, with By Tournament beside it. Listed
    # in git's own tree order, which puts "By Gameweek" *before* the season
    # root's players.csv — the per-gameweek snapshots below are real files and
    # a "first seen wins" reader claims GW1's copy instead of the season map.
    "data/2025-2026/By Gameweek/GW1/fixtures.csv",
    "data/2025-2026/By Gameweek/GW1/matches.csv",
    "data/2025-2026/By Gameweek/GW1/players.csv",
    "data/2025-2026/By Gameweek/GW1/playermatchstats.csv",
    "data/2025-2026/By Gameweek/GW1/teams.csv",
    "data/2025-2026/By Gameweek/GW10/fixtures.csv",
    "data/2025-2026/By Gameweek/GW10/players.csv",
    "data/2025-2026/By Gameweek/GW10/playermatchstats.csv",
    "data/2025-2026/By Gameweek/GW10/teams.csv",
    "data/2025-2026/By Tournament/EFL Cup/GW2/fixtures.csv",
    "data/2025-2026/players.csv",
    "data/2025-2026/supplemental/incidents_quarantined.csv",
    "data/2025-2026/teams.csv",
    # A season nobody asked for.
    "data/2023-2024/players.csv",
])


def test_repo_season_is_the_archives_folder_naming():
    assert repo_season("2025-26") == "2025-2026"
    assert repo_season("2026-27") == "2026-2027"


def test_the_by_gameweek_layout_is_found():
    found = ci_paths_from_tree(TREE, ["2025-26"])
    assert found["2025-26"]["players"] == "data/2025-2026/players.csv"
    assert found["2025-26"]["teams"] == "data/2025-2026/teams.csv"
    assert found["2025-26"]["fixtures"] == {
        1: "data/2025-2026/By Gameweek/GW1/fixtures.csv",
        10: "data/2025-2026/By Gameweek/GW10/fixtures.csv"}
    assert found["2025-26"]["playermatchstats"] == {
        1: "data/2025-2026/By Gameweek/GW1/playermatchstats.csv",
        10: "data/2025-2026/By Gameweek/GW10/playermatchstats.csv"}


def test_the_season_root_element_map_beats_a_per_gameweek_snapshot():
    """The archive publishes players.csv and teams.csv *both* at the season
    root and inside every ``By Gameweek/GW<n>`` folder, and git lists the
    gameweek folders first. A reader that took the first path it saw would key
    the whole season off GW1's snapshot — a map missing every player who
    arrived later. The shallowest path wins instead."""
    found = ci_paths_from_tree(TREE, ["2025-26"])
    assert "By Gameweek" not in found["2025-26"]["players"]
    assert "By Gameweek" not in found["2025-26"]["teams"]


def test_by_tournament_is_never_walked():
    """A2b: By Gameweek already carries every tournament, so reading both
    would count an EFL Cup tie twice."""
    found = ci_paths_from_tree(TREE, ["2025-26"])
    assert all("By Tournament" not in p
               for p in found["2025-26"]["fixtures"].values())


def test_the_flat_2024_25_layout_is_found_by_the_same_call():
    found = ci_paths_from_tree(TREE, ["2024-25"])
    assert found["2024-25"]["teams"] == "data/2024-2025/teams/teams.csv"
    assert found["2024-25"]["players"] == "data/2024-2025/players/players.csv"
    # It has no fixtures.csv anywhere; matches.csv is the fallback (A2b).
    assert found["2024-25"]["fixtures"] == {
        1: "data/2024-2025/matches/GW1/matches.csv",
        2: "data/2024-2025/matches/GW2/matches.csv"}
    assert set(found["2024-25"]["playermatchstats"]) == {1, 2}


def test_fixtures_beats_matches_when_both_are_published():
    """They are the same bytes in the live archive; picking one keeps the
    reader deterministic rather than dependent on tree order."""
    found = ci_paths_from_tree(TREE, ["2025-26"])
    assert found["2025-26"]["fixtures"][1].endswith("/fixtures.csv")


def test_a_season_the_archive_does_not_publish_is_an_empty_bundle():
    found = ci_paths_from_tree(TREE, ["2021-22"])
    assert found["2021-22"] == {"players": None, "teams": None,
                                "fixtures": {}, "playermatchstats": {}}


def test_an_unreachable_tree_is_empty_bundles_not_an_exception():
    found = ci_paths_from_tree({}, ["2025-26", "2024-25"])
    assert set(found) == {"2025-26", "2024-25"}
    assert all(b["players"] is None and b["fixtures"] == {}
               for b in found.values())


def test_season_tables_is_the_contract_every_bundle_answers():
    assert SEASON_TABLES == ("players", "teams", "fixtures",
                             "playermatchstats")


# --- Task 2: the parsers -------------------------------------------------

from gaffer.data.core_insights import (CI_ELO_COLS, CI_FIXTURE_COLS,
                                       CI_PLAYER_COLS, PMS_KEY_COLS,
                                       PMS_STAT_COLS, elo_rows, fixture_rows,
                                       player_code_map, player_match_rows)

PLAYERS_CSV = (
    "player_code,player_id,first_name,second_name,web_name,team_code,position\n"
    "208706,452,Bruno,Guimaraes,Bruno G.,3,Midfielder\n"
    "232413,266,Eberechi,Eze,Eze,3,Midfielder\n"
    "1,7,Nobody,Nowhere,Nobody,3,Defender\n")

FIXTURES_CSV = (
    "gameweek,kickoff_time,home_team,home_team_elo,home_score,away_score,"
    "away_team,away_team_elo,finished,match_id,tournament\n"
    "2,2026-08-30T13:00:00,2.0,1801.5,1,1,94.0,1750.25,True,"
    "26-27-prem-leeds-united-vs-brentford,prem\n"
    "2,2026-08-25T18:45:00,,,0,3,9.0,,True,"
    "26-27-efl-cup-exeter-city-vs-coventry-city-2026-08-24,efl-cup\n"
    "6,2026-10-10T14:00:00,8.0,,,,91.0,,False,"
    "26-27-prem-chelsea-vs-afc-bournemouth,prem\n")

PMS_CSV = (
    "player_id,match_id,minutes_played,accurate_crosses,"
    "touches_opposition_box,final_third_passes,tackles_won,interceptions,"
    "blocks,clearances,recoveries,start_min,finish_min,"
    "defensive_contributions\n"
    "452,26-27-prem-leeds-united-vs-brentford,90,2,4,11,3,1,0,2,7,0,90,6\n"
    "266,26-27-prem-leeds-united-vs-brentford,63,0,1,4,1,0,1,0,3,0,63,2\n"
    "999,26-27-prem-leeds-united-vs-brentford,12,0,0,0,0,0,0,0,0,78,90,0\n")

PMS_CSV_2024 = (  # A3: no defensive_contributions in the 2024-2025 layout
    "player_id,match_id,minutes_played,accurate_crosses,"
    "touches_opposition_box,final_third_passes,tackles_won,interceptions,"
    "blocks,clearances,recoveries,start_min,finish_min\n"
    "452,24-25-prem-a-vs-b,90,1,3,9,2,2,1,4,6,0,90\n")


def test_player_code_map_reads_the_archives_own_element_map():
    assert player_code_map(PLAYERS_CSV) == {452: 208706, 266: 232413, 7: 1}


def test_player_code_map_of_a_headerless_blob_is_empty_not_a_crash():
    assert player_code_map("") == {}
    assert player_code_map("nothing,useful\n1,2\n") == {}


def test_player_match_rows_join_to_code_and_carry_the_season():
    out = player_match_rows(PMS_CSV, "2026-27", 3, 2,
                            player_code_map(PLAYERS_CSV))
    assert list(out.columns) == CI_PLAYER_COLS
    # element 999 is in no map and drops rather than landing on a NaN key.
    assert set(out["code"]) == {208706, 232413}
    assert len(out) == 2
    assert set(out["season"]) == {"2026-27"}
    assert set(out["season_idx"]) == {3}
    assert set(out["gw"]) == {2}
    row = out[out["code"] == 208706].iloc[0]
    assert row["minutes_played"] == 90.0
    assert row["accurate_crosses"] == 2.0
    assert row["defensive_contributions"] == 6.0


def test_a_season_missing_defensive_contributions_gets_an_all_nan_column():
    """A3: the 2024-2025 layout does not publish it. The column still exists,
    so one parquet schema serves every season."""
    out = player_match_rows(PMS_CSV_2024, "2024-25", 2, 1,
                            player_code_map(PLAYERS_CSV))
    assert "defensive_contributions" in out.columns
    assert out["defensive_contributions"].isna().all()
    assert out["accurate_crosses"].iloc[0] == 1.0


def test_an_unknown_column_is_ignored_rather_than_carried():
    drifted = PMS_CSV.replace("player_id,", "brand_new_metric,player_id,") \
        .replace("452,26-27", "1.5,452,26-27") \
        .replace("266,26-27", "1.5,266,26-27") \
        .replace("999,26-27", "1.5,999,26-27")
    out = player_match_rows(drifted, "2026-27", 3, 2,
                            player_code_map(PLAYERS_CSV))
    assert "brand_new_metric" not in out.columns
    assert list(out.columns) == CI_PLAYER_COLS
    assert len(out) == 2


def test_a_missing_key_column_drops_the_file_rather_than_guessing():
    headless = PMS_CSV.replace("player_id,match_id,", "match_id,")
    out = player_match_rows(headless, "2026-27", 3, 2,
                            player_code_map(PLAYERS_CSV))
    assert out.empty
    assert list(out.columns) == CI_PLAYER_COLS


def test_pms_column_contracts_are_disjoint_and_complete():
    assert set(PMS_KEY_COLS).isdisjoint(PMS_STAT_COLS)
    assert CI_PLAYER_COLS[:4] == ["season", "season_idx", "gw", "code"]


def test_fixture_rows_emit_one_row_per_league_club_per_match():
    out = fixture_rows(FIXTURES_CSV, "2026-27", 3, 2)
    assert list(out.columns) == CI_FIXTURE_COLS
    # 3 matches: one with two league clubs, one with one, one with two = 5.
    assert len(out) == 5
    leeds = out[(out["team_code"] == 2) & (out["tournament"] == "prem")]
    assert bool(leeds["is_home"].iloc[0]) is True
    assert leeds["opponent_code"].iloc[0] == 94
    cup = out[out["tournament"] == "efl-cup"]
    assert len(cup) == 1 and cup["team_code"].iloc[0] == 9
    # The non-league side is blank in the file and contributes no row and no
    # opponent code.
    assert pd.isna(cup["opponent_code"].iloc[0])


def test_unplayed_fixtures_are_kept_because_that_is_the_whole_point():
    """A2d: density_pub_7d is a prediction-time feature only because the
    archive publishes fixtures before they are played."""
    header, *rows = FIXTURES_CSV.strip().split("\n")
    gw6 = header + "\n" + rows[2] + "\n"   # the tie nobody has played yet
    future = fixture_rows(gw6, "2026-27", 3, 6)
    assert len(future) == 2
    assert set(future["gw"]) == {6}
    assert not future["finished"].any()
    assert future["kickoff"].notna().all()


def test_a_float_gameweek_column_is_coerced_not_astyped():
    """A2c: 2025-2026 writes "10.0" where 2026-2027 writes "10"."""
    floaty = FIXTURES_CSV.replace("\n2,2026-08-30", "\n2.0,2026-08-30")
    out = fixture_rows(floaty, "2025-26", 2, 2)
    assert set(out[out["tournament"] == "prem"]["gw"]) == {2}


def test_a_fixture_file_with_no_kickoff_column_is_dropped():
    out = fixture_rows(FIXTURES_CSV.replace("kickoff_time", "when"),
                       "2026-27", 3, 2)
    assert out.empty
    assert list(out.columns) == CI_FIXTURE_COLS


def test_elo_rows_come_off_the_fixture_file_per_club():
    out = elo_rows(FIXTURES_CSV, "2026-27", 3, 2)
    assert list(out.columns) == CI_ELO_COLS
    assert set(zip(out["team_code"], out["elo"])) == {(2, 1801.5),
                                                      (94, 1750.25)}


def test_a_season_whose_elo_is_blank_yields_no_elo_rows():
    """A3c: 2026-27's archive carries no Elo yet. That is a fact, not a bug."""
    blank = FIXTURES_CSV.replace("1801.5", "").replace("1750.25", "")
    out = elo_rows(blank, "2026-27", 3, 2)
    assert out.empty
    assert list(out.columns) == CI_ELO_COLS
