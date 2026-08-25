import json

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


def test_an_empty_roster_is_not_cached(tmp_path):
    """A match understat has not processed yet answers with empty rosters.
    Caching that writes the hole in permanently: the file is never
    re-fetched, so the match is lost for good."""
    empty = {"rosters": {"h": {}, "a": {}}, "shots": {"h": [], "a": []}}
    client = UnderstatClient(
        client=_http(lambda r: httpx.Response(200, json=empty)),
        cache_dir=tmp_path, sleep=0.0)
    out = client.match_players("18001", pd.Timestamp("2024-08-16").date(),
                               "A", "B")
    assert out.empty
    assert not (tmp_path / "match" / "18001.json").exists()


def test_a_torn_cache_file_is_refetched_rather_than_raising(tmp_path):
    """A write interrupted mid-flight leaves half a JSON document, and a
    JSONDecodeError there takes down a scrape of thousands of matches."""
    path = tmp_path / "match" / "18001.json"
    path.parent.mkdir(parents=True)
    path.write_text('[{"match_id": "18001", "understat_')
    client = UnderstatClient(
        client=_http(lambda r: httpx.Response(200, json=_match())),
        cache_dir=tmp_path, sleep=0.0)
    out = client.match_players("18001", pd.Timestamp("2024-08-16").date(),
                               "Manchester United",
                               "Wolverhampton Wanderers")
    assert len(out) == 2
    # And the refetch repaired the file.
    assert json.loads(path.read_text())


def test_the_match_cache_is_written_atomically(tmp_path):
    """os.replace, not a direct write: a scrape killed mid-write must leave
    either the old file or the new one, never a truncated one."""
    import inspect

    src = inspect.getsource(UnderstatClient.match_players)
    assert "os.replace" in src


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
    # Different clubs in the two sources, so no pass but the file can
    # place him: understat has him at Fulham, FPL history at Leicester.
    us = _us([("13", "Bobby De Cordova-Reid", "Fulham")])
    fpl = _fpl([(10, "Bobby Reid", "Leicester")])
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
    assert report["token_subset"] == report["surname_club"] == 0
    assert "Nobody At All" in report["unmatched_names"][0]


# --- pass 3: token subset at the same club --------------------------------

def test_token_subset_matches_a_display_name_inside_a_legal_name():
    """vaastav carries the full legal name, understat the display name."""
    us = _us([("20", "Gabriel Martinelli", "Arsenal"),
              ("21", "Alisson", "Liverpool"),
              ("22", "Darwin Núñez", "Liverpool"),
              ("23", "Luis Díaz", "Liverpool")])
    fpl = _fpl([(30, "Gabriel Martinelli Silva", "Arsenal"),
                (31, "Alisson Ramses Becker", "Liverpool"),
                (32, "Darwin Núñez Ribeiro", "Liverpool"),
                (33, "Luis Díaz Marulanda", "Liverpool")])
    out, report = map_understat_players(
        us, fpl, team_aliases={"Arsenal": "Arsenal",
                               "Liverpool": "Liverpool"})
    assert dict(zip(out["understat_id"], out["code"])) == {
        "20": 30, "21": 31, "22": 32, "23": 33}
    assert report["token_subset"] == 4 and report["unmatched"] == 0


def test_token_subset_matches_the_other_direction_too():
    """The longer name can be understat's: the subset test is symmetric."""
    us = _us([("24", "Thiago Alcántara do Nascimento", "Liverpool")])
    fpl = _fpl([(34, "Thiago Alcántara", "Liverpool")])
    out, report = map_understat_players(us, fpl,
                                        team_aliases={"Liverpool":
                                                      "Liverpool"})
    assert list(out["code"]) == [34]
    assert report["token_subset"] == 1


def test_token_subset_refuses_two_same_club_candidates():
    """"Gabriel" sits inside three Arsenal legal names at once; guessing
    between them would attach one player's shots to another."""
    us = _us([("25", "Gabriel", "Arsenal")])
    fpl = _fpl([(35, "Gabriel dos Santos Magalhães", "Arsenal"),
                (36, "Gabriel Martinelli Silva", "Arsenal"),
                (37, "Gabriel Fernando de Jesus", "Arsenal")])
    out, report = map_understat_players(us, fpl,
                                        team_aliases={"Arsenal": "Arsenal"})
    assert out.empty
    assert report["token_subset"] == 0 and report["unmatched"] == 1


def test_token_subset_frees_up_once_the_narrower_names_are_claimed():
    """The pass sweeps every understat id before pass 4 runs, so the two
    unambiguous Arsenal Gabriels are claimed first and the bare "Gabriel"
    then has exactly one candidate left."""
    us = _us([("25", "Gabriel", "Arsenal"),
              ("26", "Gabriel Martinelli", "Arsenal"),
              ("27", "Gabriel Jesus", "Arsenal")])
    fpl = _fpl([(35, "Gabriel dos Santos Magalhães", "Arsenal"),
                (36, "Gabriel Martinelli Silva", "Arsenal"),
                (37, "Gabriel Fernando de Jesus", "Arsenal")])
    out, report = map_understat_players(us, fpl,
                                        team_aliases={"Arsenal": "Arsenal"})
    assert dict(zip(out["understat_id"], out["code"])) == {
        "25": 35, "26": 36, "27": 37}
    assert report["token_subset"] == 2 and report["surname_club"] == 1


def test_token_subset_never_reaches_across_clubs():
    us = _us([("28", "Gabriel Martinelli", "Arsenal")])
    fpl = _fpl([(38, "Gabriel Martinelli Silva", "Chelsea"),
                (39, "Somebody Else", "Chelsea")])
    out, report = map_understat_players(us, fpl,
                                        team_aliases={"Arsenal": "Arsenal"})
    assert out.empty
    assert report["token_subset"] == 0 and report["unmatched"] == 1


def test_token_subset_skips_a_code_an_earlier_pass_already_claimed():
    """Understat carries two ids for the same player; the exact pass owns
    the code and the second id must not claim it as well."""
    us = _us([("40", "Alisson Ramses Becker", "Liverpool"),
              ("41", "Alisson", "Liverpool")])
    fpl = _fpl([(50, "Alisson Ramses Becker", "Liverpool")])
    out, report = map_understat_players(us, fpl,
                                        team_aliases={"Liverpool":
                                                      "Liverpool"})
    assert out.to_dict("records") == [{"understat_id": "40", "code": 50}]
    assert report["exact"] == 1 and report["token_subset"] == 0
    assert report["unmatched"] == 1


# --- pass 4: shared token plus a first-name prefix -------------------------

def test_surname_club_bridges_a_shortened_first_name():
    """"Ben"/"Benjamin" is a nickname, not a subset — the shared surname
    plus the first-name prefix is what makes it safe."""
    us = _us([("42", "Ben White", "Arsenal")])
    fpl = _fpl([(51, "Benjamin White", "Arsenal"),
                (52, "Bukayo Saka", "Arsenal")])
    out, report = map_understat_players(us, fpl,
                                        team_aliases={"Arsenal": "Arsenal"})
    assert list(out["code"]) == [51]
    assert report["surname_club"] == 1


def test_surname_club_needs_a_shared_token_not_just_a_first_name():
    """Two Arsenal Bens are two players; the surname has to agree."""
    us = _us([("43", "Ben White", "Arsenal")])
    fpl = _fpl([(53, "Benjamin Cottrell", "Arsenal")])
    out, report = map_understat_players(us, fpl,
                                        team_aliases={"Arsenal": "Arsenal"})
    assert out.empty
    assert report["surname_club"] == 0 and report["unmatched"] == 1


def test_surname_club_needs_the_first_names_to_be_prefix_kin():
    """A bare surname match is not enough: two Beyers at Burnley are not
    the same footballer."""
    us = _us([("44", "Louis Beyer", "Burnley")])
    fpl = _fpl([(54, "Jordan Beyer", "Burnley")])
    out, report = map_understat_players(us, fpl,
                                        team_aliases={"Burnley": "Burnley"})
    assert out.empty
    assert report["surname_club"] == 0 and report["unmatched"] == 1


def test_surname_club_refuses_two_same_club_candidates():
    us = _us([("45", "Kaine Hayden", "Aston Villa")])
    fpl = _fpl([(55, "Kaine Kesler Hayden", "Aston Villa"),
                (56, "Kaine Kesler-Hayden", "Aston Villa")])
    out, report = map_understat_players(us, fpl,
                                        team_aliases={"Aston Villa":
                                                      "Aston Villa"})
    assert out.empty
    assert report["surname_club"] == 0 and report["unmatched"] == 1


def test_surname_club_never_reaches_across_clubs():
    us = _us([("46", "Ben White", "Arsenal")])
    fpl = _fpl([(57, "Benjamin White", "Chelsea")])
    out, report = map_understat_players(us, fpl,
                                        team_aliases={"Arsenal": "Arsenal"})
    assert out.empty
    assert report["surname_club"] == 0 and report["unmatched"] == 1


def test_surname_club_skips_a_code_an_earlier_pass_already_claimed():
    us = _us([("47", "Benjamin White", "Arsenal"),
              ("48", "Ben White", "Arsenal")])
    fpl = _fpl([(58, "Benjamin White", "Arsenal")])
    out, report = map_understat_players(us, fpl,
                                        team_aliases={"Arsenal": "Arsenal"})
    assert out.to_dict("records") == [{"understat_id": "47", "code": 58}]
    assert report["exact"] == 1 and report["surname_club"] == 0


def test_the_new_passes_leave_exact_and_cross_club_alone():
    """Same-club exact still wins over a subset candidate, and a unique
    league-wide name still resolves cross-club."""
    us = _us([("60", "Bruno Fernandes", "Manchester United"),
              ("61", "Kai Havertz", "Arsenal")])
    fpl = _fpl([(70, "Bruno Fernandes", "Man Utd"),
                (71, "Bruno Fernandes da Silva", "Man Utd"),
                (72, "Kai Havertz", "Chelsea")])
    out, report = map_understat_players(
        us, fpl, team_aliases={"Manchester United": "Man Utd",
                               "Arsenal": "Arsenal"})
    assert dict(zip(out["understat_id"], out["code"])) == {"60": 70, "61": 72}
    assert report["exact"] == 1 and report["cross_club"] == 1
    assert report["token_subset"] == 0 and report["surname_club"] == 0


def test_the_summary_line_carries_the_new_counters(capsys):
    us = _us([("62", "Darwin Núñez", "Liverpool"),
              ("63", "Ben White", "Arsenal")])
    fpl = _fpl([(80, "Darwin Núñez Ribeiro", "Liverpool"),
                (81, "Benjamin White", "Arsenal")])
    map_understat_players(us, fpl, team_aliases={"Liverpool": "Liverpool",
                                                 "Arsenal": "Arsenal"})
    printed = capsys.readouterr().out
    assert "1 token-subset" in printed and "1 surname-club" in printed


def test_the_override_file_still_runs_after_the_new_passes():
    """A name neither new pass can bridge — no shared token at all — still
    lands on the manual file."""
    us = _us([("64", "Fabinho", "Liverpool")])
    fpl = _fpl([(90, "Fabio Henrique Tavares", "Liverpool")])
    out, report = map_understat_players(us, fpl,
                                        team_aliases={"Liverpool":
                                                      "Liverpool"},
                                        overrides={"64": 90})
    assert list(out["code"]) == [90]
    assert report["override"] == 1
    assert report["token_subset"] == report["surname_club"] == 0


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


def test_the_alias_table_covers_the_current_seasons_promoted_clubs():
    """A club understat spells short and FPL spells long ("Coventry" vs
    "Coventry City") has no code without an entry here, and its whole
    season of team rows drops."""
    for name in ("Coventry", "Hull", "Ipswich"):
        assert name in UNDERSTAT_TEAM_ALIASES


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


_RENAMED_TEAMS = {
    "88": {"id": "88", "title": "Ipswich", "history": [
        {"date": "2024-08-17 14:00:00", "xG": 0.9, "xGA": 2.2,
         "ppda": {"att": 300, "def": 20}, "deep": 3, "deep_allowed": 12},
    ]},
}


def _renamed_handler(request):
    return httpx.Response(200, json={"dates": _DATES,
                                     "teams": _RENAMED_TEAMS, "players": []})


def test_build_understat_team_bridges_a_club_fpl_has_since_renamed(tmp_path):
    """The alias table targets the CURRENT bootstrap spelling ("Ipswich
    Town"), but an older season's name->code table still says "Ipswich".
    Without the rename bridge that club has no code in any historical
    season and drops out of the parquet entirely."""
    client = UnderstatClient(client=_http(_renamed_handler),
                             cache_dir=tmp_path / "raw", sleep=0.0)
    out = build_understat_team(["2024-25"], {"2024-25": 2},
                               {"Ipswich": 40}, client=client,
                               store_result=False)
    assert list(out["team_code"]) == [40]


def test_build_understat_team_names_the_clubs_it_drops(tmp_path, capsys):
    """A silent filter is how three clubs went missing from a season without
    anyone noticing; the names have to reach the console."""
    client = UnderstatClient(client=_http(_renamed_handler),
                             cache_dir=tmp_path / "raw", sleep=0.0)
    build_understat_team(["2024-25"], {"2024-25": 2}, {}, client=client,
                         store_result=False)
    out = capsys.readouterr().out
    assert "2024-25" in out and "Ipswich Town" in out


# --- html entities in understat's own text --------------------------------

def test_match_player_rows_unescape_html_entities_in_names():
    """Understat serves its JSON HTML-escaped, and an apostrophe comes back
    as ``&#039;`` — which normalizes to a "039" token that matches nothing."""
    match = {"rosters": {"h": {"1": {"player_id": "9", "player":
                                     "N&#039;Golo Kant&eacute;", "time": "90"}},
                         "a": {}},
             "shots": {"h": [], "a": []}}
    rows = match_player_rows(match, "1", None, "Chelsea", "Arsenal")
    assert list(rows["player_name"]) == ["N'Golo Kanté"]
    assert normalize_name(rows["player_name"].iloc[0]) == "ngolo kante"


def test_league_matches_unescape_html_entities_in_club_titles():
    dates = [{"id": "1", "isResult": True, "datetime": "2024-08-16 20:00:00",
              "h": {"id": "1", "title": "Nott&#039;m Forest"},
              "a": {"id": "2", "title": "Arsenal"}}]
    rows = league_matches(dates)
    assert rows["home_team"].iloc[0] == "Nott'm Forest"


def test_team_match_rows_unescape_html_entities_in_club_titles():
    teams = {"1": {"title": "Nott&#039;m Forest",
                   "history": [{"date": "2024-08-16", "xG": "1.0",
                                "xGA": "0.5", "deep": "3",
                                "deep_allowed": "1",
                                "ppda": {"att": "100", "def": "10"}}]}}
    rows = team_match_rows(teams, "2024-25", 0)
    assert rows["team"].iloc[0] == "Nott'm Forest"


# --- every club a code ever held ------------------------------------------

def _stub_history(monkeypatch, player_gw, tables):
    import gaffer.data.history as history_mod
    import gaffer.data.store as store_mod

    monkeypatch.setattr(store_mod, "load", lambda path: player_gw)
    monkeypatch.setattr(history_mod, "season_name_codes", lambda s: tables)


def test_history_player_index_carries_every_club_a_code_played_for(
        monkeypatch):
    """Understat's rows span five seasons, so pinning a code to its newest
    club alone loses the same-club match for every player who transferred."""
    from gaffer.data.understat import history_player_index

    player_gw = pd.DataFrame([
        {"season_idx": 0, "gw": 1, "code": 100, "name": "Dominic Solanke",
         "team_code": 91},
        {"season_idx": 2, "gw": 5, "code": 100, "name": "Dominic Solanke",
         "team_code": 6},
    ])
    _stub_history(monkeypatch, player_gw,
                  {"2022-23": {"Bournemouth": 91, "Spurs": 6}})
    out = history_player_index(["2022-23"])
    assert set(out["team_name"]) == {"Bournemouth", "Spurs"}
    assert set(out["code"]) == {100}
    assert set(out["name"]) == {"Dominic Solanke"}


def test_history_player_index_takes_the_newest_name_per_code(monkeypatch):
    """A rename mid-history should not leave two spellings behind."""
    from gaffer.data.understat import history_player_index

    player_gw = pd.DataFrame([
        {"season_idx": 0, "gw": 1, "code": 101, "name": "Joe Gomez",
         "team_code": 14},
        {"season_idx": 1, "gw": 3, "code": 101, "name": "Joseph Gomez",
         "team_code": 14},
    ])
    _stub_history(monkeypatch, player_gw, {"2022-23": {"Liverpool": 14}})
    out = history_player_index(["2022-23", "2023-24"])
    assert out.to_dict("records") == [
        {"code": 101, "name": "Joseph Gomez", "team_name": "Liverpool"}]


def test_history_player_index_drops_a_club_with_no_bootstrap_name(
        monkeypatch):
    from gaffer.data.understat import history_player_index

    player_gw = pd.DataFrame([
        {"season_idx": 0, "gw": 1, "code": 102, "name": "Someone",
         "team_code": 999},
    ])
    _stub_history(monkeypatch, player_gw, {"2022-23": {"Arsenal": 3}})
    assert history_player_index(["2022-23"]).empty


# --- the mapping against a multi-club FPL index ---------------------------

def test_the_mapping_matches_a_club_the_player_has_since_left():
    """Understat has Solanke at Bournemouth in 2022-23; the FPL index now
    carries both of his clubs, so the same-club pass reaches him."""
    us = _us([("70", "Dominic Solanke", "Bournemouth")])
    fpl = _fpl([(100, "Dominic Solanke-Mikale", "Bournemouth"),
                (100, "Dominic Solanke-Mikale", "Spurs"),
                (101, "Someone Else", "Bournemouth")])
    out, report = map_understat_players(
        us, fpl, team_aliases={"Bournemouth": "Bournemouth"})
    assert list(out["code"]) == [100]
    assert report["token_subset"] == 1 and report["unmatched"] == 0


def test_two_rows_for_one_code_at_one_club_are_not_an_ambiguity():
    """A code can reach the same club by two routes; deduping candidates by
    code is what keeps that from reading as two rival players."""
    us = _us([("71", "Gabriel Martinelli", "Arsenal")])
    fpl = _fpl([(110, "Gabriel Martinelli Silva", "Arsenal"),
                (110, "Gabriel Martinelli Silva", "Arsenal")])
    out, report = map_understat_players(us, fpl,
                                        team_aliases={"Arsenal": "Arsenal"})
    assert list(out["code"]) == [110]
    assert report["token_subset"] == 1


def test_cross_club_uniqueness_counts_codes_not_rows():
    """One player with three clubs is still one player: the league-unique
    name pass must not read his own rows as rivals."""
    us = _us([("72", "Kai Havertz", "Arsenal")])
    fpl = _fpl([(120, "Kai Havertz", "Chelsea"),
                (120, "Kai Havertz", "Arsenal"),
                (120, "Kai Havertz", "Spurs")])
    out, report = map_understat_players(us, fpl, team_aliases={})
    assert list(out["code"]) == [120]
    assert report["exact"] == 1


def test_cross_club_still_refuses_two_codes_sharing_a_name():
    us = _us([("73", "Danny Ward", "Leicester")])
    fpl = _fpl([(130, "Danny Ward", "Huddersfield"),
                (130, "Danny Ward", "Cardiff City"),
                (131, "Danny Ward", "Nowhere")])
    out, report = map_understat_players(us, fpl, team_aliases={})
    assert out.empty and report["unmatched"] == 1
