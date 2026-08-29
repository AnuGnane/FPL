"""GET /api/journal — the decision journal, cached to reports/journal.json."""

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import ADVICE_HISTORY
from gaffer.data import store
from gaffer.web.app import create_app
from gaffer.web.routers import journal as journal_router


class FakeClient:
    def __init__(self, picks=None):
        self._picks = picks or {}

    def get_entry_picks(self, entry_id, gw):
        if gw not in self._picks:
            raise RuntimeError(f"no picks for GW{gw}")
        return {"picks": self._picks[gw]}


def _history(gw=3):
    ADVICE_HISTORY.mkdir(parents=True, exist_ok=True)
    (ADVICE_HISTORY / f"gw{gw}-2026-08-21T09:00:00.json").write_text(json.dumps({
        "gw": gw,
        "xi": [{"code": 1, "name": "P1"}, {"code": 3, "name": "P3"}],
        "captain": {"code": 3, "name": "P3"},
        "buys": [{"code": 3, "name": "P3"}], "sells": [],
    }))


def _results():
    store.save(pd.DataFrame([
        {"code": 1, "gw": 3, "total_points": 4, "value": 100},
        {"code": 3, "gw": 3, "total_points": 9, "value": 80},
    ]), "live/player_gw.parquet")
    store.save(pd.DataFrame([
        {"code": 1, "element": 11, "name": "P1", "position": "MID",
         "team_id": 1, "team_code": 300, "now_cost": 100, "status": "a",
         "news": "", "chance_of_playing": None, "selected_by_percent": 1.0,
         "form": 1.0, "points_per_game": 1.0, "ep_next": 1.0,
         "price_change_percent": 0.0, "price_change_calibrating": False,
         "penalties_order": None, "direct_freekicks_order": None,
         "corners_and_indirect_freekicks_order": None},
    ]), "live/players.parquet")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(journal_router, "fpl_client",
                        lambda: FakeClient({3: [{"element": 11,
                                                 "is_captain": True,
                                                 "multiplier": 2,
                                                 "position": 1}]}))
    monkeypatch.setattr(journal_router, "entry_id", lambda: 7)
    return TestClient(create_app(), raise_server_exceptions=False)


def test_the_journal_lists_a_row_per_scored_gameweek(client):
    _history()
    _results()
    body = client.get("/api/journal").json()
    assert [r["gw"] for r in body["rows"]] == [3]
    assert body["rows"][0]["model_pts"] == 22
    assert body["rows"][0]["actual_pts"] == 8
    assert body["cumulative"][0]["delta"] == 14


def test_the_result_is_cached_to_reports_journal_json(client, tmp_path):
    _history()
    _results()
    client.get("/api/journal")
    cached = json.loads((tmp_path / "reports" / "journal.json").read_text())
    assert cached["rows"][0]["gw"] == 3


def test_a_cold_clone_is_an_empty_journal_not_an_error(client):
    resp = client.get("/api/journal")
    assert resp.status_code == 200
    assert resp.json()["rows"] == []
    assert resp.json()["cumulative"] == []


def test_no_entry_id_configured_is_an_empty_journal(client, monkeypatch):
    _history()
    _results()
    monkeypatch.setattr(journal_router, "entry_id", lambda: None)
    body = client.get("/api/journal").json()
    assert body["rows"] == []


def test_an_unreachable_fpl_api_is_an_empty_journal_not_a_500(client,
                                                              monkeypatch):
    _history()
    _results()

    def boom():
        raise RuntimeError("FPL API unavailable")

    monkeypatch.setattr(journal_router, "fpl_client", boom)
    resp = client.get("/api/journal")
    assert resp.status_code == 200
    assert resp.json()["rows"] == []
