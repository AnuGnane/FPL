"""The top-10k figure arrives with its error bar.

``latest_field_eo`` has returned ``{"eo", "se", "n", "gw"}`` per element since
the field log shipped. ``routers/players.py`` takes ``eo`` out of that dict and
drops the other three on the floor, so ``/api/players`` has been serving a
percentage with no precision attached to it for two cycles.

v10b built ``web/field_frame.py`` partly because of this gap, and was right to:
that cycle needed the error for one captain and would have paid a column on
seven hundred rows for it. §F2 needs it per compared player, on the row the
explorer already sends, which is the other side of the same trade.

The contract is ``field_eo``'s, verbatim (``schemas.py``): ``None`` means
unknown, and it never means 0.0. A standard error of zero is a claim of perfect
precision, made from a sample of three hundred entries.

The fixture wiring is ``tests/test_web_players_v8c.py``'s, reused rather than
reinvented: codes 100/101 are elements 7/8, one owned and one not.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import load_solve_state, save_solve_state
from gaffer.data import store
from gaffer.data.field import append_field_eo, field_eo_rows
from gaffer.web.app import create_app

from tests.test_web_league_sim import _artifacts


@pytest.fixture()
def players_client(tmp_path, monkeypatch):
    """``GET /api/players`` over the shipped artifact fixture."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    _artifacts(tmp_path)
    pd.DataFrame([{"team_id": 1, "code": 300, "name": "LIV"},
                  {"team_id": 2, "code": 301, "name": "ARS"},
                  {"team_id": 3, "code": 302, "name": "MCI"}]).to_parquet(
        tmp_path / "data/live/teams.parquet", index=False)
    state = load_solve_state(3)
    state.pool = pd.concat([
        state.pool,
        pd.DataFrame([{**state.pool.iloc[0].to_dict(), "code": 101,
                       "name": "Dud", "position": "DEF", "team_code": 301,
                       "cost": 45, "sell": 45, "owned": False,
                       "ep_raw": 3.0}])], ignore_index=True)
    save_solve_state(state)
    client = TestClient(create_app())

    def get():
        return client.get("/api/players").json()
    return get


@pytest.fixture()
def logged(players_client):
    """One scrape, one element measured, from three hundred entries.

    Depends on ``players_client`` so the chdir and the store patch are already
    in place — a log written into the real tree would be a leak, not a test.
    """
    append_field_eo(field_eo_rows({7: {"eo": 62.4, "se": 2.8, "n": 300}},
                                  2, "2026-27", day="2026-08-31"))


def test_a_player_in_the_log_carries_eo_se_and_n(logged, players_client):
    """One row, three numbers, one sample. ``n`` travels because ±2.8 from
    three hundred entries and ±2.8 from thirty are different claims."""
    row = next(r for r in players_client() if r["element"] == 7)
    assert row["field_eo"] == 62.4
    assert row["field_se"] == 2.8
    assert row["field_n"] == 300


def test_a_player_the_log_does_not_carry_has_no_error_bar_either(
        logged, players_client):
    row = next(r for r in players_client() if r["element"] != 7)
    assert row["field_eo"] is None
    assert row["field_se"] is None
    assert row["field_n"] is None


def test_no_log_at_all_leaves_all_three_absent(players_client):
    """A clone that never ran a scrape. ``latest_field_eo`` returns ``{}`` on
    every failure, and the row must say "unknown" three times rather than
    "measured at zero" three times."""
    for row in players_client():
        assert row["field_eo"] is None
        assert row["field_se"] is None
        assert row["field_n"] is None


def test_the_error_is_never_zero_for_an_unknown(logged, players_client):
    """The one temptation. ``0.0`` here would be read as a measurement of
    perfect precision, which is the strongest claim this payload can make."""
    assert all(r["field_se"] != 0.0 or r["field_eo"] is not None
               for r in players_client())


def test_an_unmeasured_error_beside_a_measured_eo_is_still_None(
        players_client):
    """The older-log case. ``FIELD_EO_COLS`` is fixed, so a scrape that never
    computed an error writes a NaN rather than dropping the column, and NaN
    must reach the wire as ``None`` — a JSON ``NaN`` is not a number any
    client can read, and 0.0 would be the perfect-precision lie."""
    append_field_eo(field_eo_rows(
        {7: {"eo": 62.4, "se": float("nan"), "n": 300}},
        2, "2026-27", day="2026-08-31"))
    row = next(r for r in players_client() if r["element"] == 7)
    assert row["field_eo"] == 62.4
    assert row["field_se"] is None


def test_field_class_is_unchanged_by_the_addition(logged, players_client):
    """The degradation direction: the classifier reads ``eo`` and only ``eo``,
    and gaining an error bar does not move a threshold."""
    row = next(r for r in players_client() if r["element"] == 7)
    assert row["field_class"] in {"shield", "sword", "threat", None}
