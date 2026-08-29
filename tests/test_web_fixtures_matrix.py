"""GET /api/fixtures/matrix — Dixon-Coles difficulty per team x gameweek.

Two scores per cell, not one: an opponent that concedes freely is an easy
fixture for your forwards and a hard one for your defenders' clean sheet, and
a single number cannot say both (spec §6.3).
"""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.data import store
from gaffer.models import persistence
from gaffer.web.app import create_app


class FakeDixonColes:
    """Only the two attributes the endpoint reads."""

    def __init__(self):
        self.attack_ = {300: 0.40, 301: 0.00, 302: -0.40}
        self.defence_ = {300: -0.30, 301: 0.00, 302: 0.30}
        self.fallback_attack_ = -0.50
        self.fallback_defence_ = 0.50


TEAMS = pd.DataFrame([
    {"team_id": 1, "code": 300, "name": "Liverpool", "short_name": "LIV"},
    {"team_id": 2, "code": 301, "name": "Arsenal", "short_name": "ARS"},
    {"team_id": 3, "code": 302, "name": "Everton", "short_name": "EVE"},
])

FIXTURES = pd.DataFrame([
    {"gw": 5, "home_id": 1, "away_id": 3, "finished": False},
    {"gw": 5, "home_id": 2, "away_id": 1, "finished": True},
    {"gw": 6, "home_id": 3, "away_id": 2, "finished": False},
    {"gw": 6, "home_id": 1, "away_id": 2, "finished": False},
])


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    store.save(TEAMS, "live/teams.parquet")
    store.save(FIXTURES, "live/fixtures_all.parquet")
    monkeypatch.setattr(persistence, "model_exists", lambda name: name == "team")
    monkeypatch.setattr(persistence, "load_model", lambda name: FakeDixonColes())
    return TestClient(create_app(), raise_server_exceptions=False)


def test_one_row_per_team_and_a_cell_per_requested_gameweek(client):
    body = client.get("/api/fixtures/matrix?from=5&n=2").json()
    assert body["gws"] == [5, 6]
    assert {t["code"] for t in body["teams"]} == {300, 301, 302}
    assert body["source"] == "dixon_coles"


def test_cells_name_the_opponent_and_the_venue(client):
    body = client.get("/api/fixtures/matrix?from=5&n=2").json()
    liverpool = next(t for t in body["teams"] if t["code"] == 300)
    gw5 = next(c for c in liverpool["cells"] if c["gw"] == 5)
    assert gw5["opponent"] == "EVE" and gw5["home"] is True


def test_the_hardest_attacking_fixture_is_the_strongest_defence(client):
    body = client.get("/api/fixtures/matrix?from=5&n=2").json()
    everton = next(t for t in body["teams"] if t["code"] == 302)
    gw5 = next(c for c in everton["cells"] if c["gw"] == 5)     # away at LIV
    arsenal = next(t for t in body["teams"] if t["code"] == 301)
    gw6 = next(c for c in arsenal["cells"] if c["gw"] == 6)     # away at EVE
    # Liverpool has the meanest defence of the three and Everton the leakiest.
    assert gw5["attack"] == 1.0
    assert gw6["attack"] == 0.0
    assert 0.0 <= gw5["defence"] <= 1.0


def test_the_hardest_clean_sheet_is_against_the_strongest_attack(client):
    body = client.get("/api/fixtures/matrix?from=5&n=2").json()
    everton = next(t for t in body["teams"] if t["code"] == 302)
    gw5 = next(c for c in everton["cells"] if c["gw"] == 5)     # away at LIV
    assert gw5["defence"] == 1.0


def test_finished_fixtures_are_not_in_the_matrix(client):
    body = client.get("/api/fixtures/matrix?from=5&n=2").json()
    arsenal = next(t for t in body["teams"] if t["code"] == 301)
    assert all(c["gw"] != 5 for c in arsenal["cells"])


def test_a_missing_team_model_is_an_empty_matrix_not_an_error(client,
                                                              monkeypatch):
    monkeypatch.setattr(persistence, "model_exists", lambda name: False)
    resp = client.get("/api/fixtures/matrix?from=5&n=2")
    assert resp.status_code == 200
    assert resp.json() == {"gws": [], "teams": [], "source": "none"}


def test_a_head_without_attack_parameters_degrades_to_empty(client,
                                                            monkeypatch):
    class PlainTeamModel:
        pass

    monkeypatch.setattr(persistence, "load_model", lambda name: PlainTeamModel())
    body = client.get("/api/fixtures/matrix?from=5&n=2").json()
    assert body == {"gws": [], "teams": [], "source": "none"}


def test_a_cold_clone_is_an_empty_matrix_not_a_500(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    client = TestClient(create_app(), raise_server_exceptions=False)
    resp = client.get("/api/fixtures/matrix")
    assert resp.status_code == 200
    assert resp.json() == {"gws": [], "teams": [], "source": "none"}
