import pandas as pd
import pytest

from gaffer.data.names import normalize_name
from gaffer.data.understat import (match_player_rows, league_matches,
                                   team_match_rows)
from gaffer.errors import GafferError


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
    out = league_matches(_DATES)
    assert list(out["match_id"]) == ["18001", "18002"]
    assert list(out["is_result"]) == [True, False]
    assert out.loc[0, "date"] == pd.Timestamp("2024-08-16").date()
    assert out.loc[0, "home_team"] == "Manchester United"


def test_league_matches_on_an_empty_season_is_an_empty_frame():
    out = league_matches([])
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
    out = team_match_rows(_TEAMS, season="2024-25", season_idx=2)
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
    out = team_match_rows(teams, season="2024-25", season_idx=2)
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


def _match() -> dict:
    """What getMatchData returns: rosters and shots side by side."""
    return {"rosters": _ROSTER, "shots": _SHOTS, "tmpl": "..."}


def test_match_player_rows_carries_the_marginal_understat_stats():
    out = match_player_rows(_match(), match_id="18001",
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
    out = match_player_rows(_match(), match_id="18001",
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
    out = match_player_rows({"rosters": roster, "shots": {"h": [], "a": []}},
                            match_id="18001",
                            date=pd.Timestamp("2024-08-16").date(),
                            home_team="Manchester United",
                            away_team="Wolves")
    assert out.loc[0, "us_npxg"] == 0.0


def test_match_player_rows_on_an_empty_roster_is_an_empty_frame():
    match = {"rosters": {"h": {}, "a": {}}, "shots": {"h": [], "a": []}}
    out = match_player_rows(match, match_id="18001",
                            date=pd.Timestamp("2024-08-16").date(),
                            home_team="A", away_team="B")
    assert out.empty


# --- UnderstatClient ------------------------------------------------------

import httpx

from gaffer.data.understat import UnderstatClient


def _http(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


_LEAGUE = {"dates": _DATES, "teams": _TEAMS, "players": []}


def test_league_data_requests_the_json_endpoint(tmp_path):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        return httpx.Response(200, json=_LEAGUE)

    client = UnderstatClient(client=_http(handler), cache_dir=tmp_path,
                             sleep=0.0)
    out = client.league_matches("2024-25")
    assert seen["url"] == "https://understat.com/getLeagueData/EPL/2024"
    assert list(out["match_id"]) == ["18001", "18002"]


def test_the_default_client_announces_itself_as_an_xhr(tmp_path):
    """The JSON endpoints answer the site's own ajax calls; without the
    header understat serves a page instead of the payload."""
    headers = UnderstatClient(cache_dir=tmp_path)._http.headers
    assert headers["X-Requested-With"] == "XMLHttpRequest"
    assert "gaffer" in headers["User-Agent"]


def test_league_payload_is_fetched_once_per_season(tmp_path):
    """Fixtures and team history come out of the same document — asking for
    both must not cost understat two downloads."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json=_LEAGUE)

    client = UnderstatClient(client=_http(handler), cache_dir=tmp_path,
                             sleep=0.0)
    assert len(client.league_matches("2024-25")) == 2
    assert len(client.team_history("2024-25", season_idx=2)) == 2
    assert calls["n"] == 1


def test_a_league_payload_without_dates_raises(tmp_path):
    """A season with no fixtures is an empty list; a missing key means
    understat changed its endpoint, and that must not look like no data."""
    client = UnderstatClient(
        client=_http(lambda r: httpx.Response(200, json={"players": []})),
        cache_dir=tmp_path, sleep=0.0)
    with pytest.raises(GafferError) as exc:
        client.league_matches("2024-25")
    assert "dates" in str(exc.value)


def test_an_empty_season_is_an_empty_frame_not_an_error(tmp_path):
    client = UnderstatClient(
        client=_http(lambda r: httpx.Response(
            200, json={"dates": [], "teams": {}, "players": []})),
        cache_dir=tmp_path, sleep=0.0)
    assert client.league_matches("2024-25").empty
    assert client.team_history("2024-25", season_idx=2).empty


def test_a_match_payload_without_rosters_raises(tmp_path):
    client = UnderstatClient(
        client=_http(lambda r: httpx.Response(200, json={"tmpl": "..."})),
        cache_dir=tmp_path, sleep=0.0)
    with pytest.raises(GafferError) as exc:
        client.match_players("18001", pd.Timestamp("2024-08-16").date(),
                             "A", "B")
    assert "rosters" in str(exc.value)


def test_match_data_requests_the_json_endpoint(tmp_path):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json=_match())

    client = UnderstatClient(client=_http(handler), cache_dir=tmp_path,
                             sleep=0.0)
    client.match_players("18001", pd.Timestamp("2024-08-16").date(), "A", "B")
    assert seen["url"] == "https://understat.com/getMatchData/18001"


def test_match_page_is_cached_by_id_and_never_refetched(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json=_match())

    client = UnderstatClient(client=_http(handler), cache_dir=tmp_path,
                             sleep=0.0)
    first = client.match_players("18001", pd.Timestamp("2024-08-16").date(),
                                 "Manchester United",
                                 "Wolverhampton Wanderers")
    second = client.match_players("18001", pd.Timestamp("2024-08-16").date(),
                                  "Manchester United",
                                  "Wolverhampton Wanderers")
    assert calls["n"] == 1
    assert len(first) == len(second) == 2
    assert (tmp_path / "match" / "18001.json").exists()


def test_a_cache_file_written_before_the_endpoint_change_still_reads(tmp_path):
    """Understat moved to JSON endpoints; the on-disk cache format did not.
    Thousands of already-scraped matches must not need re-fetching."""
    import json as _json

    legacy = [{"match_id": "18001", "understat_id": "1250",
               "player_name": "Bruno Fernandes", "team": "Manchester United",
               "minutes": 90.0, "us_shots": 4.0, "us_key_passes": 3.0,
               "us_npxg": 0.09, "us_xgchain": 1.2, "us_xgbuildup": 0.4}]
    path = tmp_path / "match" / "18001.json"
    path.parent.mkdir(parents=True)
    path.write_text(_json.dumps(legacy))

    def refuse(request):
        raise AssertionError("a cached match must not be refetched")

    out = UnderstatClient(client=_http(refuse), cache_dir=tmp_path,
                          sleep=0.0).match_players(
        "18001", pd.Timestamp("2024-08-16").date(), "A", "B")
    assert list(out["understat_id"]) == ["1250"]
    assert out.loc[0, "date"] == pd.Timestamp("2024-08-16").date()
    assert list(out.columns) == ["match_id", "date", "understat_id",
                                 "player_name", "team", "minutes", "us_shots",
                                 "us_key_passes", "us_npxg", "us_xgchain",
                                 "us_xgbuildup"]


def test_cached_match_survives_a_process_restart(tmp_path):
    """The 1900-page backfill has to be resumable: a fresh client must read
    the same cache."""
    def handler(request):
        return httpx.Response(200, json=_match())

    UnderstatClient(client=_http(handler), cache_dir=tmp_path,
                    sleep=0.0).match_players(
        "18001", pd.Timestamp("2024-08-16").date(), "A", "B")

    def refuse(request):
        raise AssertionError("cached match must not be refetched")

    out = UnderstatClient(client=_http(refuse), cache_dir=tmp_path,
                          sleep=0.0).match_players(
        "18001", pd.Timestamp("2024-08-16").date(), "A", "B")
    assert len(out) == 2


def test_uncached_fetches_sleep_between_requests(tmp_path, monkeypatch):
    """Politeness is not optional on somebody else's free website."""
    slept = []
    monkeypatch.setattr("gaffer.data.understat.time.sleep", slept.append)

    def handler(request):
        return httpx.Response(200, json=_match())

    client = UnderstatClient(client=_http(handler), cache_dir=tmp_path,
                             sleep=1.0)
    client.match_players("18001", pd.Timestamp("2024-08-16").date(), "A", "B")
    client.match_players("18002", pd.Timestamp("2024-08-17").date(), "A", "B")
    assert slept == [1.0, 1.0]


def test_a_cache_hit_does_not_sleep(tmp_path, monkeypatch):
    slept = []
    monkeypatch.setattr("gaffer.data.understat.time.sleep", slept.append)
    client = UnderstatClient(
        client=_http(lambda r: httpx.Response(200, json=_match())),
        cache_dir=tmp_path, sleep=1.0)
    client.match_players("18001", pd.Timestamp("2024-08-16").date(), "A", "B")
    slept.clear()
    client.match_players("18001", pd.Timestamp("2024-08-16").date(), "A", "B")
    assert slept == []


def test_a_failed_match_fetch_returns_empty_and_caches_nothing(tmp_path):
    """One dead page must cost one match, not the backfill — and must not
    poison the cache with an empty result that never retries."""
    client = UnderstatClient(
        client=_http(lambda r: httpx.Response(503)), cache_dir=tmp_path,
        sleep=0.0, retries=1)
    out = client.match_players("18001", pd.Timestamp("2024-08-16").date(),
                               "A", "B")
    assert out.empty
    assert not (tmp_path / "match" / "18001.json").exists()


def test_team_history_reads_the_league_page_once_per_season(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json=_LEAGUE)

    client = UnderstatClient(client=_http(handler), cache_dir=tmp_path,
                             sleep=0.0)
    out = client.team_history("2024-25", season_idx=2)
    assert len(out) == 2
    assert calls["n"] == 1


def test_season_year_is_the_starting_year():
    from gaffer.data.understat import season_year

    assert season_year("2024-25") == "2024"
    assert season_year("2020-21") == "2020"


# --- understat -> FPL id mapping ------------------------------------------

from gaffer.data.understat import load_overrides, map_understat_players


def _us(rows):
    """[(understat_id, player_name, team)]"""
    return pd.DataFrame([{"understat_id": i, "player_name": n, "team": t}
                         for i, n, t in rows])


def _fpl(rows):
    """[(code, name, team_name)]"""
    return pd.DataFrame([{"code": c, "name": n, "team_name": t}
                         for c, n, t in rows])


def test_map_understat_players_matches_on_name_and_club():
    us = _us([("1250", "Bruno Fernandes", "Manchester United")])
    fpl = _fpl([(1, "Bruno Fernandes", "Man Utd"),
                (2, "Bruno Guimarães", "Newcastle")])
    out, report = map_understat_players(us, fpl,
                                        team_aliases={"Manchester United":
                                                      "Man Utd"})
    assert out.to_dict("records") == [{"understat_id": "1250", "code": 1}]
    assert report["exact"] == 1 and report["unmatched"] == 0


def test_map_understat_players_ignores_accents_and_punctuation():
    us = _us([("9", "N'Golo Kanté", "Chelsea")])
    fpl = _fpl([(5, "Ngolo Kante", "Chelsea")])
    out, _ = map_understat_players(us, fpl, team_aliases={"Chelsea": "Chelsea"})
    assert list(out["code"]) == [5]


def test_map_understat_players_falls_back_to_a_unique_cross_club_name():
    """A January transfer puts the player at one club in one source and
    another in the other; a unique full-name match is safe."""
    us = _us([("11", "Kai Havertz", "Arsenal")])
    fpl = _fpl([(7, "Kai Havertz", "Chelsea")])
    out, report = map_understat_players(us, fpl,
                                        team_aliases={"Arsenal": "Arsenal"})
    assert list(out["code"]) == [7]
    assert report["cross_club"] == 1


def test_map_understat_players_refuses_an_ambiguous_cross_club_name():
    """Two players share a normalized name and neither club agrees — a coin
    flip here attaches one player's shots to another."""
    us = _us([("12", "Danny Ward", "Leicester")])
    fpl = _fpl([(8, "Danny Ward", "Huddersfield"),
                (9, "Danny Ward", "Cardiff City")])
    out, report = map_understat_players(us, fpl, team_aliases={})
    assert out.empty
    assert report["unmatched"] == 1


def test_map_understat_players_applies_the_override_file():
    # The two sources spell this one differently enough that no
    # normalization saves it — which is exactly what the override file is for.
    us = _us([("13", "Bobby De Cordova-Reid", "Fulham")])
    fpl = _fpl([(10, "Bobby Reid", "Fulham")])
    out, report = map_understat_players(us, fpl, team_aliases={},
                                        overrides={"13": 10})
    assert list(out["code"]) == [10]
    assert report["override"] == 1


def test_map_understat_players_reports_unmatched_names(capsys):
    us = _us([("14", "Nobody At All", "Nowhere")])
    fpl = _fpl([(11, "Someone Else", "Arsenal")])
    out, report = map_understat_players(us, fpl, team_aliases={})
    assert out.empty
    assert report["rows"] == 1 and report["unmatched"] == 1
    assert report["exact"] == report["cross_club"] == report["override"] == 0
    assert "Nobody At All" in report["unmatched_names"][0]


def test_map_understat_players_is_one_row_per_understat_id():
    """A player appears in 38 match frames; the mapping is a lookup table,
    not a row-for-row join."""
    us = _us([("15", "Cole Palmer", "Chelsea")] * 38)
    fpl = _fpl([(12, "Cole Palmer", "Chelsea")])
    out, _ = map_understat_players(us, fpl, team_aliases={"Chelsea": "Chelsea"})
    assert len(out) == 1


def test_load_overrides_returns_a_dict_and_skips_doc_keys():
    overrides = load_overrides()
    assert isinstance(overrides, dict)
    assert not any(k.startswith("_") for k in overrides)


# --- parquet builders -----------------------------------------------------

from gaffer.data.understat import (UNDERSTAT_TEAM_ALIASES,
                                   UNDERSTAT_PLAYER_PATH,
                                   UNDERSTAT_TEAM_PATH, build_understat_player,
                                   build_understat_team)


def _league_and_match_handler(request):
    if "getLeagueData" in str(request.url):
        return httpx.Response(200, json=_LEAGUE)
    return httpx.Response(200, json=_match())


def test_every_understat_alias_target_is_an_fpl_name():
    from gaffer.data.odds import TEAM_ALIASES

    unknown = sorted(set(UNDERSTAT_TEAM_ALIASES.values())
                     - set(TEAM_ALIASES.values()))
    assert unknown == []


def test_build_understat_player_writes_the_parquet(tmp_path, monkeypatch):
    import gaffer.data.store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    client = UnderstatClient(client=_http(_league_and_match_handler),
                             cache_dir=tmp_path / "raw", sleep=0.0)
    fpl = _fpl([(1, "Bruno Fernandes", "Man Utd"),
                (2, "Matheus Cunha", "Wolves")])
    out = build_understat_player(["2024-25"], {"2024-25": 2}, fpl,
                                 client=client)
    assert (tmp_path / UNDERSTAT_PLAYER_PATH).exists()
    assert set(out.columns) == {"season", "season_idx", "understat_id", "code",
                                "player_name", "team", "date", "minutes",
                                "us_shots", "us_key_passes", "us_npxg",
                                "us_xgchain", "us_xgbuildup"}
    assert set(out["code"]) == {1, 2}


def test_build_understat_player_only_fetches_played_matches(tmp_path):
    """The unplayed fixture in datesData has no page worth caching."""
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return _league_and_match_handler(request)

    client = UnderstatClient(client=_http(handler),
                             cache_dir=tmp_path / "raw", sleep=0.0)
    build_understat_player(["2024-25"], {"2024-25": 2},
                           _fpl([(1, "Bruno Fernandes", "Man Utd")]),
                           client=client, store_result=False)
    assert any("getMatchData/18001" in u for u in seen)
    assert not any("getMatchData/18002" in u for u in seen)


def test_build_understat_player_drops_unmapped_players(tmp_path):
    """An unmatched player contributes nothing rather than something wrong."""
    client = UnderstatClient(client=_http(_league_and_match_handler),
                             cache_dir=tmp_path / "raw", sleep=0.0)
    out = build_understat_player(["2024-25"], {"2024-25": 2},
                                 _fpl([(1, "Bruno Fernandes", "Man Utd")]),
                                 client=client, store_result=False)
    assert set(out["code"]) == {1}


def test_build_understat_team_writes_the_parquet(tmp_path, monkeypatch):
    import gaffer.data.store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    client = UnderstatClient(client=_http(_league_and_match_handler),
                             cache_dir=tmp_path / "raw", sleep=0.0)
    out = build_understat_team(["2024-25"], {"2024-25": 2},
                               {"Arsenal": 3}, client=client)
    assert (tmp_path / UNDERSTAT_TEAM_PATH).exists()
    assert list(out["team_code"]) == [3, 3]
    assert "ppda" in out.columns


def test_build_understat_team_drops_a_club_with_no_code(tmp_path):
    client = UnderstatClient(client=_http(_league_and_match_handler),
                             cache_dir=tmp_path / "raw", sleep=0.0)
    out = build_understat_team(["2024-25"], {"2024-25": 2}, {},
                               client=client, store_result=False)
    assert out.empty
