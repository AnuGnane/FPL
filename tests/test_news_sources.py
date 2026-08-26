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
         "second_name": "Saka", "team_code": 3},
        {"code": 101, "name": "Gabriel", "first_name": "Gabriel",
         "second_name": "Magalhaes", "team_code": 3},
        {"code": 102, "name": "Haaland", "first_name": "Erling",
         "second_name": "Haaland", "team_code": 43},
        {"code": 103, "name": "Palmer", "first_name": "Cole",
         "second_name": "Palmer", "team_code": 8},
        {"code": 104, "name": "Rice", "first_name": "Declan",
         "second_name": "Rice", "team_code": 3},
    ])


def _teams() -> pd.DataFrame:
    return pd.DataFrame([
        {"code": 3, "name": "Arsenal", "short_name": "ARS"},
        {"code": 43, "name": "Man City", "short_name": "MCI"},
        {"code": 8, "name": "Chelsea", "short_name": "CHE"},
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


def _injury_html() -> str:
    return (FIXTURES / "premierinjuries.html").read_text()


def _transport(calls: list, text: str | None = None):
    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if text is None:
            return httpx.Response(503)
        return httpx.Response(200, text=text)
    return httpx.MockTransport(handle)


def test_parse_injury_table_reads_every_row():
    from gaffer.data.news.premierinjuries import parse_injury_table

    rows = parse_injury_table(_injury_html())
    assert len(rows) == 5
    assert list(rows.columns) == ["name", "club", "injury_type", "status",
                                  "expected_return_date", "news_chance_pct"]
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
                         client=client, now=now)
    # The unrostered player is unmatched (4/5 = 80%, above the floor), and
    # every match is made without a club column to key on.
    assert sorted(out["code"]) == [100, 101, 102, 103]
    assert list(out.columns) == ["code", "injury_type", "news_status",
                                 "expected_return_date", "news_chance_pct",
                                 "source", "fetched_at"]
    assert out.set_index("code").loc[102, "news_chance_pct"] == 75.0
    assert (out["source"] == "premierinjuries").all()
    assert len(calls) == 1

    # Same cache window: no second request.
    fetch_injuries(_players(), _teams(), cache_dir=tmp_path, client=client,
                   now=now + timedelta(hours=1))
    assert len(calls) == 1

    # Next window: one more.
    fetch_injuries(_players(), _teams(), cache_dir=tmp_path, client=client,
                   now=now + timedelta(hours=7))
    assert len(calls) == 2


def test_fetch_injuries_degrades_to_empty_when_the_host_is_down(tmp_path,
                                                                capsys):
    from gaffer.data.news.premierinjuries import INJURY_COLS, fetch_injuries

    client = httpx.Client(transport=_transport([], None))
    out = fetch_injuries(_players(), _teams(), cache_dir=tmp_path,
                         client=client)
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
                         client=client)
    assert out.empty
    assert "unavailable" in capsys.readouterr().out


def _lineups_html() -> str:
    return (FIXTURES / "ffs_lineups.html").read_text()


def test_parse_lineups_assigns_one_slot_per_named_player():
    from gaffer.data.news.lineups import P_START_HINT, parse_lineups

    rows = parse_lineups(_lineups_html())
    assert list(rows.columns) == ["name", "club", "slot"]
    by_name = dict(zip(rows["name"], rows["slot"]))
    assert by_name["Bukayo Saka"] == "start"
    assert by_name["Gabriel Magalhaes"] == "bench"
    assert by_name["Joe Bloggs"] == "out"
    assert P_START_HINT == {"start": 1.0, "bench": 0.25, "out": 0.0}


def test_parse_lineups_covers_every_fixture_block():
    from gaffer.data.news.lineups import parse_lineups

    rows = parse_lineups(_lineups_html())
    assert set(rows["club"]) == {"Arsenal", "Chelsea", "Man City"}
    # Arsenal names four (two starters, a sub, one unavailable), Chelsea and
    # Man City one apiece.
    assert len(rows) == 6


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
    assert out.loc[100, "p_start_hint"] == 1.0     # Saka starts
    assert out.loc[101, "p_start_hint"] == 0.25    # Gabriel benched
    assert out.loc[102, "p_start_hint"] == 1.0     # Haaland starts
    assert out.loc[104, "p_start_hint"] == 1.0     # Rice starts
    assert (out["source"] == "lineups").all()
    assert len(calls) == 1


def test_fetch_lineups_degrades_to_empty_when_the_page_is_down(tmp_path):
    from gaffer.data.news.lineups import LINEUP_COLS, fetch_lineups

    client = httpx.Client(transport=_transport([], None))
    out = fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                        client=client)
    assert out.empty
    assert list(out.columns) == LINEUP_COLS
