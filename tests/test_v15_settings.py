"""v15 §4.2 — the focus league and the stance rows, and the choice kind."""

import tomllib

import pytest
from fastapi.testclient import TestClient

from gaffer.config import LOCAL_OVERLAY, serving_config
from gaffer.web.app import create_app
from gaffer.web.settings_keys import BY_FIELD, WHITELIST

BASE = "[fpl]\nentry_id = 1\nleague_id = 5\n"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(BASE)
    serving_config.cache_clear()
    yield TestClient(create_app())
    serving_config.cache_clear()


def _row(client, key):
    return next(r for r in client.get("/api/settings").json()["rows"]
                if r["key"] == key)


def _overlay(tmp_path):
    path = tmp_path / LOCAL_OVERLAY
    return tomllib.loads(path.read_text()) if path.exists() else {}


def test_the_focus_row_reads_the_effective_league_id(client):
    row = _row(client, "league_id")
    assert row["label"] == "Focus league"
    assert row["kind"] == "int" and row["value"] == 5
    assert row["section"] == "league" and row["source"] == "base"


def test_the_stance_row_is_a_choice_with_four_options(client):
    row = _row(client, "stance")
    assert row["kind"] == "choice"
    assert row["choices"] == ["auto", "chase", "defend", "neutral"]
    assert row["value"] == "auto" and row["source"] == "default"


def test_every_other_row_has_no_choices(client):
    for row in client.get("/api/settings").json()["rows"]:
        if row["kind"] != "choice":
            assert row["choices"] == []


def test_a_focus_write_lands_in_league_focus_and_not_in_config_toml(
        client, tmp_path):
    body = client.post("/api/settings",
                       json={"key": "league_id", "value": 77}).json()
    assert _overlay(tmp_path) == {"league": {"focus": 77}}
    assert "focus" not in (tmp_path / "config.toml").read_text()
    row = next(r for r in body["rows"] if r["key"] == "league_id")
    assert row["value"] == 77 and row["source"] == "local"


def test_resetting_the_focus_falls_back_to_fpl_league_id(client, tmp_path):
    client.post("/api/settings", json={"key": "league_id", "value": 77})
    body = client.post("/api/settings",
                       json={"key": "league_id", "value": None}).json()
    assert _overlay(tmp_path) == {}
    row = next(r for r in body["rows"] if r["key"] == "league_id")
    assert row["value"] == 5 and row["source"] == "base"


def test_a_stance_write_is_the_word_itself(client, tmp_path):
    body = client.post("/api/settings",
                       json={"key": "stance", "value": "defend"}).json()
    assert _overlay(tmp_path) == {"league": {"stance": "defend"}}
    row = next(r for r in body["rows"] if r["key"] == "stance")
    assert row["value"] == "defend" and row["source"] == "local"


@pytest.mark.parametrize("value", ["attack", "", 7, True])
def test_a_stance_outside_the_four_is_refused_and_writes_nothing(
        client, tmp_path, value):
    resp = client.post("/api/settings", json={"key": "stance", "value": value})
    assert resp.status_code == 422
    assert resp.json()["detail"]["constraint"] == "wrong_type"
    assert "one of" in resp.json()["detail"]["error"]
    assert _overlay(tmp_path) == {}


def test_a_focus_below_one_is_refused(client, tmp_path):
    resp = client.post("/api/settings", json={"key": "league_id", "value": 0})
    assert resp.status_code == 422
    assert _overlay(tmp_path) == {}


def test_the_whitelist_declares_the_two_rows_in_the_league_table():
    assert BY_FIELD["league_id"].section == "league"
    assert BY_FIELD["league_id"].toml_key == "focus"
    assert BY_FIELD["stance"].toml_key == "stance"
    assert BY_FIELD["stance"].choices == ("auto", "chase", "defend", "neutral")
    assert all(e.choices == () for e in WHITELIST if e.kind != "choice")
