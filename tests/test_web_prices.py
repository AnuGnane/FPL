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


# --- the freshest of the two price files ------------------------------

SNAPSHOT_MTIME = 1_756_000_000        # 2025-08-24, and its own UTC day


def _age_the_snapshot(tmp_path):
    path = tmp_path / "data/live/players.parquet"
    os.utime(path, (SNAPSHOT_MTIME, SNAPSHOT_MTIME))


def _bank_price_log(tmp_path, day: str, percent: dict[int, float]):
    codes = sorted(percent)
    pd.DataFrame({
        "snap_date": [day] * len(codes),
        "code": codes,
        "now_cost": pd.array([66] * len(codes), dtype="Int64"),
        "price_change_percent": [float(percent[c]) for c in codes],
        "direction": pd.array(["rise"] * len(codes), dtype="string"),
        "calibrating": [False] * len(codes),
    }).to_parquet(tmp_path / "data/live/price_log.parquet", index=False)


def test_a_newer_price_log_is_what_the_card_shows(client, tmp_path):
    """``players.parquet`` is only rewritten by ``advise`` and
    ``refresh-data``, and the 23:15 job banks the league every night. On a
    Friday whose last pipeline run was Tuesday, the log is the reading about
    tonight and the snapshot is three days of nothing."""
    _age_the_snapshot(tmp_path)
    _bank_price_log(tmp_path, "2025-08-25", {11: 2.0, 22: -5.0, 33: 99.0})
    rows = _rows(client)
    assert set(rows) == {33}
    assert rows[33]["name"] == "Rice"      # the log banks no name
    assert rows[33]["now_cost"] == 6.6     # and the cost comes with it
    assert rows[33]["price_change_percent"] == 99.0


def test_the_card_says_which_file_it_is_quoting(client, tmp_path):
    """``as_of`` is the only field the card has to describe its reading, so a
    swapped source has to travel in it — an age that silently meant a
    different file would be a lie in the one place this card cannot afford
    one."""
    _age_the_snapshot(tmp_path)
    body = client.get("/api/prices/movers").json()
    assert body["as_of"].startswith("2025-08-24")
    assert "price log" not in body["as_of"]

    _bank_price_log(tmp_path, "2025-08-25", {33: 99.0})
    as_of = client.get("/api/prices/movers").json()["as_of"]
    assert "price log" in as_of


def test_a_price_log_no_newer_than_the_snapshot_changes_nothing(client,
                                                                 tmp_path):
    """The log's key is a UTC day, so a same-day tie goes to the snapshot the
    pipeline just wrote."""
    _age_the_snapshot(tmp_path)
    before = client.get("/api/prices/movers").json()
    _bank_price_log(tmp_path, "2025-08-24", {33: 99.0})
    assert client.get("/api/prices/movers").json() == before


def test_a_corrupt_price_log_is_the_behaviour_that_existed_before_it(
        client, tmp_path):
    _age_the_snapshot(tmp_path)
    before = client.get("/api/prices/movers").json()
    (tmp_path / "data/live/price_log.parquet").write_text("garbage")
    assert client.get("/api/prices/movers").json() == before


def test_the_endpoint_never_touches_the_network(client, monkeypatch):
    """A card on a page must not make an API call on a page load — least of
    all on the Thursday evening everybody is loading the page."""
    def boom(*_args, **_kwargs):
        raise AssertionError("the movers card reached the network")

    monkeypatch.setattr("gaffer.api.client.FPLClient.get_bootstrap", boom)
    assert client.get("/api/prices/movers").status_code == 200
