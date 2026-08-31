"""F4: the field-EO column and its sword/shield reading.

Pure display over ``field_eo_log``. The rail that matters is that an absent
log leaves the column *absent* — null on every row — rather than zero, because
"the top 10k do not own him" and "we have never scraped the top 10k" are
opposite statements and a nought would print the wrong one.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import load_solve_state, save_solve_state
from gaffer.data import store
from gaffer.data.field import append_field_eo, field_eo_rows
from gaffer.web.app import create_app
from gaffer.web.routers.players import field_class

# Reuse the artifact fixture the league-sim suite builds; codes 100 (owned,
# element 7) and 101 (not owned, element 8).
from tests.test_web_league_sim import _artifacts


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    _artifacts(tmp_path)
    # The league-sim fixture has no team table; the explorer names teams and
    # 422s without one, so this suite adds the three the fixture's players
    # belong to rather than reaching into the other suite's artifacts.
    pd.DataFrame([{"team_id": 1, "code": 300, "name": "LIV"},
                  {"team_id": 2, "code": 301, "name": "ARS"},
                  {"team_id": 3, "code": 302, "name": "MCI"}]).to_parquet(
        tmp_path / "data/live/teams.parquet", index=False)
    # The explorer only shows candidates, and the league-sim fixture's pool is
    # the one owned player. Code 101 is this suite's *un*owned case — the one
    # the sword/shield quadrants need — so it joins the pool here.
    state = load_solve_state(3)
    state.pool = pd.concat([
        state.pool,
        pd.DataFrame([{**state.pool.iloc[0].to_dict(), "code": 101,
                       "name": "Dud", "position": "DEF", "team_code": 301,
                       "cost": 45, "sell": 45, "owned": False,
                       "ep_raw": 3.0}])], ignore_index=True)
    save_solve_state(state)
    return TestClient(create_app())


def _log(gw=2, table=None):
    append_field_eo(field_eo_rows(
        table or {7: {"eo": 78.0, "se": 2.0, "n": 300},
                  8: {"eo": 4.0, "se": 1.0, "n": 300}},
        gw, "2026-27", day="2026-09-12"))


@pytest.mark.parametrize("owned,eo,expected", [
    (True, 78.0, "shield"),
    (True, 4.0, "sword"),
    (False, 78.0, "threat"),
    (False, 4.0, None),
    (True, None, None),
])
def test_the_classification_is_ownership_crossed_with_the_field(owned, eo,
                                                                expected):
    assert field_class(owned, eo) == expected


def test_the_column_is_absent_without_a_log(client):
    rows = client.get("/api/players").json()
    assert all(r["field_eo"] is None for r in rows)
    assert all(r["field_class"] is None for r in rows)


def test_the_column_carries_the_latest_scrape(client):
    _log()
    rows = {r["code"]: r for r in client.get("/api/players").json()}
    assert rows[100]["field_eo"] == 78.0
    assert rows[101]["field_eo"] == 4.0


def test_a_player_i_own_that_the_field_owns_is_a_shield(client):
    _log()
    rows = {r["code"]: r for r in client.get("/api/players").json()}
    assert rows[100]["field_class"] == "shield"


def test_a_player_the_field_ignores_that_i_do_not_own_gets_no_label(client):
    _log()
    rows = {r["code"]: r for r in client.get("/api/players").json()}
    assert rows[101]["field_class"] is None


def test_a_player_missing_from_the_scrape_is_null_not_zero(client):
    """Absent from a sparse table means "no sampled entry started him", which
    the log records by omission. The column has to say "unknown" rather than
    invent a 0.0 the user would read as a differential."""
    _log(table={7: {"eo": 78.0, "se": 2.0, "n": 300}})
    rows = {r["code"]: r for r in client.get("/api/players").json()}
    assert rows[101]["field_eo"] is None


def test_a_corrupt_log_does_not_take_the_explorer_down(client, monkeypatch):
    """The router must call the log read inside a guard. A parquet file that
    was half-written when a laptop slept is a bad afternoon for one column,
    not for the whole player explorer."""
    def _boom():
        raise RuntimeError("corrupt parquet")

    monkeypatch.setattr("gaffer.web.routers.players.latest_field_eo", _boom)
    res = client.get("/api/players")
    assert res.status_code == 200
    assert all(r["field_eo"] is None for r in res.json())
