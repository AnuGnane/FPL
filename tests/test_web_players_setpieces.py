"""What the players endpoint serves once ``data/set_pieces.toml`` exists.

The badge and the numbers beside it have to agree. A badge that says "manual"
next to FPL's own order is worse than no badge at all: it tells a user his
correction reached the screen when it did not.

Two men at one club (300) and one at another (301), so the file can be shown
to speak about one club and not the other.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import (COMPONENT_COLS, SolveState, pool_rows,
                              save_components, save_solve_state)
from gaffer.web.app import create_app

PLAYERS = pd.DataFrame([
    {"code": 100, "element": 7, "name": "Incumbent", "position": "MID",
     "team_id": 1, "team_code": 300, "now_cost": 100, "status": "a",
     "news": "", "chance_of_playing": None, "selected_by_percent": 40.0,
     "form": 5.0, "points_per_game": 6.0, "ep_next": 6.0,
     "price_change_percent": 0.0, "price_change_calibrating": False,
     "penalties_order": 1.0, "direct_freekicks_order": 1.0,
     "corners_and_indirect_freekicks_order": 1.0},
    {"code": 101, "element": 8, "name": "Newcomer", "position": "MID",
     "team_id": 1, "team_code": 300, "now_cost": 80, "status": "a",
     "news": "", "chance_of_playing": None, "selected_by_percent": 10.0,
     "form": 3.0, "points_per_game": 4.0, "ep_next": 4.0,
     "price_change_percent": 0.0, "price_change_calibrating": False,
     "penalties_order": None, "direct_freekicks_order": None,
     "corners_and_indirect_freekicks_order": None},
    {"code": 102, "element": 9, "name": "Stranger", "position": "DEF",
     "team_id": 2, "team_code": 301, "now_cost": 45, "status": "a",
     "news": "", "chance_of_playing": None, "selected_by_percent": 5.0,
     "form": 1.0, "points_per_game": 2.0, "ep_next": 2.0,
     "price_change_percent": 0.0, "price_change_calibrating": False,
     "penalties_order": 1.0, "direct_freekicks_order": None,
     "corners_and_indirect_freekicks_order": None},
])

TEAMS = pd.DataFrame([{"team_id": 1, "code": 300, "name": "Liverpool",
                       "short_name": "LIV"},
                      {"team_id": 2, "code": 301, "name": "Arsenal",
                       "short_name": "ARS"}])

FIXTURES = pd.DataFrame([
    {"gw": 3, "home_id": 1, "away_id": 2,
     "kickoff_time": "2026-09-12T14:00:00Z", "home_goals": None,
     "away_goals": None, "finished": False},
])


def _components():
    rows = []
    for code, element, name, team in ((100, 7, "Incumbent", 300),
                                      (101, 8, "Newcomer", 300),
                                      (102, 9, "Stranger", 301)):
        row = {c: 0.0 for c in COMPONENT_COLS}
        row.update({"code": code, "element": element, "name": name,
                    "position": "MID" if team == 300 else "DEF",
                    "team_code": team, "team_name": "T", "gw": 3,
                    "opp_code": 999, "opp_name": "O", "was_home": True,
                    "kickoff_time": "2026-09-12T14:00:00Z", "p_play": 0.95,
                    "p60": 0.88, "ep": 4.0})
        rows.append(row)
    return pd.DataFrame(rows)[COMPONENT_COLS]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True, exist_ok=True)
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    TEAMS.to_parquet(tmp_path / "data/live/teams.parquet", index=False)
    FIXTURES.to_parquet(tmp_path / "data/live/fixtures_all.parquet",
                        index=False)
    pool = pool_rows(
        pd.DataFrame([{"code": 100, "position": "MID", "team_code": 300,
                       "cost": 100, "sell": 100},
                      {"code": 101, "position": "MID", "team_code": 300,
                       "cost": 80, "sell": 80},
                      {"code": 102, "position": "DEF", "team_code": 301,
                       "cost": 45, "sell": 45}]),
        PLAYERS, owned_codes=[100],
        ep_by={(100, 3): 6.0, (101, 3): 4.0, (102, 3): 2.0}, gws=[3])
    save_solve_state(SolveState(
        gw=3, gws=[3], deadline="2026-09-11T17:30:00Z",
        generated_at="2026-09-10T09:00:00Z", mode="weekly", bank=0,
        free_transfers=1, owned_codes=[100], lam=0.0,
        league_eo={}, avail_by_gw={3: []},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4,
             "horizon": 1},
        pool=pool))
    save_components(_components(), 3)
    return TestClient(create_app())


def _rows(client):
    return {r["name"]: r for r in client.get("/api/players").json()}


def _write(text: str):
    from pathlib import Path

    Path("data/set_pieces.toml").write_text(text, encoding="utf-8")


def test_with_no_file_every_order_is_fpls_and_nobody_is_badged(client):
    """The rail: this is every machine until somebody writes the file."""
    rows = _rows(client)
    assert rows["Incumbent"]["penalties_order"] == 1
    assert rows["Newcomer"]["penalties_order"] is None
    assert [r["set_piece_manual"] for r in rows.values()] == [[], [], []]


def test_the_served_order_is_the_file_s_and_says_so(client):
    _write('["Liverpool"]\npenalties = [101]\n')
    rows = _rows(client)
    assert rows["Newcomer"]["penalties_order"] == 1
    assert rows["Newcomer"]["set_piece_manual"] == ["penalties"]


def test_the_incumbent_s_served_order_clears(client):
    """The club's queue is what the file lists, so the man it leaves out is
    served as no kind of taker — and *is* badged, because that blank came
    from his file and not from FPL. A blank with no badge would read as
    "FPL has nothing", which is the opposite of what happened."""
    _write('["Liverpool"]\npenalties = [101]\n')
    rows = _rows(client)
    assert rows["Incumbent"]["penalties_order"] is None
    assert rows["Incumbent"]["set_piece_manual"] == ["penalties"]


def test_only_the_kind_the_file_names_moves(client):
    """A penalties table says nothing about free kicks or corners, so the
    incumbent keeps both of FPL's other orders."""
    _write('["Liverpool"]\npenalties = [101]\n')
    rows = _rows(client)
    assert rows["Incumbent"]["free_kicks_order"] == 1
    assert rows["Incumbent"]["corners_order"] == 1


def test_a_row_at_a_club_the_file_never_names_is_untouched(client):
    _write('["Liverpool"]\npenalties = [101]\n')
    stranger = _rows(client)["Stranger"]
    assert stranger["penalties_order"] == 1
    assert stranger["set_piece_manual"] == []


def test_corners_move_the_served_order_and_not_the_points(client):
    """Corners and free kicks reach the screen and stop there: only
    ``penalties`` has an expected-points term (``set_pieces.pen_table``)."""
    before = _rows(client)["Newcomer"]["ep_next"]
    _write('["Liverpool"]\ncorners = [101]\n')
    after = _rows(client)["Newcomer"]
    assert after["corners_order"] == 1
    assert after["set_piece_manual"] == ["corners"]
    assert after["ep_next"] == before


def test_the_explain_panel_serves_the_same_orders_as_the_table(client):
    _write('["Liverpool"]\npenalties = [101]\n')
    body = client.get("/api/players/101/explain").json()
    assert body["set_pieces"]["penalties"] == 1
    assert body["set_pieces_manual"] == ["penalties"]
    incumbent = client.get("/api/players/100/explain").json()
    assert incumbent["set_pieces"]["penalties"] is None
    assert incumbent["set_pieces"]["free_kicks"] == 1


def test_a_malformed_file_serves_fpls_orders(client):
    _write("[[[ not toml")
    rows = _rows(client)
    assert rows["Incumbent"]["penalties_order"] == 1
    assert rows["Incumbent"]["set_piece_manual"] == []


def test_a_snapshot_row_with_no_club_does_not_500_the_endpoint(client):
    """The clubs come off the frame, and a frame value is not an int until it
    is one.

    A snapshot carries every player FPL publishes, not only this week's
    candidates, so a row with a missing `team_code` never reaches the row loop
    — it is filtered out as a non-candidate first. It did reach
    `set_piece_orders`, which called `int()` on it, and one such row would have
    taken the whole explorer down over a display fact.
    """
    stray = PLAYERS.iloc[[2]].copy()
    stray["code"] = 103
    stray["element"] = 10
    stray["name"] = "Clubless"
    stray["team_code"] = float("nan")
    pd.concat([PLAYERS, stray], ignore_index=True).to_parquet(
        "data/live/players.parquet", index=False)
    _write('["Liverpool"]\npenalties = [101]\n')
    resp = client.get("/api/players")
    assert resp.status_code == 200
    rows = {r["name"]: r for r in resp.json()}
    assert "Clubless" not in rows            # not a candidate this week
    assert rows["Newcomer"]["penalties_order"] == 1
    assert rows["Incumbent"]["penalties_order"] is None
