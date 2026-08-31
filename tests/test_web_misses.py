"""``/api/misses``: a 200 for every state, including having nothing to say.

The card's contract is spec D1's — absent inputs mean an absent card, never a
card of zeros — and the only way the frontend can tell the difference is a
null gameweek. So that is what is asserted here.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import save_components
from gaffer.web.app import create_app

COMPONENTS = pd.DataFrame([
    {"code": 11, "element": 11, "name": "Saka", "position": "MID",
     "team_code": 3, "team_name": "Arsenal", "gw": 5, "opp_code": 4,
     "opp_name": "City", "was_home": 1.0, "kickoff_time": None,
     "p_play": 0.9, "p60": 0.8, "ep": 5.5}])

RESULTS = pd.DataFrame([{"code": 11, "gw": 5, "total_points": 16,
                         "minutes": 90}])

PLAYERS = pd.DataFrame({"code": [11], "element": [11], "name": ["Saka"],
                        "position": ["MID"], "now_cost": [100]})


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    return TestClient(create_app())


def test_a_clone_with_nothing_banked_is_an_empty_card(client):
    body = client.get("/api/misses").json()
    assert body == {"gw": None, "rows": []}


def test_results_without_a_forecast_are_still_an_empty_card(client, tmp_path):
    RESULTS.to_parquet(tmp_path / "data/live/player_gw.parquet", index=False)
    assert client.get("/api/misses").json()["gw"] is None


def test_a_scored_week_comes_back_named(client, tmp_path):
    RESULTS.to_parquet(tmp_path / "data/live/player_gw.parquet", index=False)
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    save_components(COMPONENTS, 5)
    body = client.get("/api/misses").json()
    assert body["gw"] == 5
    assert body["rows"][0]["name"] == "Saka"
    assert body["rows"][0]["miss"] == pytest.approx(10.5)


def test_an_explicit_gameweek_is_honoured(client, tmp_path):
    RESULTS.to_parquet(tmp_path / "data/live/player_gw.parquet", index=False)
    save_components(COMPONENTS, 5)
    assert client.get("/api/misses?gw=6").json() == {"gw": None, "rows": []}
