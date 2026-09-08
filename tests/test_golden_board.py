"""v17c — the golden board harness (specs/2026-09-07-v17c-golden-board-design.md).

Unit tests over a synthetic bundle, and the two ``golden``-marked tests that
run the real pipeline over the recorded one."""
from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path

import httpx
import pytest

from gaffer.config import Config, load_config
from tests import golden_client as gc


def _bundle(tmp_path: Path) -> Path:
    gc.save_bundle(tmp_path, {"bootstrap-static/": {"events": [{"id": 4}]},
                              "fixtures/": [{"id": 1}]})
    return tmp_path


def test_the_recorded_client_serves_every_recorded_path_and_refuses_the_rest(tmp_path):
    client = gc.RecordedClient(_bundle(tmp_path))
    assert client.get_bootstrap() == {"events": [{"id": 4}]}
    assert client.get_fixtures() == [{"id": 1}]
    with pytest.raises(KeyError, match="element-summary/7/"):
        client.get_element_summary(7)


def test_the_recorded_client_hands_out_copies_not_the_bundle(tmp_path):
    client = gc.RecordedClient(_bundle(tmp_path))
    client.get_bootstrap()["events"].append({"id": 99})
    assert client.get_bootstrap() == {"events": [{"id": 4}]}


def test_the_recorded_client_never_writes_a_raw_snapshot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    gc.RecordedClient(_bundle(tmp_path / "golden")).get_bootstrap()
    assert not (tmp_path / "data").exists()


def test_the_recording_client_banks_every_body_under_its_path(tmp_path):
    seen: list[str] = []

    class Fake(gc.RecordingClient):
        def _live(self, path):
            seen.append(path)
            return {"path": path}

    # raw_dir into tmp_path: the parent ``__init__`` makes the directory it is
    # given, and a test must not leave one in the repo's ``data/`` (v17c §2.1).
    rec = Fake(tmp_path / "out", raw_dir=tmp_path / "raw")
    rec.get_bootstrap()
    rec.get_entry_picks(2210493, 3)
    out = rec.save()
    assert out == tmp_path / "out" / gc.BUNDLE_NAME
    assert gc.load_bundle(tmp_path / "out") == {
        "bootstrap-static/": {"path": "bootstrap-static/"},
        "entry/2210493/event/3/picks/": {"path": "entry/2210493/event/3/picks/"}}
    assert seen == ["bootstrap-static/", "entry/2210493/event/3/picks/"]


def test_golden_config_round_trips_through_the_toml_writer(tmp_path):
    cfg = gc.golden_config()
    gc.write_golden_toml(cfg, tmp_path / "config.toml")
    assert asdict(load_config(tmp_path / "config.toml")) == asdict(cfg)


def test_golden_config_is_a_literal_with_the_levers_the_spec_names():
    cfg = gc.golden_config()
    assert isinstance(cfg, Config)
    assert cfg.horizon == 6
    assert cfg.scenarios_n == 40 and cfg.scenarios_seed == 20260825
    assert cfg.news_enabled is False
    assert cfg.odds_api_key == ""
    assert cfg.train_seasons == ["2022-23", "2023-24", "2024-25", "2025-26"]
    assert cfg.current_season == "2026-27"


def test_the_written_toml_has_no_odds_section_and_no_key(tmp_path):
    gc.write_golden_toml(gc.golden_config(), tmp_path / "config.toml")
    text = (tmp_path / "config.toml").read_text()
    assert "[odds]" not in text
    assert "api_key" not in text


def test_save_bundle_writes_the_same_bytes_for_the_same_answers(tmp_path):
    """v17c §2.2: sorted keys, zero mtime, no filename — the three things
    that make a re-record with the same answers the same bytes."""
    a = gc.save_bundle(tmp_path / "a", {"x/": 1, "y/": [2.5]})
    time.sleep(1.1)
    b = gc.save_bundle(tmp_path / "b", {"y/": [2.5], "x/": 1})
    assert a.read_bytes() == b.read_bytes()


def test_the_recording_client_fetches_through_the_parent_without_a_raw_dump(tmp_path):
    """The real ``_live`` path (v17c §2.1): the parent's transport answers,
    the body is banked, and ``snapshot=None`` keeps ``data/raw`` empty."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"events": [{"id": 4}]})

    rec = gc.RecordingClient(tmp_path / "out", raw_dir=tmp_path / "raw",
                             transport=httpx.MockTransport(handler))
    assert rec.get_bootstrap() == {"events": [{"id": 4}]}
    rec.save()
    assert gc.load_bundle(tmp_path / "out") == {"bootstrap-static/": {"events": [{"id": 4}]}}
    assert list((tmp_path / "raw").iterdir()) == []
