"""v17c — the golden board harness (specs/2026-09-07-v17c-golden-board-design.md).

Unit tests over a synthetic bundle, and the two ``golden``-marked tests that
run the real pipeline over the recorded one."""
from __future__ import annotations

import hashlib
from dataclasses import asdict
from pathlib import Path

import httpx
import pytest

from gaffer.config import NO_CAP, load_config, price_timing
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
    assert cfg.horizon == 6
    assert (cfg.max_hits, cfg.max_transfers, cfg.hit_bar) == (2, NO_CAP, 0.60)
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


def test_the_written_toml_carries_the_price_timing_flag_the_solve_path_reads(tmp_path):
    """v17c §2.3: ``price_timing`` is no Config field, so the round trip
    cannot see it — but ``price_timing()`` opens the cwd's config.toml on the
    solve path, and an unwritten flag would let a default flip move the
    golden."""
    gc.write_golden_toml(gc.golden_config(), tmp_path / "config.toml")
    assert "price_timing = true" in (tmp_path / "config.toml").read_text()
    assert price_timing(tmp_path / "config.toml") is True


def test_save_bundle_writes_the_same_bytes_for_the_same_answers(tmp_path):
    """v17c §2.2: sorted keys, zero mtime, no filename — the three things
    that make a re-record with the same answers the same bytes. The two
    header fields are read off the gzip member directly rather than waited
    out, so the test costs nothing and names the field that broke."""
    a = gc.save_bundle(tmp_path / "a", {"x/": 1, "y/": [2.5]}).read_bytes()
    b = gc.save_bundle(tmp_path / "b", {"y/": [2.5], "x/": 1}).read_bytes()
    assert a == b
    assert a[3] & 0x08 == 0, "FNAME set: the path is in the header"
    assert a[4:8] == b"\x00\x00\x00\x00", "mtime is not zero"


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


def _fake_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "models").mkdir(parents=True)
    (repo / "models" / "team.joblib").write_bytes(b"model")
    (repo / "data" / "history").mkdir(parents=True)
    (repo / "data" / "history" / "player_gw.parquet").write_bytes(b"rows")
    (repo / "data" / "core_insights" / "2026-27").mkdir(parents=True)
    (repo / "data" / "core_insights" / "2026-27" / "stats.parquet").write_bytes(b"ci")
    (repo / "data" / "manager_tenures.toml").write_text("[x]\n")
    return repo


def test_input_hashes_cover_models_and_history_and_name_absent_optionals(tmp_path):
    repo = _fake_repo(tmp_path)
    hashes = gc.input_hashes(repo)
    assert hashes["models/team.joblib"] == hashlib.sha256(b"model").hexdigest()
    assert hashes["data/history/player_gw.parquet"] == hashlib.sha256(b"rows").hexdigest()
    assert hashes["data/chip_scenarios.toml"] == "absent"
    assert hashes["data/set_pieces.toml"] == "absent"
    assert not any(k.startswith("data/core_insights") for k in hashes)


def test_matching_hashes_do_not_skip(tmp_path):
    repo = _fake_repo(tmp_path)
    header = {"inputs": gc.input_hashes(repo)}
    assert gc.stale_inputs(header, repo) == []


def test_a_changed_model_hash_skips_with_the_file_named(tmp_path):
    repo = _fake_repo(tmp_path)
    header = {"inputs": gc.input_hashes(repo)}
    (repo / "models" / "team.joblib").write_bytes(b"retrained")
    assert gc.stale_inputs(header, repo) == ["models/team.joblib"]
    (repo / "models" / "team.joblib").unlink()
    assert gc.stale_inputs(header, repo) == ["models/team.joblib"]


def test_an_optional_input_that_appears_is_a_drift(tmp_path):
    repo = _fake_repo(tmp_path)
    header = {"inputs": gc.input_hashes(repo)}
    (repo / "data" / "set_pieces.toml").write_text("[pens]\n")
    assert gc.stale_inputs(header, repo) == ["data/set_pieces.toml"]


def test_build_scratch_tree_links_the_heavy_inputs_and_copies_the_frozen_ones(tmp_path):
    repo = _fake_repo(tmp_path)
    golden = tmp_path / "golden"
    (golden / "data" / "core_insights" / "2026-27").mkdir(parents=True)
    (golden / "data" / "core_insights" / "2026-27" / "stats.parquet").write_bytes(b"frozen")
    gc.write_golden_toml(gc.golden_config(), golden / "config.toml")
    root = tmp_path / "scratch"
    gc.build_scratch_tree(root, repo, golden)
    assert (root / "models").is_symlink() and (root / "models" / "team.joblib").read_bytes() == b"model"
    assert (root / "data" / "history").is_symlink()
    assert not (root / "data" / "core_insights").is_symlink()
    assert (root / "data" / "core_insights" / "2026-27" / "stats.parquet").read_bytes() == b"frozen"
    assert (root / "data" / "manager_tenures.toml").read_text() == "[x]\n"
    assert (root / "config.toml").read_text() == (golden / "config.toml").read_text()
    assert (root / "reports").is_dir()
    assert not (root / "data" / "live").exists()


def test_strip_volatile_removes_generated_at_and_rewrites_paths():
    obj = {"generated_at": "2026-09-08T09:17:00", "gw": 4,
           "nested": [{"generated_at": 1, "path": "/tmp/x/reports/a.json"}],
           "other": "/tmp/y/z"}
    assert gc.strip_volatile(obj, "/tmp/x") == {
        "gw": 4, "nested": [{"path": "<cwd>/reports/a.json"}], "other": "/tmp/y/z"}


def test_lever_counts_read_the_served_advice():
    advice = {
        "restraint": {"steps": [{"taken": True}, {"taken": False}, {"taken": False}]},
        "objective": {"hits": 1}, "chip_table": [{}, {}],
        "strategy": {"lam": 0.0958}, "bench": [1, 2, 3, 4], "vice": {"code": 9},
        "plan_by_gw": [{}] * 6}
    counts = gc.lever_counts(advice)
    assert counts == {"restraint_steps_taken": 1, "restraint_steps_refused": 2,
                      "objective_hits": 1, "chip_rows": 2, "league_lam": 0.0958,
                      "bench": 4, "vice": True, "plan_weeks": 6}
    assert gc.levers_below_floor(counts) == []
    assert gc.levers_below_floor({**counts, "league_lam": 0.0, "plan_weeks": 3}) == [
        "league_lam", "plan_weeks"]


def test_lever_counts_survive_a_missing_block():
    counts = gc.lever_counts({"restraint": None, "objective": None, "strategy": None,
                              "chip_table": [], "bench": [], "vice": None,
                              "plan_by_gw": []})
    assert counts["restraint_steps_taken"] == 0 and counts["league_lam"] == 0.0
    assert set(gc.levers_below_floor(counts)) == set(gc.LEVER_FLOORS)


def test_the_fixture_is_under_the_size_budget():
    if not (gc.GOLDEN_DIR / gc.HEADER_NAME).exists():
        pytest.skip("golden board not recorded yet")
    assert gc.fixture_kb(gc.GOLDEN_DIR) < 5120
