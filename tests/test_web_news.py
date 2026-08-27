"""GET /api/news/{gw} — what the news layer moved, and on what evidence."""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import save_availability
from gaffer.data import store
from gaffer.news_shadow import SHADOW_COLS, SHADOW_PATH
from gaffer.web.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    return TestClient(create_app(), raise_server_exceptions=False)


def _shadow(rows) -> None:
    store.save(pd.DataFrame(rows, columns=SHADOW_COLS), SHADOW_PATH)


def _players() -> None:
    store.save(pd.DataFrame([
        {"code": 1, "element": 11, "name": "Gibbs-White", "position": "MID",
         "team_id": 17, "team_code": 17, "now_cost": 70, "status": "d",
         "news": "Knock - 75% chance of playing", "chance_of_playing": 75.0,
         "selected_by_percent": 12.0, "form": 4.0, "points_per_game": 4.2,
         "ep_next": 4.0, "price_change_percent": 0.0,
         "price_change_calibrating": False, "penalties_order": 1.0,
         "direct_freekicks_order": 1.0,
         "corners_and_indirect_freekicks_order": 2.0},
        {"code": 2, "element": 12, "name": "Fit Lad", "position": "DEF",
         "team_id": 3, "team_code": 3, "now_cost": 45, "status": "a",
         "news": "", "chance_of_playing": None,
         "selected_by_percent": 3.0, "form": 2.0, "points_per_game": 3.0,
         "ep_next": 3.0, "price_change_percent": 0.0,
         "price_change_calibrating": False, "penalties_order": None,
         "direct_freekicks_order": None,
         "corners_and_indirect_freekicks_order": None},
    ]), "live/players.parquet")
    store.save(pd.DataFrame([{"code": 17, "team_id": 17,
                              "name": "Nott'm Forest", "short_name": "NFO"},
                             {"code": 3, "team_id": 3, "name": "Arsenal",
                              "short_name": "ARS"}]), "live/teams.parquet")


def test_news_with_no_shadow_log_is_an_empty_panel_not_an_error(client):
    body = client.get("/api/news/5").json()
    assert body["gw"] == 5 and body["moved"] == 0 and body["rows"] == []


def test_news_lists_only_the_players_the_layer_actually_moved(client,
                                                              tmp_path):
    _players()
    _shadow([
        {"season": "2026-27", "gw": 5, "code": 1, "p_play_news": 0.05,
         "p_play_flags": 0.75, "e_min_news": 4.0, "e_min_flags": 62.0,
         "run_at": "2026-09-04T09:00:00"},
        {"season": "2026-27", "gw": 5, "code": 2, "p_play_news": 0.9,
         "p_play_flags": 0.9, "e_min_news": 80.0, "e_min_flags": 80.0,
         "run_at": "2026-09-04T09:00:00"},
    ])
    body = client.get("/api/news/5").json()
    assert body["moved"] == 1
    row = body["rows"][0]
    assert row["name"] == "Gibbs-White"
    assert row["team_name"] == "Nott'm Forest"
    assert row["p_play_news"] == 0.05 and row["p_play_flags"] == 0.75
    assert row["e_min_news"] == 4.0 and row["e_min_flags"] == 62.0


def test_news_carries_the_official_flag_as_evidence(client, tmp_path):
    _players()
    _shadow([{"season": "2026-27", "gw": 5, "code": 1, "p_play_news": 0.05,
              "p_play_flags": 0.75, "e_min_news": 4.0, "e_min_flags": 62.0,
              "run_at": "2026-09-04T09:00:00"}])
    row = client.get("/api/news/5").json()["rows"][0]
    assert row["status"] == "d"
    assert row["chance_of_playing"] == 75.0
    assert row["official_note"] == "Knock - 75% chance of playing"


def test_news_carries_the_availability_snapshot_as_evidence(client, tmp_path):
    """The Gibbs-White case reads: official 75% · FFS out · news 0%."""
    _players()
    _shadow([{"season": "2026-27", "gw": 5, "code": 1, "p_play_news": 0.05,
              "p_play_flags": 0.75, "e_min_news": 4.0, "e_min_flags": 62.0,
              "run_at": "2026-09-04T09:00:00"}])
    save_availability(pd.DataFrame([
        {"code": 1, "status": "d", "chance_of_playing": 75,
         "injury_type": "knock", "expected_return_gw": 6,
         "p_start_hint": 0.0, "source": "premierinjuries|lineups",
         "fetched_at": "2026-09-04T08:00:00Z"}]), 5)
    row = client.get("/api/news/5").json()["rows"][0]
    assert row["injury_type"] == "knock"
    assert row["expected_return_gw"] == 6
    assert row["p_start_hint"] == 0.0
    assert row["lineup_hint"] == "out"
    assert row["source"] == "premierinjuries|lineups"


def test_the_lineup_hint_is_named_not_left_as_a_probability(client, tmp_path):
    _players()
    _shadow([{"season": "2026-27", "gw": 5, "code": 1, "p_play_news": 0.5,
              "p_play_flags": 0.9, "e_min_news": 40.0, "e_min_flags": 80.0,
              "run_at": "2026-09-04T09:00:00"}])
    for hint, want in ((1.0, "xi"), (0.5, "doubt"), (0.0, "out"),
                       (None, None)):
        save_availability(pd.DataFrame([
            {"code": 1, "status": "a", "chance_of_playing": None,
             "injury_type": None, "expected_return_gw": None,
             "p_start_hint": hint, "source": "lineups",
             "fetched_at": "x"}]), 5)
        assert client.get("/api/news/5").json()["rows"][0]["lineup_hint"] \
            == want


def test_only_the_latest_run_of_the_gameweek_is_read(client, tmp_path):
    """The log is appended every run. Two rows for one player are two
    readings of the same week, and the newest is the one that shipped."""
    _players()
    _shadow([
        {"season": "2026-27", "gw": 5, "code": 1, "p_play_news": 0.05,
         "p_play_flags": 0.75, "e_min_news": 4.0, "e_min_flags": 62.0,
         "run_at": "2026-09-03T09:00:00"},
        {"season": "2026-27", "gw": 5, "code": 1, "p_play_news": 0.60,
         "p_play_flags": 0.75, "e_min_news": 50.0, "e_min_flags": 62.0,
         "run_at": "2026-09-04T09:00:00"},
    ])
    rows = client.get("/api/news/5").json()["rows"]
    assert len(rows) == 1 and rows[0]["p_play_news"] == 0.60


def test_rows_are_ordered_by_how_far_the_layer_moved_them(client, tmp_path):
    _players()
    _shadow([
        {"season": "2026-27", "gw": 5, "code": 2, "p_play_news": 0.80,
         "p_play_flags": 0.90, "e_min_news": 70.0, "e_min_flags": 80.0,
         "run_at": "2026-09-04T09:00:00"},
        {"season": "2026-27", "gw": 5, "code": 1, "p_play_news": 0.05,
         "p_play_flags": 0.75, "e_min_news": 4.0, "e_min_flags": 62.0,
         "run_at": "2026-09-04T09:00:00"},
    ])
    assert [r["code"] for r in client.get("/api/news/5").json()["rows"]] \
        == [1, 2]


def test_a_gameweek_with_no_shadow_rows_is_an_empty_panel(client, tmp_path):
    _players()
    _shadow([{"season": "2026-27", "gw": 4, "code": 1, "p_play_news": 0.05,
              "p_play_flags": 0.75, "e_min_news": 4.0, "e_min_flags": 62.0,
              "run_at": "2026-09-04T09:00:00"}])
    assert client.get("/api/news/5").json()["moved"] == 0


def test_news_survives_a_missing_players_snapshot(client, tmp_path):
    """Names are a nicety; the numbers are the panel. A player the snapshot
    does not know is shown by his code."""
    _shadow([{"season": "2026-27", "gw": 5, "code": 1, "p_play_news": 0.05,
              "p_play_flags": 0.75, "e_min_news": 4.0, "e_min_flags": 62.0,
              "run_at": "2026-09-04T09:00:00"}])
    row = client.get("/api/news/5").json()["rows"][0]
    assert row["name"] == "1" and row["team_name"] == ""
