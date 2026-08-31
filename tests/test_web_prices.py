"""``/api/prices/movers``: the alert list the advice payload cannot carry.

``advise.py`` is protected, so the payload's watch set is frozen at
squad-plus-plan and cannot learn about the watchlist. This endpoint is where
the wider set lives, and the tests are mostly about the two properties that
buys: it never reaches the network, and it never lies about how old its
reading is.
"""

from __future__ import annotations

import json
import os

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import SolveState, save_solve_state
from gaffer.web.app import create_app

GW = 5

PLAYERS = pd.DataFrame({
    "code": [11, 22, 33, 44, 55],
    "name": ["Saka", "Haaland", "Rice", "Starred", "Nobody"],
    "position": ["MID", "FWD", "MID", "DEF", "GKP"],
    "team_code": [3, 4, 3, 5, 6],
    "now_cost": [101, 150, 65, 45, 40],
    "price_change_percent": [98.5, -100.0, 12.0, 95.0, 99.9],
    "price_change_calibrating": [False, False, False, True, False],
})

POOL = pd.DataFrame([
    {"code": 11, "name": "Saka", "position": "MID", "team_code": 3,
     "cost": 101, "sell": 101, "owned": True, "gw": GW, "ep_raw": 5.0},
])

ADVICE = {"gw": GW, "buys": [{"code": 22, "name": "Haaland"}],
          "sells": [{"code": 33, "name": "Rice"}], "hits": 0,
          "xi": [], "bench": [], "expected_pts": 60.0,
          "captain": {"code": 11, "name": "Saka"},
          "vice": {"code": 22, "name": "Haaland"}}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    (tmp_path / f"reports/gw{GW}-advice.json").write_text(json.dumps(ADVICE))
    save_solve_state(SolveState(
        gw=GW, gws=[GW], deadline="2026-09-01T11:00:00Z",
        generated_at="2026-08-31T09:00:00Z", mode="weekly", bank=0,
        free_transfers=1, owned_codes=[11], lam=0.0, league_eo={},
        avail_by_gw={GW: []},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.0, "horizon": 1, "hit_cost": 4,
             "max_transfers": 2, "bank_weight": 0.0},
        pool=POOL))
    return TestClient(create_app())


def _rows(client):
    return {r["code"]: r for r in client.get("/api/prices/movers")
            .json()["rows"]}


def test_the_squad_and_the_plan_are_watched(client):
    rows = _rows(client)
    assert rows[11]["source"] == "squad"
    assert rows[22]["source"] == "plan"


def test_a_player_in_neither_is_not_watched_however_close_he_is(client):
    """Player 55 is at 99.9% and belongs to nobody. An alert about a player
    the manager has no relationship with is noise."""
    assert 55 not in _rows(client)


def test_starring_a_player_puts_him_in_the_watch_set(client):
    assert 44 not in _rows(client)
    client.post("/api/watchlist", json={"code": 44})
    assert _rows(client)[44]["source"] == "watchlist"


def test_a_starred_squad_player_reads_as_squad(client):
    """A4's resolution order. "Why is he here?" has one answer per row, and
    the strongest reason is the true one."""
    client.post("/api/watchlist", json={"code": 11})
    assert _rows(client)[11]["source"] == "squad"


def test_below_the_threshold_is_not_a_mover(client):
    """Rice is in the plan and sitting at 12% — watched, but not moving."""
    assert 33 not in _rows(client)


def test_the_direction_and_the_calibrating_caveat_ride_the_row(client):
    client.post("/api/watchlist", json={"code": 44})
    rows = _rows(client)
    assert rows[11]["direction"] == "rise"
    assert rows[22]["direction"] == "drop"
    assert rows[44]["calibrating"] is True
    assert rows[11]["calibrating"] is False


def test_the_rows_are_sorted_by_how_close_the_change_is(client):
    codes = [r["code"] for r in client.get("/api/prices/movers")
             .json()["rows"]]
    assert codes == [22, 11]        # |-100| before |98.5|


def test_the_payload_says_how_old_its_reading_is(client, tmp_path):
    """A4: a movers strip showing Tuesday's predictor on a Friday evening is
    worse than no strip at all, so the age is a field and the card prints
    it."""
    path = tmp_path / "data/live/players.parquet"
    os.utime(path, (1_756_000_000, 1_756_000_000))
    body = client.get("/api/prices/movers").json()
    assert body["as_of"].startswith("2025-")
    assert body["available"] is True


def test_no_player_snapshot_is_an_unavailable_panel_not_a_500(client,
                                                              tmp_path):
    (tmp_path / "data/live/players.parquet").unlink()
    body = client.get("/api/prices/movers").json()
    assert body == {"available": False, "as_of": None, "rows": []}


def test_no_solve_state_still_serves_the_watchlist(client, tmp_path):
    """A clone that has never solved has no squad and no plan, but a star is
    a star."""
    client.post("/api/watchlist", json={"code": 44})
    for name in tmp_path.glob("reports/solve_state*"):
        name.unlink()
    for name in tmp_path.glob("reports/gw*-advice.json"):
        name.unlink()
    rows = _rows(client)
    assert list(rows) == [44]
    assert rows[44]["source"] == "watchlist"


def test_a_corrupt_players_snapshot_is_unavailable_not_a_500(client,
                                                             tmp_path):
    (tmp_path / "data/live/players.parquet").write_text("garbage")
    assert client.get("/api/prices/movers").json()["available"] is False


def test_the_endpoint_never_touches_the_network(client, monkeypatch):
    """A card on a page must not make an API call on a page load — least of
    all on the Thursday evening everybody is loading the page."""
    def boom(*_args, **_kwargs):
        raise AssertionError("the movers card reached the network")

    monkeypatch.setattr("gaffer.api.client.FPLClient.get_bootstrap", boom)
    assert client.get("/api/prices/movers").status_code == 200
