import pandas as pd
import pytest

from gaffer.data.match_odds import (FOOTBALL_DATA_ALIASES, PRICE_TRIPLES,
                                    TOTALS_PAIRS, parse_football_data,
                                    resolve_fd_team)
from gaffer.errors import GafferError


def _csv_rows(extra: dict | None = None) -> pd.DataFrame:
    """Two matches in football-data's own column vocabulary."""
    base = {
        "Date": ["16/08/2024", "17/08/2024"],
        "HomeTeam": ["Man United", "Nott'm Forest"],
        "AwayTeam": ["Wolves", "Bournemouth"],
        "AvgCH": [1.80, 2.30], "AvgCD": [3.80, 3.30], "AvgCA": [4.50, 3.20],
        "AvgC>2.5": [1.90, 2.05], "AvgC<2.5": [1.95, 1.80],
    }
    base.update(extra or {})
    return pd.DataFrame(base)


def test_resolve_fd_team_maps_football_data_short_names():
    assert resolve_fd_team("Man United") == "Man Utd"
    assert resolve_fd_team("Nott'm Forest") == "Nott'm Forest"
    assert resolve_fd_team("Wolves") == "Wolves"
    assert resolve_fd_team("Spurs") == "Spurs"


def test_resolve_fd_team_raises_on_an_unknown_name():
    """A silently mismatched club attaches one team's odds to another, which
    is far worse than losing the odds for a season."""
    with pytest.raises(GafferError) as exc:
        resolve_fd_team("Barnsley Athletic")
    assert "FOOTBALL_DATA_ALIASES" in str(exc.value)


def test_every_alias_target_is_an_fpl_bootstrap_name():
    from gaffer.data.odds import TEAM_ALIASES

    fpl_names = set(TEAM_ALIASES.values())
    unknown = sorted(set(FOOTBALL_DATA_ALIASES.values()) - fpl_names)
    assert unknown == []


def test_parse_football_data_devigs_the_closing_triple_with_shin():
    from gaffer.data.odds import shin_devig

    out = parse_football_data(_csv_rows(), season="2024-25", season_idx=2)
    want = shin_devig([1.80, 3.80, 4.50])
    assert abs(out.loc[0, "p_home"] - want[0]) < 1e-12
    assert abs(out.loc[0, "p_draw"] - want[1]) < 1e-12
    assert abs(out.loc[0, "p_away"] - want[2]) < 1e-12
    assert abs(out.loc[0, "p_home"] + out.loc[0, "p_draw"]
               + out.loc[0, "p_away"] - 1.0) < 1e-12


def test_parse_football_data_devigs_the_totals_pair():
    from gaffer.data.odds import devig

    out = parse_football_data(_csv_rows(), season="2024-25", season_idx=2)
    assert abs(out.loc[0, "p_over25"] - devig([1.90, 1.95])[0]) < 1e-12


def test_parse_football_data_maps_names_and_dates():
    out = parse_football_data(_csv_rows(), season="2024-25", season_idx=2)
    assert list(out["home_name"]) == ["Man Utd", "Nott'm Forest"]
    assert list(out["away_name"]) == ["Wolves", "Bournemouth"]
    assert list(out["date"]) == [pd.Timestamp("2024-08-16").date(),
                                 pd.Timestamp("2024-08-17").date()]
    assert set(out["season"]) == {"2024-25"} and set(out["season_idx"]) == {2}


def test_parse_football_data_accepts_four_digit_years_too():
    """Older seasons use dd/mm/yy, newer ones dd/mm/yyyy; both appear in the
    same archive."""
    rows = _csv_rows({"Date": ["16/08/24", "17/08/24"]})
    out = parse_football_data(rows, season="2024-25", season_idx=2)
    assert out.loc[0, "date"] == pd.Timestamp("2024-08-16").date()


def test_parse_football_data_falls_back_down_the_price_chain():
    """Closing averages are the first choice; a season that predates them
    still has to parse."""
    rows = _csv_rows().drop(columns=["AvgCH", "AvgCD", "AvgCA"])
    rows["B365H"], rows["B365D"], rows["B365A"] = [1.80, 2.30], [3.80, 3.30], [4.50, 3.20]
    out = parse_football_data(rows, season="2020-21", season_idx=0)
    assert len(out) == 2
    assert out["p_home"].notna().all()


def test_parse_football_data_takes_the_first_fully_present_triple():
    """A partially-populated preferred triple must not win over a complete
    later one — half a market is not a market."""
    rows = _csv_rows()
    rows.loc[0, "AvgCH"] = float("nan")
    rows["AvgH"], rows["AvgD"], rows["AvgA"] = [1.70, 2.20], [3.90, 3.40], [4.60, 3.30]
    out = parse_football_data(rows, season="2024-25", season_idx=2)
    from gaffer.data.odds import shin_devig
    assert abs(out.loc[0, "p_home"] - shin_devig([1.70, 3.90, 4.60])[0]) < 1e-12


def test_parse_football_data_without_any_price_triple_returns_empty():
    rows = _csv_rows().drop(columns=["AvgCH", "AvgCD", "AvgCA"])
    out = parse_football_data(rows, season="2024-25", season_idx=2)
    assert out.empty
    assert list(out.columns) == ["season", "season_idx", "date", "home_name",
                                 "away_name", "p_home", "p_draw", "p_away",
                                 "p_over25"]


def test_parse_football_data_without_a_totals_pair_uses_the_neutral_prior():
    from gaffer.data.odds import NEUTRAL_P_OVER25

    rows = _csv_rows().drop(columns=["AvgC>2.5", "AvgC<2.5"])
    out = parse_football_data(rows, season="2024-25", season_idx=2)
    assert (out["p_over25"] == NEUTRAL_P_OVER25).all()


def test_parse_football_data_drops_blank_trailing_rows():
    """football-data ships trailing all-empty rows in most season files."""
    rows = _csv_rows()
    blank = pd.DataFrame([{c: float("nan") for c in rows.columns}])
    blank["HomeTeam"] = None
    out = parse_football_data(pd.concat([rows, blank], ignore_index=True),
                              season="2024-25", season_idx=2)
    assert len(out) == 2


def test_price_and_totals_preference_chains_are_ordered_closing_first():
    assert PRICE_TRIPLES[0] == ("AvgCH", "AvgCD", "AvgCA")
    assert TOTALS_PAIRS[0] == ("AvgC>2.5", "AvgC<2.5")


import httpx

from gaffer.data.match_odds import (MATCH_ODDS_PATH, build_match_odds,
                                    download_season, join_to_fixtures,
                                    season_slug)

_CSV = ("Date,HomeTeam,AwayTeam,AvgCH,AvgCD,AvgCA,AvgC>2.5,AvgC<2.5\n"
        "16/08/2024,Man United,Wolves,1.80,3.80,4.50,1.90,1.95\n"
        "17/08/2024,Nott'm Forest,Bournemouth,2.30,3.30,3.20,2.05,1.80\n")


def _fixtures() -> pd.DataFrame:
    return pd.DataFrame([
        {"season_idx": 2, "gw": 1, "kickoff_time": "2024-08-16T19:00:00Z",
         "home_code": 1, "away_code": 39, "home_goals": 1, "away_goals": 0},
        {"season_idx": 2, "gw": 1, "kickoff_time": "2024-08-17T14:00:00Z",
         "home_code": 17, "away_code": 91, "home_goals": 1, "away_goals": 1},
        {"season_idx": 2, "gw": 2, "kickoff_time": "2024-08-24T14:00:00Z",
         "home_code": 39, "away_code": 17, "home_goals": 2, "away_goals": 2},
    ])


_NAME_TO_CODE = {"Man Utd": 1, "Wolves": 39, "Nott'm Forest": 17,
                 "Bournemouth": 91}


def test_season_slug_is_the_two_year_pair():
    assert season_slug("2024-25") == "2425"
    assert season_slug("2020-21") == "2021"


def test_download_season_caches_and_does_not_refetch_a_finished_season(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        assert str(request.url) == (
            "https://www.football-data.co.uk/mmz4281/2425/E0.csv")
        return httpx.Response(200, text=_CSV)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    first = download_season("2024-25", cache_dir=tmp_path, client=client)
    second = download_season("2024-25", cache_dir=tmp_path, client=client)
    assert calls["n"] == 1
    assert len(first) == len(second) == 2
    assert (tmp_path / "2024-25" / "E0.csv").exists()


def test_download_season_refetches_the_current_season(tmp_path):
    """The running season's file grows every week; a cached copy is stale by
    definition."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, text=_CSV)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    download_season("2024-25", cache_dir=tmp_path, client=client, refresh=True)
    download_season("2024-25", cache_dir=tmp_path, client=client, refresh=True)
    assert calls["n"] == 2


def test_download_season_on_a_missing_file_returns_none(tmp_path):
    """A season the archive has not published yet must not fail a backfill."""
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    assert download_season("2030-31", cache_dir=tmp_path, client=client) is None


def test_join_to_fixtures_matches_on_date_and_both_team_codes():
    parsed = parse_football_data(_csv_rows(), season="2024-25", season_idx=2)
    out, report = join_to_fixtures(parsed, _fixtures(), _NAME_TO_CODE)
    assert list(out.columns) == ["season_idx", "gw", "kickoff_time",
                                 "home_code", "away_code", "p_home", "p_draw",
                                 "p_away", "p_over25"]
    assert list(out["home_code"]) == [1, 17]
    assert list(out["gw"]) == [1, 1]
    assert report == {"rows": 2, "matched": 2, "unmatched": 0}


def test_join_to_fixtures_counts_unmatched_rows_without_raising():
    """A cup game, a postponement, or a club we cannot code must cost that
    row and nothing else."""
    parsed = parse_football_data(_csv_rows(), season="2024-25", season_idx=2)
    out, report = join_to_fixtures(parsed, _fixtures(),
                                   {"Man Utd": 1, "Wolves": 39})
    assert len(out) == 1
    assert report == {"rows": 2, "matched": 1, "unmatched": 1}


def test_join_to_fixtures_uses_uk_local_dates():
    """A 20:00 UK kickoff in summer is 19:00 UTC on the same day, but a
    23:00 one would roll over — football-data stamps UK dates, so the
    comparison has to be made in UK time."""
    parsed = parse_football_data(
        _csv_rows({"Date": ["16/08/2024", "17/08/2024"]}),
        season="2024-25", season_idx=2)
    fx = _fixtures()
    fx.loc[0, "kickoff_time"] = "2024-08-16T23:30:00Z"   # 00:30 UK, 17 Aug
    out, report = join_to_fixtures(parsed, fx, _NAME_TO_CODE)
    assert report["unmatched"] == 1


def test_join_to_fixtures_keeps_a_double_gameweek_apart():
    """Date + both team codes is unique even when a team plays twice in one
    gameweek."""
    rows = _csv_rows({"Date": ["16/08/2024", "24/08/2024"],
                      "HomeTeam": ["Man United", "Wolves"],
                      "AwayTeam": ["Wolves", "Nott'm Forest"]})
    parsed = parse_football_data(rows, season="2024-25", season_idx=2)
    out, _ = join_to_fixtures(parsed, _fixtures(), _NAME_TO_CODE)
    assert list(out["gw"]) == [1, 2]


def test_join_to_fixtures_bridges_an_fpl_club_rename():
    """FPL called the club "Ipswich" in 2024-25 and "Ipswich Town" later; the
    alias tables carry the current name, so the older season's name table has
    to be reached through the rename bridge or every row drops."""
    rows = _csv_rows({"HomeTeam": ["Ipswich", "Nott'm Forest"],
                      "AwayTeam": ["Wolves", "Bournemouth"]})
    parsed = parse_football_data(rows, season="2024-25", season_idx=2)
    assert list(parsed["home_name"]) == ["Ipswich Town", "Nott'm Forest"]
    names = dict(_NAME_TO_CODE)
    names.pop("Man Utd")
    names["Ipswich"] = 1          # the 2024-25 bootstrap's spelling
    out, report = join_to_fixtures(parsed, _fixtures(), names)
    assert report == {"rows": 2, "matched": 2, "unmatched": 0}
    assert list(out["home_code"]) == [1, 17]


def test_join_to_fixtures_still_drops_a_club_no_table_knows():
    """The rename bridge must not turn a genuinely unknown club into a
    match."""
    parsed = parse_football_data(_csv_rows(), season="2024-25", season_idx=2)
    out, report = join_to_fixtures(parsed, _fixtures(),
                                   {"Man Utd": 1, "Wolves": 39})
    assert len(out) == 1
    assert report == {"rows": 2, "matched": 1, "unmatched": 1}


def test_build_match_odds_writes_the_parquet(tmp_path, monkeypatch):
    import gaffer.data.store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=_CSV)))
    out = build_match_odds(["2024-25"], _fixtures(), {"2024-25": _NAME_TO_CODE},
                           cache_dir=tmp_path / "raw", client=client,
                           season_indexes={"2024-25": 2})
    assert len(out) == 2
    assert (tmp_path / MATCH_ODDS_PATH).exists()


def test_build_match_odds_survives_a_season_the_archive_lacks(tmp_path,
                                                              monkeypatch):
    import gaffer.data.store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)

    def handler(request):
        if "/2425/" in str(request.url):
            return httpx.Response(200, text=_CSV)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = build_match_odds(["2023-24", "2024-25"], _fixtures(),
                           {"2024-25": _NAME_TO_CODE}, cache_dir=tmp_path / "raw",
                           client=client,
                           season_indexes={"2023-24": 1, "2024-25": 2})
    assert len(out) == 2
