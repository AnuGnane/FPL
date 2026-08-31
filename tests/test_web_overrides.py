"""``/api/overrides``: the only endpoint in the tool that writes a number the
model then has to obey.

So it is the only endpoint that has to refuse things. A code nobody has heard
of, a probability of 1.5, a pin that pins nothing: all 422 with a structured
detail the form can render inline, exactly as the what-if lab's constraint
errors do.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.config import serving_config
from gaffer.web.app import create_app

PLAYERS = pd.DataFrame({
    "code": [11, 22], "element": [1, 2], "name": ["Saka", "Haaland"],
    "position": ["MID", "FWD"], "team_id": [1, 2], "team_code": [3, 4],
    "now_cost": [100, 150], "status": ["d", "a"], "news": ["knock", ""],
    "chance_of_playing": [25.0, None], "selected_by_percent": [40.0, 60.0],
    "form": [5.0, 8.0], "points_per_game": [5.0, 7.0],
    "ep_next": [5.5, 8.5], "price_change_percent": [0.0, 0.0],
    "price_change_calibrating": [False, False],
    "penalties_order": [None, 1.0], "direct_freekicks_order": [None, None],
    "corners_and_indirect_freekicks_order": [None, None]})

COMPONENTS = pd.DataFrame([
    {"code": 11, "gw": 5, "p_play": 0.82, "p60": 0.7, "ep": 5.5},
    {"code": 22, "gw": 5, "p_play": 0.99, "p60": 0.95, "ep": 8.5}])

SHADOW = pd.DataFrame([
    {"season": "2026-27", "gw": 5, "code": 11, "p_play_news": 0.82,
     "p_play_flags": 0.9, "e_min_news": 61.0, "e_min_flags": 70.0,
     "run_at": "2026-08-31T10:00:00+00:00"}])


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 5\n\n[news]\noverrides = true\n')
    serving_config.cache_clear()
    (tmp_path / "data" / "live").mkdir(parents=True)
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    SHADOW.to_parquet(tmp_path / "data/live/news_shadow.parquet", index=False)
    (tmp_path / "reports").mkdir()
    COMPONENTS.to_parquet(tmp_path / "reports/components_gw5.parquet",
                          index=False)
    (tmp_path / "reports/solve_state_gw5.json").write_text("{}")
    yield TestClient(create_app())
    serving_config.cache_clear()


def test_no_pins_is_an_empty_active_panel(client):
    body = client.get("/api/overrides").json()
    assert body == {"active": True, "rows": []}


def test_a_pin_comes_back_named_and_dated(client):
    posted = client.post("/api/overrides",
                         json={"code": 11, "p_play": 1.0, "note": "trained"})
    assert posted.status_code == 200
    row = posted.json()["rows"][0]
    assert row["code"] == 11 and row["name"] == "Saka"
    assert row["p_play"] == 1.0 and row["e_min"] is None
    assert row["note"] == "trained"
    assert row["set_at"].startswith("20")
    # A3: what the served pipeline had for him at the moment of the pin.
    assert row["model_p_play"] == 0.82
    assert row["model_e_min"] == 61.0
    assert client.get("/api/overrides").json()["rows"] == posted.json()["rows"]


def test_an_unknown_code_is_a_structured_422(client):
    response = client.post("/api/overrides", json={"code": 999,
                                                   "p_play": 1.0})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["constraint"] == "unknown_player"
    assert detail["players"] == [999]
    assert "999" in detail["error"]


@pytest.mark.parametrize("payload", [
    {"code": 11, "p_play": 1.5},
    {"code": 11, "e_min": 120.0},
    {"code": 11},
    {"code": 11, "p_play": 1.0, "note": "x" * 500},
])
def test_a_value_the_model_cannot_act_on_is_a_structured_422(client,
                                                             payload):
    response = client.post("/api/overrides", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"]["constraint"] == "override_value"


def test_deleting_a_pin_returns_the_panel_without_it(client):
    client.post("/api/overrides", json={"code": 11, "p_play": 1.0})
    client.post("/api/overrides", json={"code": 22, "e_min": 90.0})
    body = client.delete("/api/overrides/11").json()
    assert [r["code"] for r in body["rows"]] == [22]


def test_deleting_a_pin_that_is_not_there_is_a_404(client):
    assert client.delete("/api/overrides/11").status_code == 404


def test_the_panel_says_when_the_flag_is_off(client, tmp_path):
    """A pin that is saved but not being applied is worth a sentence, not a
    silent nothing."""
    client.post("/api/overrides", json={"code": 11, "p_play": 1.0})
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 5\n\n[news]\noverrides = false\n')
    serving_config.cache_clear()
    body = client.get("/api/overrides").json()
    assert body["active"] is False
    assert len(body["rows"]) == 1


def test_a_missing_player_snapshot_does_not_stop_a_read(client, tmp_path):
    """The panel is a read path on a page that already works."""
    client.post("/api/overrides", json={"code": 11, "p_play": 1.0})
    (tmp_path / "data/live/players.parquet").unlink()
    body = client.get("/api/overrides").json()
    assert body["rows"][0]["name"] == "11"


def test_a_missing_player_snapshot_refuses_a_write(client, tmp_path):
    """With no code list there is nothing to validate against, and an
    unvalidated pin is the one thing this endpoint must not write."""
    (tmp_path / "data/live/players.parquet").unlink()
    response = client.post("/api/overrides", json={"code": 11, "p_play": 1.0})
    assert response.status_code == 422
