"""Cup fixture ingestion. No network: every fetch runs through
httpx.MockTransport against the committed snapshots in tests/data/cups/."""

from __future__ import annotations

from pathlib import Path

import httpx
import pandas as pd

from gaffer.data.cups import (CUP_TOURNAMENTS, cup_match_rows,
                              cup_paths_from_tree, download_cup_matches,
                              team_code_map)

FIXTURES = Path(__file__).parent / "data" / "cups"


def _matches_csv() -> str:
    return (FIXTURES / "matches_gw2.csv").read_text()


def _teams_csv() -> str:
    return (FIXTURES / "teams.csv").read_text()


def test_team_code_map_prefers_the_published_code_column():
    codes = team_code_map(_teams_csv())
    assert codes[1] == 3        # Arsenal: season id 1 -> stable code 3
    assert codes[14] == 43      # Man City
    assert len(codes) == 8


def test_team_code_map_falls_back_to_names_when_no_code_column():
    """A season table that ships only ids and names still resolves, through
    the caller's {bootstrap name: code} table — the same table
    build_match_odds already threads through for football-data."""
    csv = "id,name,short_name\n1,Arsenal,ARS\n14,Man City,MCI\n"
    codes = team_code_map(csv, names={"Arsenal": 3, "Man City": 43})
    assert codes == {1: 3, 14: 43}


def test_cup_match_rows_emits_one_row_per_league_team_per_match():
    rows = cup_match_rows(_matches_csv(), season="2025-26", season_idx=3,
                          codes=team_code_map(_teams_csv()))
    # Fulham away at Bristol City: one row, because Bristol City has no id.
    # Brentford v Bournemouth: two. Arsenal v Port Vale: one. City v Chelsea:
    # two. Everton v Liverpool has no kickoff and is dropped. Grimsby v
    # Walsall has no league club at all and is dropped.
    assert len(rows) == 6
    assert set(rows.columns) == {"season", "season_idx", "tournament",
                                 "date", "team_code"}
    assert set(rows["team_code"]) == {54, 94, 91, 3, 43, 8}
    assert rows["season_idx"].unique().tolist() == [3]
    assert rows["tournament"].unique().tolist() == ["efl-cup"]


def test_cup_match_rows_dates_are_plain_uk_dates():
    """The congestion join keys on a date, and a tz-aware timestamp against a
    plain date matches nothing while looking fine — the same trap
    merge_understat_team documents."""
    rows = cup_match_rows(_matches_csv(), season="2025-26", season_idx=3,
                          codes=team_code_map(_teams_csv()))
    fulham = rows[rows["team_code"] == 54]["date"].iloc[0]
    assert fulham == pd.Timestamp("2025-08-27").date()


def test_cup_match_rows_survives_an_empty_file():
    rows = cup_match_rows("gameweek,kickoff_time\n", season="2025-26",
                          season_idx=3, codes={})
    assert rows.empty
    assert list(rows.columns) == ["season", "season_idx", "tournament",
                                  "date", "team_code"]


def _tree_payload() -> dict:
    return {"tree": [
        {"path": "data/2025-2026/teams.csv"},
        {"path": "data/2025-2026/By Tournament/EFL Cup/GW2/matches.csv"},
        {"path": "data/2025-2026/By Tournament/EFL Cup/GW2/shots.csv"},
        {"path": "data/2025-2026/By Tournament/Premier League/GW2/matches.csv"},
        {"path": "data/2024-2025/By Tournament/Europa League/GW7/matches.csv"},
        {"path": "data/2026-2027/By Tournament/EFL Cup/GW3/matches.csv"},
    ]}


def test_cup_paths_from_tree_keeps_only_cup_matches_for_wanted_seasons():
    paths = cup_paths_from_tree(_tree_payload(), ["2025-26"])
    assert paths == [
        "data/2025-2026/By Tournament/EFL Cup/GW2/matches.csv"]
    both = cup_paths_from_tree(_tree_payload(), ["2024-25", "2025-26"])
    assert len(both) == 2
    assert all("Premier League" not in p for p in both)


def _handler(calls: list):
    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "api.github.com" in str(request.url):
            return httpx.Response(200, json=_tree_payload())
        if str(request.url).endswith("teams.csv"):
            return httpx.Response(200, text=_teams_csv())
        return httpx.Response(200, text=_matches_csv())
    return handle


def test_download_cup_matches_writes_a_parquet_and_caches_each_file(tmp_path,
                                                                    monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    calls: list[str] = []
    client = httpx.Client(transport=httpx.MockTransport(_handler(calls)))
    df = download_cup_matches(["2025-26"], {"2025-26": 3},
                              cache_dir=tmp_path / "raw", client=client)
    assert len(df) == 6
    assert set(df["team_code"]) == {54, 94, 91, 3, 43, 8}
    assert (tmp_path / "history" / "cup_matches.parquet").exists()
    before = len(calls)

    # Second run: everything is on disk, so only the tree is re-read.
    download_cup_matches(["2025-26"], {"2025-26": 3},
                         cache_dir=tmp_path / "raw", client=client)
    assert len(calls) == before + 1


def test_download_cup_matches_skips_a_file_that_404s(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)

    def handle(request: httpx.Request) -> httpx.Response:
        if "api.github.com" in str(request.url):
            return httpx.Response(200, json=_tree_payload())
        if str(request.url).endswith("teams.csv"):
            return httpx.Response(200, text=_teams_csv())
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handle))
    df = download_cup_matches(["2025-26"], {"2025-26": 3},
                              cache_dir=tmp_path / "raw", client=client)
    assert df.empty
    assert list(df.columns) == ["season", "season_idx", "tournament",
                               "date", "team_code"]


def test_load_cup_matches_is_none_without_a_parquet(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod
    from gaffer.data.cups import load_cup_matches

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    assert load_cup_matches() is None
