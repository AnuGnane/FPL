"""The top-10k threshold (holiday F-4): page 200's last row, read and banked.

The fixture ``tests/data/top10k_standings_page200.json`` is the overall
league's page 200 as served on 2026-10-07, with entry ids and names replaced
at record time. Its last row is rank_sort 10,000 on 398 points.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from gaffer.config import Config
from gaffer.data import store
from gaffer.data.top_threshold import (
    THRESHOLD_COLS,
    THRESHOLD_RANK,
    append_threshold,
    bank_threshold,
    fetch_threshold,
    load_threshold_log,
    parse_threshold,
    threshold_rows,
    threshold_series,
)

FIXTURE = Path(__file__).parent / "data" / "top10k_standings_page200.json"

EVENTS = pd.DataFrame([
    {"gw": 6, "deadline_time": "2026-10-02T17:30:00Z"},
    {"gw": 7, "deadline_time": "2026-10-16T17:30:00Z"},
])


def _page() -> dict:
    return json.loads(FIXTURE.read_text())


class _Client:
    def __init__(self, payload=None, boom=False):
        self.payload = payload if payload is not None else _page()
        self.boom = boom
        self.calls: list[tuple[int, int]] = []

    def get_league_standings(self, league_id, page=1):
        self.calls.append((league_id, page))
        if self.boom:
            raise RuntimeError("the FPL API is down")
        return self.payload


@pytest.fixture()
def here(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr("gaffer.data.top_threshold.snap_date",
                        lambda *a: "2026-10-07")
    return tmp_path


def test_the_threshold_is_the_ten_thousandth_row_of_the_recorded_page():
    reading = parse_threshold(_page())
    assert THRESHOLD_RANK == 10_000
    assert reading == {"rank_sort": 10_000, "rank": 9881, "total": 398,
                       "event_total": 69,
                       "last_updated": "2026-10-07T00:59:48Z"}


def test_a_page_served_out_of_order_still_names_the_last_position():
    page = _page()
    page["standings"]["results"].reverse()
    assert parse_threshold(page)["rank_sort"] == 10_000


def test_nothing_that_names_an_entry_survives_the_parse():
    assert set(parse_threshold(_page())) == set(THRESHOLD_COLS) - {
        "season", "gw", "snap_date"}


@pytest.mark.parametrize("payload", [
    {}, {"standings": {"results": []}}, {"standings": None},
    {"standings": {"results": [{"rank_sort": 1}]}}])
def test_an_empty_or_reshaped_page_is_no_reading(payload):
    assert parse_threshold(payload) is None


def test_the_fetch_reads_page_two_hundred_of_the_overall_league():
    client = _Client()
    assert fetch_threshold(client)["total"] == 398
    assert client.calls == [(314, 200)]


def test_a_dead_fetch_is_no_reading_rather_than_a_raise():
    assert fetch_threshold(_Client(boom=True)) is None


def test_a_bank_logs_the_last_passed_deadlines_week_and_says_so(here, capsys):
    now = pd.Timestamp("2026-10-07T12:00:00Z")
    assert bank_threshold(_Client(), EVENTS, "2026-27", now=now) == 1
    assert "Top-10k threshold: 398 points at rank 10000 for gw6 at " \
        "2026-10-07." in capsys.readouterr().out
    log = load_threshold_log()
    assert list(log.columns) == THRESHOLD_COLS
    assert log.iloc[0][["season", "gw", "total"]].tolist() == [
        "2026-27", 6, 398]


def test_two_banks_in_one_day_leave_one_row(here):
    now = pd.Timestamp("2026-10-07T12:00:00Z")
    bank_threshold(_Client(), EVENTS, "2026-27", now=now)
    bank_threshold(_Client(), EVENTS, "2026-27", now=now)
    assert len(load_threshold_log()) == 1


def test_before_the_first_deadline_nothing_is_fetched_or_printed(here, capsys):
    client = _Client()
    now = pd.Timestamp("2026-09-01T12:00:00Z")
    assert bank_threshold(client, EVENTS, "2026-27", now=now) is None
    assert client.calls == []
    assert capsys.readouterr().out == ""


def test_a_dead_fetch_prints_one_line_and_banks_nothing(here, capsys):
    now = pd.Timestamp("2026-10-07T12:00:00Z")
    assert bank_threshold(_Client(boom=True), EVENTS, "2026-27",
                          now=now) is None
    printed = capsys.readouterr().out.strip().splitlines()
    assert len(printed) == 1
    assert printed[0].startswith("top-10k threshold not banked:")
    assert load_threshold_log().empty


def test_the_series_takes_each_weeks_latest_day_within_one_season(here):
    def _row(gw, day, total, season="2026-27"):
        reading = {"rank_sort": 10_000, "rank": 9_990, "total": total,
                   "event_total": 50, "last_updated": ""}
        return threshold_rows(reading, gw, season, day)

    for rows in (_row(5, "2026-09-27", 300), _row(5, "2026-09-30", 331),
                 _row(6, "2026-10-04", 380), _row(6, "2025-10-04", 999,
                                                  season="2025-26")):
        append_threshold(rows)
    assert threshold_series("2026-27") == {5: 331, 6: 380}
    assert threshold_series("2025-26") == {6: 999}
    assert threshold_series("2024-25") == {}


def test_the_snapshot_job_banks_the_threshold_beside_its_rows(here,
                                                               monkeypatch,
                                                               capsys):
    from gaffer.snapshot import run_snapshot

    client = _Client()
    client.get_bootstrap = lambda: {"events": []}
    monkeypatch.setattr("gaffer.api.client.FPLClient", lambda *a, **k: client)
    monkeypatch.setattr("gaffer.data.bootstrap.build_players",
                        lambda raw: pd.DataFrame())
    monkeypatch.setattr("gaffer.data.bootstrap.build_teams",
                        lambda raw: pd.DataFrame())
    monkeypatch.setattr("gaffer.data.bootstrap.build_events",
                        lambda raw: EVENTS.assign(finished=[True, False]))
    monkeypatch.setattr("gaffer.snapshot.news_availability",
                        lambda *a, **kw: pd.DataFrame())
    run_snapshot(cfg=Config(entry_id=1, league_id=2,
                            current_season="2026-27"))
    assert "Top-10k threshold: 398 points" in capsys.readouterr().out
    assert threshold_series("2026-27")


def test_the_field_switch_off_leaves_the_threshold_unfetched(here,
                                                             monkeypatch):
    from gaffer.snapshot import run_snapshot

    client = _Client()
    client.get_bootstrap = lambda: {"events": []}
    monkeypatch.setattr("gaffer.api.client.FPLClient", lambda *a, **k: client)
    monkeypatch.setattr("gaffer.data.bootstrap.build_events",
                        lambda raw: EVENTS.assign(finished=[True, False]))
    monkeypatch.setattr("gaffer.data.bootstrap.build_players",
                        lambda raw: pd.DataFrame())
    monkeypatch.setattr("gaffer.data.bootstrap.build_teams",
                        lambda raw: pd.DataFrame())
    monkeypatch.setattr("gaffer.snapshot.news_availability",
                        lambda *a, **kw: pd.DataFrame())
    run_snapshot(cfg=Config(entry_id=1, league_id=2, current_season="2026-27",
                            field_scrape=False))
    assert client.calls == []
