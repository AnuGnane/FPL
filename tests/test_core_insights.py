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
