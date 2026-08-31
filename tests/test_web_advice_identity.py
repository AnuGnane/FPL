"""``/api/advice/latest`` serves the enrichment, and survives without it."""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.data import store
from gaffer.web.app import create_app

GW = 5

PLAYERS = pd.DataFrame({
    "code": [11, 22], "name": ["Saka", "Haaland"],
    "position": ["MID", "FWD"], "team_id": [1, 13], "team_code": [3, 43],
    "now_cost": [101, 150], "selected_by_percent": [40.0, 60.0],
})
TEAMS = pd.DataFrame({"team_id": [1, 13, 14], "code": [3, 43, 1],
                      "name": ["Arsenal", "Man City", "Man Utd"],
                      "short_name": ["ARS", "MCI", "MUN"]})
FIXTURES = pd.DataFrame({
    "gw": [5], "home_id": [1], "away_id": [14],
    "kickoff_time": ["2026-09-12T14:00:00Z"],
    "home_goals": [None], "away_goals": [None], "finished": [False]})

# ``staleness_for`` reads the event table on every request, so the route needs
# one on disk before it can answer at all — the same two-row table the rest of
# the advice suite writes (``test_web_advice._write_artifacts``).
EVENTS = pd.DataFrame([
    {"gw": GW, "deadline_time": "2026-09-11T17:30:00Z", "is_current": False,
     "is_next": True, "finished": False, "data_checked": False},
    {"gw": GW + 1, "deadline_time": "2099-09-18T17:30:00Z",
     "is_current": False, "is_next": False, "finished": False,
     "data_checked": False}])

ADVICE = {
    "gw": GW, "hits": 0, "expected_pts": 54.3,
    "xi": [{"code": 11, "name": "Saka", "position": "MID", "ep": 5.1}],
    "bench": [{"code": 22, "name": "Haaland", "position": "FWD", "ep": 6.2}],
    "buys": [], "sells": [],
    "captain": {"code": 11, "name": "Saka", "position": "MID", "ep": 5.1},
    "vice": {"code": 22, "name": "Haaland", "position": "FWD", "ep": 6.2},
    "chip_table": [], "strategy": None,
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A clone with one solved gameweek, wired the way the advice tests wire
    it: a real artifact on disk and a real solve state beside it."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    (tmp_path / "data" / "live").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    TEAMS.to_parquet(tmp_path / "data/live/teams.parquet", index=False)
    FIXTURES.to_parquet(tmp_path / "data/live/fixtures_all.parquet",
                        index=False)
    EVENTS.to_parquet(tmp_path / "data/live/events.parquet", index=False)
    (tmp_path / "reports" / f"gw{GW}-advice.json").write_text(
        json.dumps(ADVICE))
    _write_solve_state(tmp_path)
    return tmp_path, TestClient(create_app())


def _write_solve_state(tmp_path):
    """Reuse the project's own helper so this test cannot drift from the
    shape ``load_solve_state`` expects."""
    from gaffer.artifacts import SolveState, save_solve_state

    save_solve_state(SolveState(
        gw=GW, gws=[GW], deadline="2026-09-11T17:30:00Z",
        generated_at="2026-09-10T20:00:00+00:00", mode="weekly", bank=0.5,
        free_transfers=1, owned_codes=[11, 22], lam=0.0, league_eo={},
        cover={}, avail_by_gw={}, opt={},
        pool=pd.DataFrame({"code": [11, 22], "position": ["MID", "FWD"]})))


def test_the_payload_carries_identity_and_the_weeks_fixture(client):
    _tmp, api = client
    advice = api.get("/api/advice/latest").json()["advice"]
    assert advice["xi"][0]["team_short"] == "ARS"
    assert advice["xi"][0]["team_code"] == 3
    assert advice["xi"][0]["next_fixture"]["opponent_short"] == "MUN"
    assert advice["xi"][0]["next_fixture"]["home"] is True


def test_a_blank_gameweek_player_carries_a_null_fixture(client):
    _tmp, api = client
    advice = api.get("/api/advice/latest").json()["advice"]
    assert advice["bench"][0]["team_short"] == "MCI"
    assert advice["bench"][0]["next_fixture"] is None


def test_positions_are_still_backfilled_alongside(client):
    """The two serve-time decorations compose; neither undoes the other."""
    _tmp, api = client
    advice = api.get("/api/advice/latest").json()["advice"]
    assert advice["xi"][0]["position"] == "MID"


def test_the_route_is_a_200_with_no_fixture_file_at_all(client):
    tmp_path, api = client
    (tmp_path / "data/live/fixtures_all.parquet").unlink()
    advice = api.get("/api/advice/latest").json()["advice"]
    assert advice["xi"][0]["next_fixture"] is None
    assert advice["xi"][0]["team_short"] == "ARS"


def test_the_artifact_on_disk_is_untouched(client):
    """A2: the enrichment is a decoration on the way out, and the file the
    next ``advise`` run diffs against must be byte-identical."""
    tmp_path, api = client
    before = (tmp_path / "reports" / f"gw{GW}-advice.json").read_bytes()
    api.get("/api/advice/latest")
    assert (tmp_path / "reports" / f"gw{GW}-advice.json").read_bytes() \
        == before
