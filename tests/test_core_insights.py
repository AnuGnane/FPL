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
                                       PMS_COUNT_COLS, PMS_STAT_COLS,
                                       elo_rows, fixture_rows,
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


PMS_CSV_2026_BLANKS = (
    # The 2026-27 drift, in the proportions the live file has it: some played
    # rows blank, some filled, one unused substitute, and
    # defensive_contributions a header with nothing under it in GW1-2.
    "player_id,match_id,minutes_played,accurate_crosses,"
    "touches_opposition_box,final_third_passes,tackles_won,interceptions,"
    "blocks,clearances,recoveries,start_min,finish_min,"
    "defensive_contributions\n"
    "452,26-27-prem-leeds-united-vs-brentford,90,,,,,,,,,0,90,\n"
    "266,26-27-prem-leeds-united-vs-brentford,0,,,,,,,,,,,\n"
    "7,26-27-prem-leeds-united-vs-brentford,78,3,5,12,2,1,1,3,8,0,78,\n")


def test_a_blank_count_in_a_played_row_is_the_zero_the_archive_means():
    """The 2026-27 files leave a count blank where 2025-26 wrote 0 — 181 of
    310 played rows in GW1. Read literally that is a season in which two
    thirds of the league has an unknown number of crosses, and role_wb_share
    would report "unknown" for the season it was built to describe."""
    out = player_match_rows(PMS_CSV_2026_BLANKS, "2026-27", 3, 2,
                            player_code_map(PLAYERS_CSV))
    played = out[out["code"] == 208706].iloc[0]
    assert played["accurate_crosses"] == 0.0
    assert played["touches_opposition_box"] == 0.0
    assert played["recoveries"] == 0.0


def test_a_blank_count_in_an_unplayed_row_stays_unknown():
    """He recorded no crosses because he never came on. A zero there would
    put him in the denominator of every per-start rate as a real zero."""
    out = player_match_rows(PMS_CSV_2026_BLANKS, "2026-27", 3, 2,
                            player_code_map(PLAYERS_CSV))
    benched = out[out["code"] == 232413].iloc[0]
    assert pd.isna(benched["accurate_crosses"])
    assert pd.isna(benched["touches_opposition_box"])


def test_the_minute_columns_are_never_filled_with_zero():
    """``start_min`` is not a count. A blank means the archive did not record
    when he came on; filling it with 0 would assert that he started."""
    out = player_match_rows(PMS_CSV_2026_BLANKS, "2026-27", 3, 2,
                            player_code_map(PLAYERS_CSV))
    benched = out[out["code"] == 232413].iloc[0]
    assert pd.isna(benched["start_min"])
    assert pd.isna(benched["finish_min"])


def test_a_column_blank_for_every_row_is_unpublished_not_all_zero():
    """2026-27 GW1-2 carry ``defensive_contributions`` as a header with
    nothing under it. "The publisher has not filled this in yet" is not
    "every player recorded zero"."""
    out = player_match_rows(PMS_CSV_2026_BLANKS, "2026-27", 3, 2,
                            player_code_map(PLAYERS_CSV))
    assert out["defensive_contributions"].isna().all()


def test_a_real_zero_and_a_filled_blank_are_the_same_number():
    """The convention only matters if it agrees with the season that spells
    it out: 2025-26's explicit 0 and 2026-27's blank must read alike."""
    explicit = player_match_rows(
        PMS_CSV_2026_BLANKS.replace(",90,,,,,,,,,0,90,",
                                    ",90,0,0,0,0,0,0,0,0,0,90,"),
        "2025-26", 2, 2, player_code_map(PLAYERS_CSV))
    blank = player_match_rows(PMS_CSV_2026_BLANKS, "2026-27", 3, 2,
                              player_code_map(PLAYERS_CSV))
    for col in ("accurate_crosses", "touches_opposition_box", "recoveries"):
        assert (explicit[explicit["code"] == 208706][col].iloc[0]
                == blank[blank["code"] == 208706][col].iloc[0])


def test_pms_column_contracts_are_disjoint_and_complete():
    assert set(PMS_KEY_COLS).isdisjoint(PMS_STAT_COLS)
    assert CI_PLAYER_COLS[:4] == ["season", "season_idx", "gw", "code"]
    # The blank-means-zero rule applies to counts and to nothing else: the
    # minute columns and minutes_played itself are measurements, and a zero
    # written into one of them is a claim rather than a fill.
    assert set(PMS_COUNT_COLS) < set(PMS_STAT_COLS)
    assert set(PMS_COUNT_COLS).isdisjoint(
        {"minutes_played", "start_min", "finish_min"})


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


# ``test_a_float_gameweek_column_is_coerced_not_astyped`` stood here and was
# deleted in the T1-T6 review (2026-09-03) as vacuous by construction:
# ``fixture_rows`` stamps ``gw`` from its own argument and never reads the
# file's ``gameweek`` column, so a fixture that made that column a float
# string asserted nothing about anything. A2c's float/int drift is real, and
# the way it is handled is by not reading the column at all — a claim that
# belongs in ``fixture_rows``' docstring, where it now is, rather than in a
# test that cannot fail.


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


# --- Task 3: the collector and its readers -------------------------------

import pytest

from gaffer.data import store
from gaffer.data.core_insights import (ci_path, download_core_insights,
                                       load_core_insights, season_table_stats)


class _FakeHTTP:
    """An httpx.Client stand-in that serves a path -> text dict.

    Anything it is not given 404s the way the real archive does, which is what
    ``_cached_get`` turns into a printed skip.
    """

    def __init__(self, files: dict[str, str]):
        self.files = dict(files)
        self.asked: list[str] = []

    def get(self, url, **_kw):
        self.asked.append(url)
        path = url.split("/main/", 1)[-1]
        if path not in self.files:
            raise httpx.HTTPError(f"404 {path}")
        return _Resp(self.files[path])


class _Resp:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        return None

    def json(self):
        import json as _json
        return _json.loads(self.text)


import httpx  # noqa: E402 — imported after _FakeHTTP for readability


ARCHIVE = {
    "data/2026-2027/players.csv": PLAYERS_CSV,
    "data/2026-2027/teams.csv": "code,id,name,elo\n2,1,Leeds,\n",
    "data/2026-2027/By Gameweek/GW2/fixtures.csv": FIXTURES_CSV,
    "data/2026-2027/By Gameweek/GW2/playermatchstats.csv": PMS_CSV,
}

ARCHIVE_TREE = _tree(sorted(ARCHIVE))


@pytest.fixture()
def clone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_the_collector_writes_three_parquets_per_season(clone):
    http = _FakeHTTP(ARCHIVE)
    out = download_core_insights(["2026-27"], {"2026-27": 3},
                                 tree=ARCHIVE_TREE, client=http)
    assert out["2026-27"] == {"players": 2, "fixtures": 5, "elo": 2}
    for table in ("players", "fixtures", "elo"):
        assert store.exists(ci_path("2026-27", table))


def test_the_written_players_table_is_season_guarded_by_construction(clone):
    http = _FakeHTTP(ARCHIVE)
    download_core_insights(["2026-27"], {"2026-27": 3}, tree=ARCHIVE_TREE,
                           client=http)
    frame = load_core_insights("2026-27", "players")
    assert set(frame["season"]) == {"2026-27"}
    assert ci_path("2026-27", "players") == \
        "core_insights/2026-27/players.parquet"


def test_a_reader_for_a_season_never_collected_is_an_empty_typed_frame(clone):
    frame = load_core_insights("2019-20", "players")
    assert frame.empty
    assert list(frame.columns) == CI_PLAYER_COLS


def test_an_unreachable_archive_writes_nothing_and_does_not_raise(clone):
    out = download_core_insights(["2026-27"], {"2026-27": 3}, tree={},
                                 client=_FakeHTTP({}))
    assert out["2026-27"] == {"players": 0, "fixtures": 0, "elo": 0}
    assert not store.exists(ci_path("2026-27", "players"))


def test_a_season_the_archive_publishes_empty_writes_empty_tables(clone):
    tree = _tree(["data/2026-2027/players.csv", "data/2026-2027/teams.csv"])
    out = download_core_insights(
        ["2026-27"], {"2026-27": 3}, tree=tree,
        client=_FakeHTTP({"data/2026-2027/players.csv": PLAYERS_CSV,
                          "data/2026-2027/teams.csv": "code,id\n2,1\n"}))
    assert out["2026-27"] == {"players": 0, "fixtures": 0, "elo": 0}
    # Written, not skipped: "we looked and there was nothing" is a fact worth
    # banking, and the health line renders 0 rows rather than "never run".
    assert store.exists(ci_path("2026-27", "players"))
    assert load_core_insights("2026-27", "players").empty


def test_a_season_with_no_element_map_collects_no_player_rows(clone):
    """Without players.csv nothing can be joined to a code, so the player
    table is empty while fixtures and elo are unaffected."""
    files = {k: v for k, v in ARCHIVE.items()
             if k != "data/2026-2027/players.csv"}
    tree = _tree(sorted(files))
    out = download_core_insights(["2026-27"], {"2026-27": 3}, tree=tree,
                                 client=_FakeHTTP(files))
    assert out["2026-27"]["players"] == 0
    assert out["2026-27"]["fixtures"] == 5


def test_one_bad_gameweek_costs_one_gameweek(clone):
    files = dict(ARCHIVE)
    files["data/2026-2027/By Gameweek/GW3/playermatchstats.csv"] = "gibberish"
    tree = _tree(sorted(files))
    out = download_core_insights(["2026-27"], {"2026-27": 3}, tree=tree,
                                 client=_FakeHTTP(files))
    assert out["2026-27"]["players"] == 2


def test_season_table_stats_is_what_the_health_line_renders(clone):
    http = _FakeHTTP(ARCHIVE)
    download_core_insights(["2026-27"], {"2026-27": 3}, tree=ARCHIVE_TREE,
                           client=http)
    stats = season_table_stats("2026-27")
    assert stats["players"]["rows"] == 2
    assert stats["fixtures"]["rows"] == 5
    assert stats["fixtures"]["latest"] == "2026-10-10"
    assert stats["elo"]["rows"] == 2


def test_season_table_stats_on_a_cold_clone_says_never(clone):
    stats = season_table_stats("2026-27")
    assert stats == {"players": {"rows": 0, "latest": None},
                     "fixtures": {"rows": 0, "latest": None},
                     "elo": {"rows": 0, "latest": None}}


# --- Task 4: the command and its plist -----------------------------------

from pathlib import Path as _Path


def test_the_cli_exposes_core_insights():
    from typer.main import get_command

    from gaffer.cli import app

    assert "core-insights" in get_command(app).commands


def test_the_plist_runs_the_command_twice_a_day():
    text = _Path("scripts/com.gaffer.core-insights.plist").read_text()
    assert "com.gaffer.core-insights" in text
    assert "uv run gaffer core-insights" in text
    assert text.count("<key>Hour</key><integer>6</integer>") == 1
    assert text.count("<key>Hour</key><integer>18</integer>") == 1
    assert text.count("<key>Minute</key><integer>30</integer>") == 2


def test_the_installer_installs_it():
    text = _Path("scripts/install_automation.sh").read_text()
    assert "core-insights" in text


def test_the_installer_loop_names_every_plist_and_no_others():
    """The loop is a hand-maintained list beside a directory of files, which
    is exactly the pair that drifts: a plist nobody installs is a job that
    silently never runs, and a name with no plist makes the installer exit
    non-zero half way through and leave the rest unloaded."""
    line = next(ln for ln in
                _Path("scripts/install_automation.sh").read_text().splitlines()
                if ln.startswith("for name in "))
    installed = set(line.removeprefix("for name in ").split(";")[0].split())
    shipped = {p.stem.removeprefix("com.gaffer.")
               for p in _Path("scripts").glob("com.gaffer.*.plist")}
    assert installed == shipped


# --- T1-T6 review: the cache, the season map, and the atomic write -------

from gaffer.data.core_insights import (CI_CACHE,  # noqa: E402
                                       fetch_csv, hot_gameweeks,
                                       season_index_map)

FINISHED_FIXTURES = (
    "gameweek,kickoff_time,home_team,home_team_elo,home_score,away_score,"
    "away_team,away_team_elo,finished,match_id,tournament\n"
    "2,2026-08-30T13:00:00,2.0,1801.5,1,1,94.0,1750.25,True,m1,prem\n")

LIVE_FIXTURES = FINISHED_FIXTURES.replace(",True,m1", ",False,m1")


def _bundle(gws, prefix="data/2026-2027/By Gameweek"):
    return {"players": None, "teams": None,
            "fixtures": {gw: f"{prefix}/GW{gw}/fixtures.csv" for gw in gws},
            "playermatchstats": {gw: f"{prefix}/GW{gw}/playermatchstats.csv"
                                 for gw in gws}}


def _bank(cache: _Path, path: str, text: str) -> None:
    dest = cache / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text)


def test_a_finished_gameweek_is_cold_and_is_never_fetched_twice(tmp_path):
    bundle = _bundle([1])
    _bank(tmp_path, bundle["fixtures"][1], FINISHED_FIXTURES)
    assert hot_gameweeks(bundle, tmp_path) == set()


def test_the_gameweek_being_played_is_hot_on_every_run(tmp_path):
    """The one that matters. "Cached forever" meant the collector could never
    see the week in progress, which is the week the tool is answering about."""
    bundle = _bundle([1, 2])
    _bank(tmp_path, bundle["fixtures"][1], FINISHED_FIXTURES)
    _bank(tmp_path, bundle["fixtures"][2], LIVE_FIXTURES)
    assert hot_gameweeks(bundle, tmp_path) == {2}


def test_a_gameweek_with_nothing_cached_is_hot(tmp_path):
    """"No readable cached fixture list to judge it by" is the docstring's own
    second clause and the module docstring's too, and it was the one case the
    code answered the other way: an uncached gameweek fell through `continue`
    and came back cold. Harmless today — `fetch_csv` takes the same branch for
    `refresh=True` on a file it has not got — but a caller reading the set as
    "the weeks this run will go and look at" was reading a lie, and the fix is
    to make the code say what both docstrings promise."""
    assert hot_gameweeks(_bundle([3]), tmp_path) == {3}


def test_an_unreadable_cached_fixture_list_is_hot_not_trusted(tmp_path):
    bundle = _bundle([1])
    _bank(tmp_path, bundle["fixtures"][1], "not a csv at all")
    assert hot_gameweeks(bundle, tmp_path) == {1}


def test_refresh_forces_the_last_n_gameweeks_however_final_they_are(tmp_path):
    bundle = _bundle([1, 2, 3])
    for gw in (1, 2, 3):
        _bank(tmp_path, bundle["fixtures"][gw], FINISHED_FIXTURES)
    assert hot_gameweeks(bundle, tmp_path, refresh=2) == {2, 3}


def test_a_hot_file_is_re_fetched_and_a_cold_one_is_not(tmp_path):
    path = "data/2026-2027/By Gameweek/GW2/fixtures.csv"
    _bank(tmp_path, path, "stale\n")
    http = _FakeHTTP({path: FINISHED_FIXTURES})
    assert fetch_csv(path, http, tmp_path) == "stale\n"
    assert http.asked == []
    assert fetch_csv(path, http, tmp_path, refresh=True) == FINISHED_FIXTURES
    assert len(http.asked) == 1
    assert (tmp_path / path).read_text() == FINISHED_FIXTURES


def test_a_failed_re_fetch_keeps_the_copy_it_had(tmp_path):
    """Freshness is worth a request and never a deletion: the collector's
    other rail is that an unreachable archive truncates nothing."""
    path = "data/2026-2027/By Gameweek/GW2/fixtures.csv"
    _bank(tmp_path, path, FINISHED_FIXTURES)
    got = fetch_csv(path, http=_FakeHTTP({}), cache_dir=tmp_path,
                    refresh=True)
    assert got == FINISHED_FIXTURES
    assert (tmp_path / path).read_text() == FINISHED_FIXTURES


def test_the_collector_re_reads_an_unfinished_gameweek_on_the_next_run(clone):
    live = dict(ARCHIVE)
    live["data/2026-2027/By Gameweek/GW2/fixtures.csv"] = LIVE_FIXTURES
    http = _FakeHTTP(live)
    download_core_insights(["2026-27"], {"2026-27": 3},
                           tree=ARCHIVE_TREE, client=http)
    first = len(http.asked)
    download_core_insights(["2026-27"], {"2026-27": 3},
                           tree=ARCHIVE_TREE, client=http)
    # The element map and GW2's two files, every run — and nothing else.
    assert len(http.asked) - first == 3


def test_the_collector_leaves_a_finished_gameweek_alone_on_the_next_run(clone):
    # ARCHIVE's fixture file carries an unplayed GW6 tie, which is what makes
    # that gameweek hot for ever; this is the week that has actually finished.
    done = dict(ARCHIVE)
    done["data/2026-2027/By Gameweek/GW2/fixtures.csv"] = FINISHED_FIXTURES
    http = _FakeHTTP(done)
    download_core_insights(["2026-27"], {"2026-27": 3},
                           tree=ARCHIVE_TREE, client=http)
    first = len(http.asked)
    download_core_insights(["2026-27"], {"2026-27": 3},
                           tree=ARCHIVE_TREE, client=http)
    # Only the element map, which changes all season as players are added.
    assert len(http.asked) - first == 1


def test_a_write_that_dies_mid_parquet_leaves_the_previous_one_whole(
        clone, monkeypatch):
    """W1's house rule, on the collector's own output: a reader must never see
    half a parquet, and a killed run must not cost the last good one."""
    download_core_insights(["2026-27"], {"2026-27": 3}, tree=ARCHIVE_TREE,
                           client=_FakeHTTP(ARCHIVE))
    before = load_core_insights("2026-27", "players")
    assert len(before) == 2

    real = store.save

    def _explode(frame, rel):
        real(frame, rel)
        raise OSError("disk full")

    monkeypatch.setattr(store, "save", _explode)
    with pytest.raises(OSError):
        download_core_insights(["2026-27"], {"2026-27": 3}, tree=ARCHIVE_TREE,
                               client=_FakeHTTP(ARCHIVE))
    # Restored by hand rather than with ``monkeypatch.undo``, which would also
    # undo the ``clone`` fixture's chdir and leave the assertions below
    # reading the repository's own data directory.
    monkeypatch.setattr(store, "save", real)
    assert len(load_core_insights("2026-27", "players")) == 2
    assert not list((tmp := _Path("data/core_insights")).glob("**/*.tmp*")), \
        f"a temp file was left behind under {tmp}"


def test_the_season_index_comes_from_history_not_from_the_config_order(clone):
    """The arm builders join on season_idx, and the serving frame has no
    `season` column to join on instead — so the index is the join key, and a
    key derived from a config list's *position* moves when somebody reorders
    that list."""
    store.save(pd.DataFrame({"season": ["2022-23", "2023-24", "2024-25"],
                             "season_idx": [0, 1, 2]}),
               "history/player_gw.parquet")
    # A config that names them in a different order, and one season history
    # has never seen.
    out = season_index_map(["2024-25", "2022-23", "2023-24", "2026-27"],
                           "2026-27")
    assert out == {"2022-23": 0, "2023-24": 1, "2024-25": 2, "2026-27": 3}


def test_the_season_index_falls_back_to_position_before_any_history(clone):
    out = season_index_map(["2024-25", "2025-26"], "2025-26")
    assert out == {"2024-25": 0, "2025-26": 1}


def test_the_cache_lives_where_the_docstring_says_it_does():
    assert str(CI_CACHE) == "data/raw/core_insights"


# --- W4 review round: the season list and the refused tree ----------------


def test_the_current_season_named_twice_is_collected_once(monkeypatch):
    """`train_seasons` routinely already names the season being played — the
    shipped `config.example.toml` does — and appending `current_season` to it
    unconditionally asked the archive for that season twice: every file
    fetched again, every parquet written twice, and the printed line claiming
    one more season than exists."""
    from typer.testing import CliRunner

    from gaffer.cli import app
    from gaffer.config import Config
    from gaffer.data import core_insights as ci_mod

    seen = {}

    def fake(seasons, indexes, *a, **k):
        seen["seasons"] = list(seasons)
        seen["indexes"] = dict(indexes)
        return {s: {"players": 1, "fixtures": 1, "elo": 1} for s in seasons}

    monkeypatch.setattr(ci_mod, "download_core_insights", fake)
    monkeypatch.setattr(ci_mod, "season_index_map",
                        lambda seasons, cur: {s: i
                                              for i, s in enumerate(seasons)})
    monkeypatch.setattr("gaffer.config.load_config", lambda *a, **k: Config(
        entry_id=1, league_id=2,
        train_seasons=["2024-25", "2025-26", "2026-27"],
        current_season="2026-27"))

    result = CliRunner().invoke(app, ["core-insights"])
    assert result.exit_code == 0, result.output
    assert seen["seasons"] == ["2024-25", "2025-26", "2026-27"]
    assert "across 3 seasons" in result.output


def test_a_current_season_missing_from_train_seasons_is_still_collected(
        monkeypatch):
    """Dedup must not become a filter: the season being played is the one the
    fixture table is a prediction-time input for, so it is collected whether
    or not the training list happens to name it."""
    from typer.testing import CliRunner

    from gaffer.cli import app
    from gaffer.config import Config
    from gaffer.data import core_insights as ci_mod

    seen = {}
    monkeypatch.setattr(ci_mod, "download_core_insights",
                        lambda seasons, indexes, *a, **k:
                        (seen.update(seasons=list(seasons)),
                         {s: {"players": 1} for s in seasons})[1])
    monkeypatch.setattr(ci_mod, "season_index_map",
                        lambda seasons, cur: {s: i
                                              for i, s in enumerate(seasons)})
    monkeypatch.setattr("gaffer.config.load_config", lambda *a, **k: Config(
        entry_id=1, league_id=2, train_seasons=["2024-25", "2025-26"],
        current_season="2026-27"))

    result = CliRunner().invoke(app, ["core-insights"])
    assert result.exit_code == 0, result.output
    assert seen["seasons"] == ["2024-25", "2025-26", "2026-27"]


def test_a_tree_listing_refused_by_github_is_named_not_blamed_on_the_archive(
        clone):
    """GitHub answers a rate limit or a moved repository with a 403 and a JSON
    body carrying `message` and no `tree`. That parses, so `fetch_tree`
    returned it happily, `ci_paths_from_tree` found no paths in it, and the
    caller printed "the archive published nothing reachable" — blaming the
    publisher for our own throttling. The distinction is the whole diagnosis:
    one is waited out, the other is reported."""
    from gaffer.data.core_insights import fetch_tree

    class _Refused:
        def get(self, url, **_kw):
            return _Resp('{"message": "API rate limit exceeded for 1.2.3.4.",'
                         ' "documentation_url": "https://docs.github.com/"}')

    out = fetch_tree(client=_Refused())
    assert out == {}


def test_a_refused_tree_prints_the_message_github_gave(clone, capsys):
    from gaffer.data.core_insights import fetch_tree

    class _Refused:
        def get(self, url, **_kw):
            return _Resp('{"message": "API rate limit exceeded for 1.2.3.4."}')

    fetch_tree(client=_Refused())
    printed = capsys.readouterr().out
    assert "rate limit exceeded" in printed
    assert "core-insights" in printed


def test_a_real_tree_is_not_mistaken_for_a_refusal(clone):
    """The guard reads `message` on the *listing* object; a tree whose paths
    happen to include the word must still come through."""
    from gaffer.data.core_insights import fetch_tree

    class _Ok:
        def get(self, url, **_kw):
            return _Resp('{"tree": [{"path": "data/2026-2027/players.csv"}]}')

    assert fetch_tree(client=_Ok())["tree"][0]["path"].endswith("players.csv")
