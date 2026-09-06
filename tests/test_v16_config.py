"""v16 §3.2 — the hit bar: a Config field, bounded, and a Settings row."""
from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

from gaffer.config import (HIT_BAR_HI, HIT_BAR_LO, LOCAL_OVERLAY, Config,
                           load_config, optimizer_top_n, serving_config)
from gaffer.errors import GafferError

BASE = "[fpl]\nentry_id = 1\nleague_id = 5\n"


def _load(tmp_path, monkeypatch, base: str = BASE, local: str | None = None):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(base)
    if local is not None:
        (tmp_path / LOCAL_OVERLAY).write_text(local)
    return load_config()


def test_hit_bar_is_a_field_defaulting_to_sixty_percent():
    assert "hit_bar" in {f.name for f in dataclasses.fields(Config)}
    assert Config(entry_id=1, league_id=5).hit_bar == 0.60


def test_the_bounds_are_a_coin_toss_and_never():
    assert (HIT_BAR_LO, HIT_BAR_HI) == (0.5, 0.95)


def test_hit_bar_is_read_from_the_optimizer_table(tmp_path, monkeypatch):
    cfg = _load(tmp_path, monkeypatch, base=BASE + "[optimizer]\nhit_bar = 0.7\n")
    assert cfg.hit_bar == 0.7


def test_the_overlay_wins(tmp_path, monkeypatch):
    cfg = _load(tmp_path, monkeypatch, base=BASE + "[optimizer]\nhit_bar = 0.7\n",
                local="[optimizer]\nhit_bar = 0.55\n")
    assert cfg.hit_bar == 0.55


@pytest.mark.parametrize("line", ["hit_bar = 0.4", "hit_bar = 0.96",
                                  "hit_bar = true", 'hit_bar = "high"'])
def test_a_bar_outside_the_bounds_is_refused_by_name(tmp_path, monkeypatch, line):
    with pytest.raises(GafferError, match=r"\[optimizer\] hit_bar"):
        _load(tmp_path, monkeypatch, base=BASE + f"[optimizer]\n{line}\n")


@pytest.fixture()
def settings_client(tmp_path, monkeypatch):
    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(BASE)
    serving_config.cache_clear()
    optimizer_top_n.cache_clear()
    yield TestClient(create_app())
    serving_config.cache_clear()
    optimizer_top_n.cache_clear()


def test_the_settings_panel_serves_the_bar_with_its_range(settings_client):
    rows = {r["key"]: r for r in settings_client.get("/api/settings").json()["rows"]}
    row = rows["hit_bar"]
    assert row["value"] == 0.60 and row["kind"] == "float"
    assert (row["lo"], row["hi"]) == (0.5, 0.95)
    assert row["section"] == "optimizer" and row["source"] == "default"


def test_a_saved_bar_reaches_load_config(settings_client, tmp_path):
    resp = settings_client.post("/api/settings", json={"key": "hit_bar", "value": 0.7})
    assert resp.status_code == 200, resp.text
    assert load_config(tmp_path / "config.toml").hit_bar == 0.7


def test_a_bar_above_the_ceiling_is_refused_at_the_endpoint(settings_client):
    resp = settings_client.post("/api/settings", json={"key": "hit_bar", "value": 0.99})
    assert resp.status_code == 422
    assert resp.json()["detail"]["constraint"] == "out_of_range"
