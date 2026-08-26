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
                                  "expected_return_date"]
    saka = rows[rows["name"] == "Bukayo Saka"].iloc[0]
    assert saka["club"] == "Arsenal"
    assert saka["injury_type"] == "hamstring"
    assert saka["status"] == "out"
    assert saka["expected_return_date"] == pd.Timestamp("2026-09-12").date()


def test_parse_injury_table_keeps_a_row_with_no_return_date():
    """"Doubtful, no date" is real information — it must not be dropped just
    because the return column is blank."""
    from gaffer.data.news.premierinjuries import parse_injury_table

    rows = parse_injury_table(_injury_html())
    palmer = rows[rows["name"] == "Cole Palmer"].iloc[0]
    assert palmer["expected_return_date"] is None
    assert palmer["status"] == "doubtful"


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
    # Barnsley's player is unmatched (4/5 = 80%, above the floor).
    assert sorted(out["code"]) == [100, 101, 102, 103]
    assert list(out.columns) == ["code", "injury_type", "news_status",
                                 "expected_return_date", "source",
                                 "fetched_at"]
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
