"""The two live news sources. No network: every fetch runs through
httpx.MockTransport against the committed snapshots in tests/data/news/."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pandas as pd

FIXTURES = Path(__file__).parent / "data" / "news"


def _players() -> pd.DataFrame:
    return pd.DataFrame([
        {"code": 100, "name": "Saka", "first_name": "Bukayo",
         "second_name": "Saka", "team_code": 3, "starts": 10,
         "minutes": 900},
        {"code": 101, "name": "Gabriel", "first_name": "Gabriel",
         "second_name": "Magalhaes", "team_code": 3, "starts": 9,
         "minutes": 810},
        {"code": 102, "name": "Haaland", "first_name": "Erling",
         "second_name": "Haaland", "team_code": 43, "starts": 10,
         "minutes": 900},
        {"code": 103, "name": "Palmer", "first_name": "Cole",
         "second_name": "Palmer", "team_code": 8, "starts": 10,
         "minutes": 880},
        {"code": 104, "name": "Rice", "first_name": "Declan",
         "second_name": "Rice", "team_code": 3, "starts": 8,
         "minutes": 700},
        {"code": 105, "name": "O'Riley", "first_name": "Matt",
         "second_name": "O'Riley", "team_code": 36, "starts": 7,
         "minutes": 600},
        {"code": 106, "name": "Welbeck", "first_name": "Danny",
         "second_name": "Welbeck", "team_code": 36, "starts": 2,
         "minutes": 200},
        {"code": 107, "name": "Mitoma", "first_name": "Kaoru",
         "second_name": "Mitoma", "team_code": 36, "starts": 9,
         "minutes": 800},
        {"code": 108, "name": "Verbruggen", "first_name": "Bart",
         "second_name": "Verbruggen", "team_code": 36, "starts": 10,
         "minutes": 900},
        # v8a F5: a player the injury table never lists, so a verdict about
        # him has to travel on a carrier row of its own.
        {"code": 99, "name": "Nketiah", "first_name": "Eddie",
         "second_name": "Nketiah", "team_code": 3, "starts": 1,
         "minutes": 90},
    ]).assign(news="")


def _teams() -> pd.DataFrame:
    return pd.DataFrame([
        {"code": 3, "name": "Arsenal", "short_name": "ARS"},
        {"code": 43, "name": "Man City", "short_name": "MCI"},
        {"code": 8, "name": "Chelsea", "short_name": "CHE"},
        {"code": 36, "name": "Brighton", "short_name": "BHA"},
    ])


def test_match_codes_resolves_exact_names_within_the_named_club():
    from gaffer.data.news.normalize import match_codes

    rows = pd.DataFrame([{"name": "Bukayo Saka", "club": "Arsenal"},
                         {"name": "Erling Haaland", "club": "Man City"}])
    out = match_codes(rows, _players(), _teams(), label="test")
    assert out["code"].tolist() == [100, 102]


def test_match_codes_takes_a_token_reorder_only_when_one_candidate_answers():
    """The AGS rule, ported: 'Magalhaes Gabriel' against the bootstrap's
    'Gabriel Magalhaes', taken only because exactly one unclaimed Arsenal
    player answers to those tokens. No edit distance — a wrong player's
    injury is worse than no injury."""
    from gaffer.data.news.normalize import match_codes

    rows = pd.DataFrame([{"name": "Magalhaes Gabriel", "club": "Arsenal"}])
    out = match_codes(rows, _players(), _teams(), label="test")
    assert out["code"].tolist() == [101]


def test_match_codes_drops_a_player_at_a_club_we_do_not_carry():
    from gaffer.data.news.normalize import match_codes

    rows = pd.DataFrame([{"name": "Bukayo Saka", "club": "Arsenal"},
                         {"name": "Joe Bloggs", "club": "Barnsley"}])
    out = match_codes(rows, _players(), _teams(), label="test")
    assert out["code"].tolist() == [100]


def test_match_codes_never_claims_one_player_twice():
    from gaffer.data.news.normalize import match_codes

    rows = pd.DataFrame([{"name": "Gabriel Magalhaes", "club": "Arsenal"},
                         {"name": "Gabriel", "club": "Arsenal"}])
    out = match_codes(rows, _players(), _teams(), label="test")
    assert out["code"].tolist() == [101]


def test_match_codes_discards_the_whole_batch_below_the_coverage_floor(capsys):
    """A shape change must not half-apply: if the page has been rewritten and
    only a sixth of it parses, the sixth that did is not a picture of the
    league's injuries, and acting on it is worse than acting on none."""
    from gaffer.data.news.normalize import match_codes

    rows = pd.DataFrame([{"name": "Bukayo Saka", "club": "Arsenal"}]
                        + [{"name": f"Nobody {i}", "club": "Arsenal"}
                           for i in range(5)])
    out = match_codes(rows, _players(), _teams(), label="injuries",
                      min_coverage=0.5)
    assert out.empty
    assert "injuries" in capsys.readouterr().out


def test_match_codes_on_an_empty_frame_returns_an_empty_frame():
    from gaffer.data.news.normalize import match_codes

    out = match_codes(pd.DataFrame(columns=["name", "club"]), _players(),
                      _teams(), label="test")
    assert out.empty
    assert "code" in out.columns


def _namesakes() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Two Danny Wards, one at Forest and one at Leicester.

    The real pair: the press writes the club out in full, the bootstrap
    abbreviates it, and picking the wrong one benches a fit starter.
    """
    players = pd.DataFrame([
        {"code": 200, "name": "Ward", "first_name": "Danny",
         "second_name": "Ward", "team_code": 17},
        {"code": 201, "name": "Ward", "first_name": "Danny",
         "second_name": "Ward", "team_code": 13},
    ])
    teams = pd.DataFrame([
        {"code": 17, "name": "Nott'm Forest", "short_name": "NFO"},
        {"code": 13, "name": "Leicester", "short_name": "LEI"},
    ])
    return players, teams


def test_match_codes_uses_the_club_alias_to_pick_the_right_namesake():
    """The reviewer's scenario: "Nottingham Forest" is not a bootstrap
    spelling, and without the alias the exact pass took whichever namesake
    came first in team order — a fit Leicester keeper benched by a Forest
    keeper's hamstring."""
    from gaffer.data.news.normalize import match_codes

    players, teams = _namesakes()
    rows = pd.DataFrame([{"name": "Danny Ward",
                          "club": "Nottingham Forest"}])
    out = match_codes(rows, players, teams, label="test")
    assert out["code"].tolist() == [200]


def test_match_codes_matches_nobody_when_two_namesakes_answer():
    """No alias, no resolvable club, two candidates: the exact pass must be
    as conservative as the token sweeps and take neither."""
    from gaffer.data.news.normalize import match_codes

    players, teams = _namesakes()
    rows = pd.DataFrame([{"name": "Danny Ward", "club": "Notts County"}])
    out = match_codes(rows, players, teams, label="test", min_coverage=0.0)
    assert out.empty


def test_match_codes_resolves_the_press_full_club_names():
    from gaffer.data.news.normalize import match_codes

    players = pd.DataFrame([
        {"code": 102, "name": "Haaland", "first_name": "Erling",
         "second_name": "Haaland", "team_code": 43},
        {"code": 300, "name": "Haaland", "first_name": "Erling",
         "second_name": "Haaland", "team_code": 1},
    ])
    teams = pd.DataFrame([
        {"code": 43, "name": "Man City", "short_name": "MCI"},
        {"code": 1, "name": "Man Utd", "short_name": "MUN"},
    ])
    rows = pd.DataFrame([{"name": "Erling Haaland",
                          "club": "Manchester City"}])
    out = match_codes(rows, players, teams, label="test")
    assert out["code"].tolist() == [102]


def test_match_codes_still_takes_a_lone_candidate_with_an_unresolved_club():
    """A club string nothing answers to is not a reason to drop a name only
    one player in the league carries."""
    from gaffer.data.news.normalize import match_codes

    rows = pd.DataFrame([{"name": "Bukayo Saka", "club": "Arsenal FC XI"}])
    out = match_codes(rows, _players(), _teams(), label="test")
    assert out["code"].tolist() == [100]


def test_scraped_entities_are_unescaped_before_anything_reads_them():
    """A scraped page is HTML, and HTML spells an ampersand ``&amp;`` and an
    apostrophe ``&#039;``. Left escaped, "Brighton &amp; Hove Albion" misses
    the club alias table by a word nobody wrote and "O&#039;Riley" is a
    different name from the one in the bootstrap."""
    from gaffer.data.news.lineups import parse_lineups
    from gaffer.data.news.premierinjuries import parse_injury_table

    row = parse_injury_table(
        "<table><tr><td>Player Matt O&#039;Riley</td>"
        "<td>Reason Knee Injury</td><td>Further Detail &amp; so on</td>"
        "<td>Potential Return 12/09/2026</td><td>Condition x</td>"
        "<td>Status Ruled Out</td></tr></table>").iloc[0]
    assert row["name"] == "Matt O'Riley"

    line = parse_lineups(
        "<h2>Brighton &amp; Hove Albion</h2>"
        '<ul class="story-parts"><li class="headers"><strong>Out:</strong>'
        '<ul class="players"><li>Matt O&#039;Riley</li></ul></li></ul>'
    ).iloc[0]
    assert line["club"] == "Brighton & Hove Albion"
    assert line["name"] == "Matt O'Riley"


def test_an_unescaped_club_and_name_resolve_to_a_code():
    """The end of that: through the alias table and the name index, which is
    where the escaping was actually costing matches."""
    from gaffer.data.news.lineups import parse_lineups
    from gaffer.data.news.normalize import (club_code, club_code_map,
                                            match_codes)

    teams = pd.DataFrame([
        {"code": 36, "name": "Brighton", "short_name": "BHA"}])
    players = pd.DataFrame([
        {"code": 200, "name": "O'Riley", "first_name": "Matt",
         "second_name": "O'Riley", "team_code": 36}])
    rows = parse_lineups(
        "<h2>Brighton &amp; Hove Albion</h2>"
        '<ul class="story-parts"><li class="headers"><strong>Out:</strong>'
        '<ul class="players"><li>Matt O&#039;Riley</li></ul></li></ul>')
    assert club_code(club_code_map(teams), rows["club"].iloc[0]) == 36
    assert match_codes(rows.drop(columns=["code"]), players, teams,
                       label="test")["code"].tolist() == [200]


def _injury_html() -> str:
    return (FIXTURES / "premierinjuries.html").read_text()


def _transport(calls: list, text: str | None = None):
    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if text is None:
            return httpx.Response(503)
        return httpx.Response(200, text=text)
    return httpx.MockTransport(handle)


def _client(text: str) -> httpx.Client:
    """A client that answers every request with ``text``."""
    return httpx.Client(transport=_transport([], text))


def test_parse_injury_table_reads_every_row():
    from gaffer.data.news.premierinjuries import parse_injury_table

    rows = parse_injury_table(_injury_html())
    assert len(rows) == 5
    assert list(rows.columns) == ["name", "club", "injury_type", "status",
                                  "expected_return_date", "news_chance_pct",
                                  "further_detail"]
    saka = rows[rows["name"] == "Bukayo Saka"].iloc[0]
    # The page carries no club column at all, so every row matches on the
    # name alone, through the uniqueness rule.
    assert saka["club"] == ""
    assert saka["injury_type"] == "hamstring"
    assert saka["status"] == "out"
    assert saka["expected_return_date"] == pd.Timestamp("2026-09-12").date()
    assert pd.isna(saka["news_chance_pct"])   # "Ruled Out" is not a number


def test_parse_injury_table_reads_the_reason_column_not_the_prose():
    """The type comes off "Reason", which is a short vocabulary, not off the
    "Further Detail" quote, which is a sentence that happens to name body
    parts. "Suspended" is the ban the return curves already know."""
    from gaffer.data.news.premierinjuries import parse_injury_table

    rows = parse_injury_table(_injury_html()).set_index("name")
    assert rows.loc["Erling Haaland", "injury_type"] == "knock"
    assert rows.loc["Magalhaes Gabriel", "injury_type"] == "groin"
    assert rows.loc["Joe Bloggs", "injury_type"] == "suspension"
    # "Other" is the site's shrug, and the pooled curve answers it.
    assert rows.loc["Cole Palmer", "injury_type"] == "unknown"


def test_parse_injury_table_reads_a_percentage_status_as_a_doubt():
    """The status column is either "Ruled Out" or a percentage, and the
    percentage is a chance_of_playing the site is handing us outright."""
    from gaffer.data.news.premierinjuries import parse_injury_table

    rows = parse_injury_table(_injury_html()).set_index("name")
    assert rows.loc["Erling Haaland", "status"] == "doubtful"
    assert rows.loc["Erling Haaland", "news_chance_pct"] == 75.0
    assert rows.loc["Joe Bloggs", "news_chance_pct"] == 100.0


def test_parse_injury_table_keeps_a_row_with_no_return_date():
    """"No Return Date" is the site's literal text where a date would go. The
    row is real information — it must not be dropped, and it must not parse
    into a date."""
    from gaffer.data.news.premierinjuries import parse_injury_table

    rows = parse_injury_table(_injury_html())
    palmer = rows[rows["name"] == "Cole Palmer"].iloc[0]
    assert palmer["expected_return_date"] is None
    assert palmer["status"] == "out"


def test_parse_injury_table_tolerates_cells_without_their_label():
    """Every cell prints its own column label, and the parse strips it. If
    the site ever stops printing them the columns are still in order, so the
    positional reading stands in rather than the row being lost."""
    from gaffer.data.news.premierinjuries import parse_injury_table

    html = ("<table><tr><td>Bukayo Saka</td><td>Hamstring Injury</td>"
            "<td>Aug 20: 'tight'</td><td>12/09/2026</td>"
            "<td>Not Available</td><td>Ruled Out</td><td>TRACK</td>"
            "</tr></table>")
    row = parse_injury_table(html).iloc[0]
    assert row["name"] == "Bukayo Saka"
    assert row["injury_type"] == "hamstring"
    assert row["status"] == "out"
    assert row["expected_return_date"] == pd.Timestamp("2026-09-12").date()


def test_parse_injury_table_on_a_rewritten_page_returns_empty_not_garbage():
    from gaffer.data.news.premierinjuries import parse_injury_table

    assert parse_injury_table("<html><body><p>hello</p></body></html>").empty


def test_fetch_injuries_matches_codes_and_caches_the_page(tmp_path):
    from gaffer.data.news.premierinjuries import fetch_injuries

    calls: list[str] = []
    client = httpx.Client(transport=_transport(calls, _injury_html()))
    now = datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc)
    out = fetch_injuries(_players(), _teams(), cache_dir=tmp_path,
                         client=client, now=now, classifier=False,
                         shadow=False)
    # The unrostered player is unmatched (4/5 = 80%, above the floor), and
    # every match is made without a club column to key on.
    assert sorted(out["code"]) == [100, 101, 102, 103]
    assert list(out.columns) == ["code", "injury_type", "news_status",
                                 "expected_return_date", "news_chance_pct",
                                 "further_detail", "llm_verdict",
                                 "llm_confidence", "source", "fetched_at"]
    assert out.set_index("code").loc[102, "news_chance_pct"] == 75.0
    assert (out["source"] == "premierinjuries").all()
    assert len(calls) == 1

    # Same cache window: no second request.
    fetch_injuries(_players(), _teams(), cache_dir=tmp_path, client=client,
                   now=now + timedelta(hours=1), classifier=False,
                   shadow=False)
    assert len(calls) == 1

    # Next window: one more.
    fetch_injuries(_players(), _teams(), cache_dir=tmp_path, client=client,
                   now=now + timedelta(hours=7), classifier=False,
                   shadow=False)
    assert len(calls) == 2


def test_fetch_injuries_degrades_to_empty_when_the_host_is_down(tmp_path,
                                                                capsys):
    from gaffer.data.news.premierinjuries import INJURY_COLS, fetch_injuries

    client = httpx.Client(transport=_transport([], None))
    out = fetch_injuries(_players(), _teams(), cache_dir=tmp_path,
                         client=client, classifier=False, shadow=False)
    assert out.empty
    assert list(out.columns) == INJURY_COLS
    assert "unavailable" in capsys.readouterr().out


def test_cache_path_clamps_the_window_to_a_day(tmp_path):
    """``cache_hours`` comes out of config.toml, so it can be anything. Above
    24 the bucket arithmetic collapses to a single window and the filename
    stops carrying the day; below 1 it divides by zero."""
    from gaffer.data.news import cache_path

    now = datetime(2026, 9, 4, 23, tzinfo=timezone.utc)
    assert (cache_path(tmp_path, "x", 999, now).name
            == cache_path(tmp_path, "x", 24, now).name)
    assert (cache_path(tmp_path, "x", 0, now).name
            == cache_path(tmp_path, "x", 1, now).name)


def test_fetch_injuries_degrades_on_any_httpx_error_not_just_transport(
        tmp_path, capsys):
    """``TooManyRedirects`` and ``DecodingError`` are ``RequestError`` but not
    ``TransportError``, and a redirect loop on a news host was reaching the
    advise path as an exception."""
    from gaffer.data.news.premierinjuries import fetch_injuries

    def loop(request: httpx.Request) -> httpx.Response:
        raise httpx.TooManyRedirects("too many redirects",
                                     request=request)

    client = httpx.Client(transport=httpx.MockTransport(loop))
    out = fetch_injuries(_players(), _teams(), cache_dir=tmp_path,
                         client=client, classifier=False, shadow=False)
    assert out.empty
    assert "unavailable" in capsys.readouterr().out


def _lineups_html() -> str:
    return (FIXTURES / "ffs_lineups.html").read_text()


def test_parse_lineups_reads_the_pitch_and_the_absence_lists():
    """The real page shape: an ``<h2>`` per club, a pitch of ``row-N`` lists
    whose ``<li>`` carry ``title="Surname (First)"`` and an FPL photo URL,
    then ``Out:``/``Doubts:``/``Banned:`` lists of bare names."""
    from gaffer.data.news.lineups import P_START_HINT, parse_lineups

    rows = parse_lineups(_lineups_html())
    assert list(rows.columns) == ["name", "club", "slot", "code"]
    by_name = dict(zip(rows["name"], rows["slot"]))
    assert by_name["Bukayo Saka"] == "start"
    assert by_name["Gabriel Magalhães"] == "out"
    assert by_name["Danny Welbeck"] == "doubt"
    assert by_name["Bart Verbruggen"] == "out"
    assert P_START_HINT == {"start": 1.0, "doubt": 0.25, "out": 0.0}


def test_parse_lineups_reorders_the_surname_first_title_and_takes_the_code():
    """``title="Saka (Bukayo)"`` is the bootstrap's name inside out, and the
    photo filename is the FPL player code outright — so the XI joins on the
    code and the reordered name is only ever the fallback."""
    from gaffer.data.news.lineups import parse_lineups

    rows = parse_lineups(_lineups_html()).set_index("name")
    assert rows.loc["Bukayo Saka", "code"] == 100
    assert rows.loc["Declan Rice", "code"] == 104
    # The absence lists carry no photo at all.
    assert pd.isna(rows.loc["Danny Welbeck", "code"])


def test_parse_lineups_strips_the_doubt_percentage_from_the_name():
    from gaffer.data.news.lineups import parse_lineups

    assert "Danny Welbeck" in set(parse_lineups(_lineups_html())["name"])


def test_parse_lineups_ignores_the_latest_news_prose():
    """The prose paragraph names half the squad and is not a list. A parse
    that read it would hint players nobody has said anything about."""
    from gaffer.data.news.lineups import parse_lineups

    rows = parse_lineups(_lineups_html())
    arsenal = rows[rows["club"] == "Arsenal"]
    assert len(arsenal) == 3          # two starters, one out
    assert "Kaoru Mitoma" not in set(arsenal["name"])


def test_parse_lineups_unescapes_the_club_heading():
    from gaffer.data.news.lineups import parse_lineups

    assert set(parse_lineups(_lineups_html())["club"]) == {
        "Arsenal", "Brighton & Hove Albion"}


def test_parse_lineups_on_a_rewritten_page_returns_empty():
    from gaffer.data.news.lineups import parse_lineups

    assert parse_lineups(
        "<html><body><p>team news soon</p></body></html>").empty


def test_fetch_lineups_maps_slots_to_hints_and_codes(tmp_path):
    from gaffer.data.news.lineups import fetch_lineups

    calls: list[str] = []
    client = httpx.Client(transport=_transport(calls, _lineups_html()))
    out = fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                        client=client).set_index("code")
    assert out.loc[100, "p_start_hint"] == 1.0     # Saka, joined by code
    assert out.loc[104, "p_start_hint"] == 1.0     # Rice, joined by code
    assert out.loc[101, "p_start_hint"] == 0.0     # Gabriel is Out
    assert out.loc[105, "p_start_hint"] == 1.0     # O'Riley, joined by code
    assert out.loc[107, "p_start_hint"] == 1.0     # Mitoma, unknown photo code
    assert out.loc[106, "p_start_hint"] == 0.25    # Welbeck is a doubt
    assert out.loc[108, "p_start_hint"] == 0.0     # Verbruggen is banned
    assert len(out) == 7
    assert (out["source"] == "lineups").all()
    assert len(calls) == 1


def test_fetch_lineups_leaves_a_player_on_no_list_unhinted(tmp_path):
    """A mere omission from the predicted XI is not evidence this cycle: 102
    and 103 are named nowhere on the page and get no row at all."""
    from gaffer.data.news.lineups import fetch_lineups

    client = httpx.Client(transport=_transport([], _lineups_html()))
    out = fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                        client=client)
    assert 102 not in set(out["code"])
    assert 103 not in set(out["code"])


def test_fetch_lineups_prefers_the_photo_code_over_the_title_name(tmp_path):
    """The code in the photo URL is the FPL code outright; the title is a
    name a human typed. Where they disagree the code wins, and no name
    matching is even attempted for that row."""
    from gaffer.data.news.lineups import fetch_lineups

    markup = ("<h2>Arsenal</h2>"
              '<ul class="row-1"><li title="Rice (Declan)">'
              '<img src="https://resources.premierleague.com/premierleague25'
              '/photos/players/110x140/100.png?v=2026"></li></ul>')
    client = httpx.Client(transport=_transport([], markup))
    out = fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                        client=client, absence=False)
    assert out["code"].tolist() == [100]


def test_fetch_lineups_ignores_a_pitch_under_a_heading_that_is_not_a_club(
        tmp_path):
    """The live page carries a "Scout Picks" widget built from byte-identical
    pitch markup under an editorial heading. Its eleven photo codes are real
    FPL codes, so nothing downstream would notice eleven bogus predicted
    starters — the heading is the only thing that tells them apart."""
    from gaffer.data.news.lineups import fetch_lineups

    markup = ("<h2>Follow us on social</h2>"
              '<ul class="row-1"><li title="Saka (Bukayo) - Midfielder">'
              '<img src="https://resources.premierleague.com/premierleague25'
              '/photos/players/110x140/100.png"></li></ul>')
    client = httpx.Client(transport=_transport([], markup))
    assert fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                         client=client).empty


def test_fetch_lineups_drops_a_pitch_entry_whose_photo_is_at_another_club(
        tmp_path):
    """The photo says who and the ``<h2>`` says where. Where they disagree
    the entry is furniture, not a line-up, and a wrong 1.0 ceiling is exactly
    the mistake the code join was supposed to make impossible."""
    from gaffer.data.news.lineups import fetch_lineups

    markup = ("<h2>Arsenal</h2>"
              '<ul class="row-1"><li title="Haaland (Erling)">'
              '<img src="https://resources.premierleague.com/premierleague25'
              '/photos/players/110x140/102.png"></li></ul>')
    client = httpx.Client(transport=_transport([], markup))
    out = fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                        client=client, min_coverage=0.0)
    assert out.empty


def test_fetch_lineups_keeps_the_absence_lists_inside_their_own_club(tmp_path):
    """"Welbeck" under the Arsenal heading is not Brighton's Welbeck. The
    club the ``<h2>`` names scopes the match, and an absentee nobody at that
    club answers to is dropped rather than guessed at."""
    from gaffer.data.news.lineups import fetch_lineups

    markup = ("<h2>Arsenal</h2>"
              '<ul class="story-parts"><li class="headers">'
              "<strong>Out:</strong>"
              '<ul class="players"><li>Danny Welbeck</li></ul></li></ul>')
    client = httpx.Client(transport=_transport([], markup))
    out = fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                        client=client, min_coverage=0.0)
    assert out.empty


def test_fetch_lineups_keeps_the_code_join_when_the_name_batch_is_discarded(
        tmp_path, capsys):
    """The coverage floor guards *name matching*, which is the pass that can
    silently mis-resolve. A row joined on the photo code cannot be wrong, so
    a page whose absence lists have all been renamed still yields its XI."""
    from gaffer.data.news.lineups import fetch_lineups

    markup = ("<h2>Arsenal</h2>"
              '<ul class="row-1"><li title="Saka (Bukayo)">'
              '<img src="https://resources.premierleague.com/premierleague25'
              '/photos/players/110x140/100.png"></li></ul>'
              '<ul class="story-parts"><li class="headers">'
              "<strong>Out:</strong><ul class=\"players\">"
              + "".join(f"<li>Nobody {i}</li>" for i in range(5))
              + "</ul></li></ul>")
    client = httpx.Client(transport=_transport([], markup))
    out = fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                        client=client, absence=False)
    assert out["code"].tolist() == [100]
    assert "lineups" in capsys.readouterr().out


def test_fetch_lineups_degrades_to_empty_when_the_page_is_down(tmp_path):
    from gaffer.data.news.lineups import LINEUP_COLS, fetch_lineups

    client = httpx.Client(transport=_transport([], None))
    out = fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                        client=client)
    assert out.empty
    assert list(out.columns) == LINEUP_COLS


# --- v8a F4: notable absences ---------------------------------------------

def _absence_players() -> pd.DataFrame:
    """One club, four players: a regular in the XI, a regular left out, a
    fringe player left out, and a listed doubt."""
    return pd.DataFrame([
        {"code": 11, "name": "In XI", "first_name": "A", "second_name": "One",
         "team_code": 3, "starts": 10, "minutes": 900},
        {"code": 12, "name": "Left Out", "first_name": "B",
         "second_name": "Two", "team_code": 3, "starts": 9, "minutes": 800},
        {"code": 13, "name": "Fringe", "first_name": "C",
         "second_name": "Three", "team_code": 3, "starts": 1, "minutes": 90},
        {"code": 14, "name": "Doubtful", "first_name": "D",
         "second_name": "Four", "team_code": 3, "starts": 8, "minutes": 700}])


def test_a_regular_left_out_of_a_parsed_xi_is_damped():
    from gaffer.data.news.lineups import notable_absences

    out = notable_absences(_absence_players(), covered={3},
                           claimed={11, 14}, damp=0.75, min_share=0.6)
    assert list(out["code"]) == [12]
    assert out.iloc[0]["absence_damp"] == 0.75


def test_a_fringe_player_left_out_is_not_news():
    """Half a squad is out of every predicted XI. Only a player the manager
    has actually been picking says anything by being missing."""
    from gaffer.data.news.lineups import notable_absences

    out = notable_absences(_absence_players(), covered={3},
                           claimed={11, 14}, damp=0.75, min_share=0.6)
    assert 13 not in set(out["code"])


def test_a_club_whose_xi_was_not_parsed_damps_nobody():
    """No team sheet is not the same as a team sheet without him."""
    from gaffer.data.news.lineups import notable_absences

    out = notable_absences(_absence_players(), covered=set(),
                           claimed=set(), damp=0.75, min_share=0.6)
    assert out.empty


def test_a_player_the_official_flags_already_docked_is_not_damped_twice():
    """The injury feed's ``status`` is the sharper claim and it is applied
    first. Damping a flagged player again for being out of a predicted XI
    charges him twice for one absence — and the predicted XI leaves him out
    *because* of the flag, so the second charge is not even a second source.
    """
    from gaffer.data.news.lineups import notable_absences

    players = _absence_players()
    players.loc[players["code"] == 12, "status"] = "d"
    players.loc[players["code"] == 12, "chance_of_playing"] = 50.0
    out = notable_absences(players, covered={3}, claimed={11, 14},
                           damp=0.75, min_share=0.6)
    assert out.empty


def test_a_doubt_with_a_chance_percentage_is_not_damped_twice():
    from gaffer.data.news.lineups import notable_absences

    players = _absence_players()
    players.loc[players["code"] == 12, "chance_of_playing"] = 25.0
    out = notable_absences(players, covered={3}, claimed={11, 14},
                           damp=0.75, min_share=0.6)
    assert out.empty


def test_an_unflagged_regular_is_still_damped():
    """The other half of the rail: ``status = 'a'`` and a full chance is the
    fit player nobody has docked, and his omission is the whole signal."""
    from gaffer.data.news.lineups import notable_absences

    players = _absence_players()
    players["status"] = "a"
    players["chance_of_playing"] = 100.0
    out = notable_absences(players, covered={3}, claimed={11, 14},
                           damp=0.75, min_share=0.6)
    assert list(out["code"]) == [12]


def test_a_player_already_on_an_absence_list_is_not_damped_twice():
    from gaffer.data.news.lineups import notable_absences

    out = notable_absences(_absence_players(), covered={3},
                           claimed={11, 12, 14}, damp=0.75, min_share=0.6)
    assert out.empty


def test_fetch_lineups_emits_absence_rows_beside_the_hints(tmp_path):
    from gaffer.data.news.lineups import LINEUP_COLS, fetch_lineups

    client = httpx.Client(transport=_transport([], _lineups_html()))
    out = fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                        client=client, absence=True, absence_damp=0.75)
    assert list(out.columns) == LINEUP_COLS
    assert out["p_start_hint"].notna().any()


def test_the_absence_rule_can_be_switched_off(tmp_path):
    from gaffer.data.news.lineups import fetch_lineups

    on = fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                       client=httpx.Client(
                           transport=_transport([], _lineups_html())),
                       absence=True, absence_damp=0.75)
    off = fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                        client=httpx.Client(
                            transport=_transport([], _lineups_html())),
                        absence=False)
    assert off["absence_damp"].isna().all()
    assert len(off) <= len(on)


# --- v8a F5: the free text and the verdicts --------------------------------

_DETAIL_HTML = """
<table><tr>
<td>Player Bukayo Saka</td><td>Reason Hamstring Injury</td>
<td>Further Detail Arteta said he is close but Sunday may come too soon</td>
<td>Potential Return 20/09/2026</td><td>Status Doubtful</td>
</tr></table>
"""


def test_the_further_detail_cell_is_parsed_and_kept():
    """Today it is read only to be thrown away. It is the sharpest sentence
    on the page and the whole input to the classifier."""
    from gaffer.data.news.premierinjuries import parse_injury_table

    out = parse_injury_table(_DETAIL_HTML)
    assert "further_detail" in out.columns
    assert "too soon" in out.iloc[0]["further_detail"]


def test_the_detail_never_reaches_the_injury_type():
    """A quote names body parts belonging to whatever else the sentence is
    about; the Reason column is still the only source of the type."""
    from gaffer.data.news.premierinjuries import parse_injury_table

    out = parse_injury_table(_DETAIL_HTML)
    assert out.iloc[0]["injury_type"] == "hamstring"


def test_a_disabled_classifier_makes_no_subprocess_call(tmp_path,
                                                        monkeypatch):
    from gaffer.data.news import premierinjuries as pi

    calls = []
    monkeypatch.setattr(pi, "classify_news",
                        lambda *a, **k: calls.append(1))
    out = pi.fetch_injuries(_players(), _teams(), cache_dir=tmp_path,
                            client=_client(_DETAIL_HTML), classifier=False,
                            shadow=False)
    assert calls == []
    assert "llm_verdict" in out.columns and out["llm_verdict"].isna().all()


def test_the_shadow_pass_attaches_verdicts_without_serving_them(tmp_path,
                                                                monkeypatch):
    import pandas as pd

    from gaffer.data.news import premierinjuries as pi

    verdicts = pd.DataFrame([{"code": 1, "verdict": "rotation_risk",
                              "confidence": 0.8, "model": "fake",
                              "text_hash": "h", "fetched_at": "now"}])
    monkeypatch.setattr(pi, "classify_news", lambda *a, **k: verdicts)
    out = pi.fetch_injuries(_players(), _teams(), cache_dir=tmp_path,
                            client=_client(_DETAIL_HTML), classifier=False,
                            shadow=True)
    assert set(out.columns) >= {"llm_verdict", "llm_confidence"}


def test_a_verdict_for_a_player_with_no_injury_row_still_travels(tmp_path,
                                                                 monkeypatch):
    """The bootstrap ``news`` column speaks about players the injury table
    never lists, and a verdict with no carrier row would be a verdict nobody
    ever logs."""
    import pandas as pd

    from gaffer.data.news import premierinjuries as pi

    verdicts = pd.DataFrame([{"code": 99, "verdict": "rotation_risk",
                              "confidence": 0.6, "model": "fake",
                              "text_hash": "h", "fetched_at": "now"}])
    monkeypatch.setattr(pi, "classify_news", lambda *a, **k: verdicts)
    out = pi.fetch_injuries(_players(), _teams(), cache_dir=tmp_path,
                            client=_client(_DETAIL_HTML), classifier=False,
                            shadow=True)
    row = out[out["code"] == 99]
    assert len(row) == 1
    assert pd.isna(row.iloc[0]["injury_type"])


def test_a_classifier_that_dies_leaves_the_frame_alone(tmp_path, monkeypatch):
    from gaffer.data.news import premierinjuries as pi

    def boom(*a, **k):
        raise RuntimeError("the CLI is not logged in")

    monkeypatch.setattr(pi, "classify_news", boom)
    out = pi.fetch_injuries(_players(), _teams(), cache_dir=tmp_path,
                            client=_client(_DETAIL_HTML), classifier=False,
                            shadow=True)
    assert out["llm_verdict"].isna().all()
