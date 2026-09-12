"""v17c — the golden board harness (specs/2026-09-07-v17c-golden-board-design.md).

Unit tests over a synthetic bundle, and the ``golden``-marked tests that run
the real pipeline over the recorded one."""
from __future__ import annotations

import functools
import hashlib
import io
import json
from dataclasses import asdict
from pathlib import Path

import httpx
import pandas as pd
import pytest

from gaffer.config import NO_CAP, load_config
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
    """v17c §2.3 wrote the flag by hand because it was no Config field; since
    v17e §2.1 it is one and the round trip covers it. The line is still
    asserted here, and last in ``[optimizer]``, because the recorded
    ``config.toml`` is byte-pinned and a layout that moved it would rewrite
    the fixture."""
    gc.write_golden_toml(gc.golden_config(), tmp_path / "config.toml")
    text = (tmp_path / "config.toml").read_text()
    assert "price_timing = true" in text
    assert load_config(tmp_path / "config.toml").price_timing is True


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


def test_a_stale_board_skips_naming_the_file_and_the_command(tmp_path):
    """v18a Task 2: the one shared skip helper must be loud — the sentence
    names the first differing input, how many differ, and the exact
    re-record command, so a stale board is actionable from the pytest
    output alone rather than from reading ``golden_client.py``.

    The tree is the same minimal fake repo ``input_hashes``' own tests use
    (``_fake_repo``): a ``models/`` file and a ``data/history`` file are all
    ``stale_inputs`` reads, so nothing heavier — no real ``models/`` copy,
    no symlink to the real ``data/history`` — is needed to make it compute
    honestly."""
    repo = _fake_repo(tmp_path)
    golden = tmp_path / "golden"
    golden.mkdir()
    header = {"inputs": gc.input_hashes(repo)}
    (golden / gc.HEADER_NAME).write_text(json.dumps(header))

    (repo / "models" / "team.joblib").write_bytes(b"retrained")

    with pytest.raises(pytest.skip.Exception) as exc:
        gc.golden_header_or_skip(repo, golden)
    message = str(exc.value)
    assert "models/team.joblib" in message
    assert "1 input(s) differ" in message
    assert "python -m tests.golden_client --write" in message


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
           "other": "/tmp/y/z",
           # v17c §1 item 1: the rewrite is on a path boundary, so the sibling
           # directory stays itself while the root itself becomes the marker.
           "sibling": "/tmp/xy/z", "root": "/tmp/x"}
    assert gc.strip_volatile(obj, "/tmp/x") == {
        "gw": 4, "nested": [{"path": "<cwd>/reports/a.json"}], "other": "/tmp/y/z",
        "sibling": "/tmp/xy/z", "root": "<cwd>"}


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


REPO = Path(__file__).resolve().parents[1]


def test_the_fixture_is_under_the_size_budget():
    gc.golden_header_or_skip(REPO)
    assert gc.fixture_kb(gc.GOLDEN_DIR) < 5120


@pytest.fixture(scope="module")
def golden_run(tmp_path_factory):
    """One pipeline run per module, shared by the golden tests. Skips,
    loudly (v18a), when a hashed input moved (spec §2.6), when the board has
    not been recorded, or when there is no models/ at all."""
    header = gc.golden_header_or_skip(REPO)
    root = tmp_path_factory.mktemp("golden")
    gc.build_scratch_tree(root, REPO)
    advice, state, ladder = gc.run_golden(root)
    cwd = str(root.resolve())
    return {"header": header, "cwd": cwd,
            "advice": gc.strip_volatile(advice, cwd),
            "state": gc.strip_volatile(state, cwd),
            "ladder": gc.strip_volatile(ladder, cwd)}


@pytest.mark.golden
def test_the_golden_board_reproduces_the_expected_advice_and_state(golden_run):
    expected = gc.GOLDEN_DIR / gc.EXPECTED_DIR
    assert golden_run["advice"] == json.loads((expected / "advice.json").read_text())
    assert golden_run["state"] == json.loads((expected / "solve_state.json").read_text())


@pytest.mark.golden
def test_the_golden_board_reproduces_the_expected_ladder(golden_run):
    """v18b Task 4: the ladder joins advice and state as a fourth expected
    file. Fails clearly, naming the missing fixture, until the orchestrator
    re-records ``expected/ladder.json`` for this cycle."""
    path = gc.GOLDEN_DIR / gc.EXPECTED_DIR / "ladder.json"
    if not path.exists():
        pytest.fail(f"{path} not recorded; run python -m tests.golden_client --write")
    assert golden_run["ladder"] == json.loads(path.read_text())


@pytest.mark.golden
def test_the_golden_board_still_exercises_every_lever(golden_run):
    counts = gc.lever_counts(golden_run["advice"])
    assert gc.levers_below_floor(counts) == []
    assert counts == golden_run["header"]["levers"]


@pytest.mark.golden
def test_the_golden_run_writes_nothing_through_the_symlinks(golden_run):
    """``models/`` and ``data/history`` are symlinks into the repo (spec
    §2.4); a run that wrote through one would have changed a digest."""
    assert gc.stale_inputs(golden_run["header"], REPO) == []


@pytest.mark.golden
def test_the_golden_board_serves_the_recorded_plan_route(golden_run):
    """v17f §1 part 2: the board's plan route, byte for byte, over the run
    the module fixture already made. Recorded on main's code before the
    served plan moved; never re-recorded inside v17f."""
    expected = json.loads((gc.GOLDEN_DIR / gc.EXPECTED_DIR / "plan.json").read_text())
    served = gc.plan_route(Path(golden_run["cwd"]), int(golden_run["header"]["gw"]))
    assert served == expected


def test_the_header_config_is_golden_config():
    """On the keys the header recorded: a field added after the recording
    (v17e §2.7 added three) is not in the header, and the fixture is never
    rewritten by a refactor. The added fields must hold what the recorded
    config.toml implies — price_timing = true is written, the other two are
    absent and so default.

    The comparison is two-sided even though it is written over the header's
    keys: a field that is removed or renamed leaves the header carrying a key
    the golden config lacks, and the dict equality fails on it. The added
    fields are checked only where they are still added, so the next
    legitimate `--record` — after which the header carries all of them and
    `added` is empty — does not have to edit this test."""
    header = gc.golden_header_or_skip(REPO)
    golden = asdict(gc.golden_config())
    assert {k: v for k, v in golden.items()
            if k in header["config"]} == header["config"]
    added = {k: v for k, v in golden.items() if k not in header["config"]}
    defaults = {"price_timing": True, "xg_per_shot": False,
                "news_lineup_providers": ["ffs", "rotowire"]}
    assert added == {k: v for k, v in defaults.items() if k in added}
    assert header["config"]["odds_api_key"] == ""


def test_the_recorded_config_file_has_no_odds_section():
    gc.golden_header_or_skip(REPO)
    path = gc.GOLDEN_DIR / "config.toml"
    assert "[odds]" not in path.read_text()
    assert "api_key" not in path.read_text()


def _stub_run_advise(tmp_path: Path, calls: dict, live_mod):
    """The ``run_advise`` a ``run_golden`` test runs instead of the pipeline:
    it records what it was handed and writes the two report files."""
    import time as time_mod

    def fake_run_advise(cfg, client=None):
        calls["cwd"] = Path.cwd()
        calls["cfg"] = cfg
        calls["client"] = client
        calls["sleep"] = live_mod.time.sleep
        calls["stdlib_sleep"] = time_mod.sleep
        (tmp_path / "reports" / "gw4-advice.json").write_text(
            json.dumps({"gw": 4, "generated_at": "x"}))
        (tmp_path / "reports" / "solve_state_gw4.json").write_text(
            json.dumps({"gw": 4, "generated_at": "y"}))
        (tmp_path / "reports" / "ladder_gw4.json").write_text(
            json.dumps({"gw": 4, "generated_at": "z", "wall_s": 1.2}))

        class A:
            gw = 4
        return A()

    return fake_run_advise


def test_run_golden_runs_in_the_scratch_tree_and_reads_the_two_files_back(tmp_path, monkeypatch):
    """``run_golden`` over a stub ``run_advise``: it chdirs into the root,
    clears the serving-config cache on both sides, silences the refresh
    sleep for the replay client, and hands back the two JSON files the run
    wrote."""
    import time as time_mod

    import gaffer.data.live as live_mod
    from gaffer.config import config_in_force, invalidate

    calls: dict[str, object] = {}
    (tmp_path / "reports").mkdir()
    client = gc.RecordedClient(_bundle(tmp_path / "bundle"))

    monkeypatch.setattr(gc, "run_advise", _stub_run_advise(tmp_path, calls, live_mod))
    invalidate()
    before = Path.cwd()
    advice, state, ladder = gc.run_golden(tmp_path, client=client)
    assert Path.cwd() == before
    assert calls["cwd"] == tmp_path.resolve()
    assert asdict(calls["cfg"]) == asdict(gc.golden_config())
    assert calls["client"] is client
    assert calls["sleep"] is not time_mod.sleep
    # The patch is on live's own ``time`` name, so the stdlib module keeps
    # its sleep throughout the run (Task 4 review).
    assert calls["stdlib_sleep"] is time_mod.sleep
    assert live_mod.time.sleep is time_mod.sleep
    assert advice == {"gw": 4, "generated_at": "x"} and state == {"gw": 4, "generated_at": "y"}
    assert ladder == {"gw": 4, "generated_at": "z", "wall_s": 1.2}
    assert config_in_force.cache_info().currsize == 0


def test_run_golden_keeps_the_politeness_sleep_for_a_live_client(tmp_path, monkeypatch):
    """v17c §2.8: the sleep is silenced only for a ``RecordedClient``. The
    recorder does contact the server, so ``--record``'s 654 element-summary
    fetches keep ``refresh_live``'s pacing."""
    import time as time_mod

    import gaffer.data.live as live_mod

    calls: dict[str, object] = {}
    (tmp_path / "reports").mkdir()

    monkeypatch.setattr(gc, "run_advise", _stub_run_advise(tmp_path, calls, live_mod))
    gc.run_golden(tmp_path, client=object())
    assert calls["sleep"] is time_mod.sleep


def test_run_golden_restores_the_cwd_when_the_run_raises(tmp_path, monkeypatch):
    from gaffer.config import config_in_force

    def boom(cfg, client=None):
        raise RuntimeError("solver died")

    monkeypatch.setattr(gc, "run_advise", boom)
    before = Path.cwd()
    with pytest.raises(RuntimeError, match="solver died"):
        gc.run_golden(tmp_path, client=object())
    assert Path.cwd() == before
    # The golden's config must not survive the failure into the next caller.
    assert config_in_force.cache_info().currsize == 0


def test_write_expected_refuses_without_a_bundle(tmp_path):
    """The refusal comes before the scratch tree, so a mistyped directory
    writes nothing (Task 4 review)."""
    with pytest.raises(SystemExit, match="run --record first"):
        gc.write_expected(tmp_path / "empty")


def test_write_expected_gathers_the_inputs_in_a_fresh_scratch_tree(tmp_path, monkeypatch):
    """v18a Task 2b: the run's own scratch tree already carries the report
    it wrote, and gathering there a second time would record it as
    ``Inputs.prior_advice`` — a value ``--inputs`` mode, which always
    gathers in a tree of its own, records as ``None``. The two entry points
    must build the same Inputs, so the gather here must not reuse the run's
    root."""
    golden = tmp_path / "golden"
    golden.mkdir()
    (golden / gc.BUNDLE_NAME).write_bytes(b"not a real bundle")
    monkeypatch.setattr(gc, "HASHED_ROOTS", ())  # the missing-roots refusal is not this test's concern

    built: list[Path] = []
    monkeypatch.setattr(gc, "build_scratch_tree",
                        lambda root, repo, golden=None: built.append(Path(root)))

    run_roots: list[Path] = []

    def fake_run_golden(root, client=None):
        run_roots.append(Path(root))
        return {"gw": 4}, {"gw": 4}, {"gw": 4}

    monkeypatch.setattr(gc, "run_golden", fake_run_golden)
    monkeypatch.setattr(gc, "plan_route", lambda root, gw, client=None: {"plan": True})

    gather_roots: list[Path] = []

    def fake_gather_golden(root, client=None, predictions=None):
        gather_roots.append(Path(root))
        return "the-inputs"

    monkeypatch.setattr(gc, "gather_golden", fake_gather_golden)
    saved: dict[str, object] = {}
    monkeypatch.setattr(gc, "save_inputs",
                        lambda inputs, directory: saved.update(
                            inputs=inputs, directory=directory))
    monkeypatch.setattr(gc, "load_bundle", lambda directory: {})
    monkeypatch.setattr(gc, "lever_counts", lambda advice: {})
    monkeypatch.setattr(gc, "input_hashes", lambda repo: {})
    monkeypatch.setattr(gc, "_git_head", lambda repo: "deadbee")

    gc.write_expected(golden)

    assert len(built) == 2, "one scratch tree for the run, one for the gather"
    assert run_roots == [built[0]]
    assert gather_roots == [built[1]]
    assert built[0] != built[1], "the gather must not reuse the run's own root"
    assert saved == {"inputs": "the-inputs", "directory": golden / gc.INPUTS_DIR}


def test_main_refuses_to_run_outside_the_repo_root(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert gc.main(["--write"]) == 2
    assert "repo root" in capsys.readouterr().err


# --- the recorded Inputs (v17g §2.8) ------------------------------------


def test_the_recording_models_bank_the_frame_the_live_models_returned(tmp_path,
                                                                     monkeypatch):
    """v17g §2.5: the frame banked is ``predict_components``' own, before the
    blend and the rescale — so what is banked is what came back, untouched,
    and ``missing`` and ``calibration`` are pass-throughs."""
    frame = pd.DataFrame({"code": [101, 102], "gw": [4, 4], "ep": [5.5, 1.25]})
    rec = gc.RecordingModels(tmp_path / "inputs")
    monkeypatch.setattr(rec._live, "components", lambda **kw: frame)
    monkeypatch.setattr(rec._live, "missing", lambda: ["team"])
    monkeypatch.setattr(rec._live, "calibration", lambda: "cal")

    out = rec.components(pred_frame=None, tg_future=None, players=None,
                         avail=None, pens=None)
    assert out is frame
    pd.testing.assert_frame_equal(
        pd.read_parquet(tmp_path / "inputs" / gc.PREDICTED_NAME), frame)
    assert rec.missing() == ["team"] and rec.calibration() == "cal"


def test_gather_golden_gathers_in_the_scratch_tree_under_the_golden_config(
        tmp_path, monkeypatch):
    """The sibling of ``run_golden``, asserted the way ``run_golden`` is: the
    cwd, the config and the two seams it hands on."""
    calls: dict[str, object] = {}

    def fake_gather(cfg, client=None, *, predictions=None):
        calls.update(cwd=Path.cwd(), cfg=cfg, client=client,
                     predictions=predictions)
        return "gathered"

    monkeypatch.setattr(gc, "gather_inputs", fake_gather)
    client = gc.RecordedClient(_bundle(tmp_path / "bundle"))
    before = Path.cwd()
    assert gc.gather_golden(tmp_path, client, "models") == "gathered"
    assert Path.cwd() == before
    assert calls["cwd"] == tmp_path.resolve()
    assert asdict(calls["cfg"]) == asdict(gc.golden_config())
    assert calls["client"] is client and calls["predictions"] == "models"


def test_the_inputs_mode_records_the_inputs_and_leaves_the_header_alone(
        tmp_path, monkeypatch, capsys):
    """v17g §2.8: ``--write`` restamps ``written_at``, ``commit`` and
    ``runtime_s`` and rewrites the expected files, which is churn a no-op
    refactor must not create. ``--inputs`` writes one directory."""
    seen: dict[str, object] = {}

    def fake_gather_golden(root, client=None, predictions=None):
        seen.update(root=root, predictions=predictions)
        return "inputs"

    monkeypatch.setattr(gc, "gather_golden", fake_gather_golden)
    monkeypatch.setattr(gc.tempfile, "mkdtemp", lambda prefix=None: str(tmp_path))
    monkeypatch.setattr(gc, "build_scratch_tree",
                        lambda root, repo, golden=None: seen.update(built=root))
    monkeypatch.setattr(gc, "write_expected", lambda *a, **kw: pytest.fail(
        "--inputs must not rewrite the expected files"))
    monkeypatch.setattr(gc, "save_inputs",
                        lambda inputs, directory: seen.update(
                            saved=(inputs, directory)))

    assert gc.main(["--inputs"]) == 0
    assert seen["built"] == seen["root"] == tmp_path
    assert seen["saved"] == ("inputs", gc.GOLDEN_DIR / gc.INPUTS_DIR)
    assert seen["predictions"].directory == gc.GOLDEN_DIR / gc.INPUTS_DIR
    assert str(gc.GOLDEN_DIR / gc.INPUTS_DIR) in capsys.readouterr().out


def _needs_recorded_inputs() -> None:
    if not (gc.GOLDEN_DIR / gc.INPUTS_DIR).exists():
        pytest.skip("inputs not recorded yet "
                    "(python -m tests.golden_client --inputs)")


def _built_from_inputs(tmp_path, monkeypatch):
    """``build_advice`` over the recorded Inputs, serialized the way
    ``run_advise`` serializes it, so the comparison is like for like.

    Built in ``tmp_path`` and not in the repo root, which is
    ``advice_fixture.a_scratch_working_directory``'s reason turned around: a
    build is supposed to write nothing, and the day one regains a write is
    the day this overwrites the user's own gameweek. It is also the cwd the
    expected numbers were recorded under — a tree with no price log — so a
    read that leaked past the seal answers here as it answered there, rather
    than with this machine's week.
    """
    from gaffer.advise import build_advice
    from gaffer.inputs import load_inputs

    # Loaded before the chdir: the recording is addressed absolutely, and
    # reading it is the caller's read, never the build's.
    inputs = load_inputs(gc.GOLDEN_DIR / gc.INPUTS_DIR)
    monkeypatch.chdir(tmp_path)
    out = build_advice(inputs, gc.golden_config())
    return out, json.loads(json.dumps(asdict(out.advice), default=str))


@pytest.mark.golden
def test_the_recorded_inputs_build_the_same_advice_with_no_models(tmp_path,
                                                                 monkeypatch):
    """Spec §1 part 2. No hash guard and no module fixture: the point of this
    test is that it runs where the others cannot — with no ``models/`` on the
    machine at all, which is the limit v17c wrote down."""
    _needs_recorded_inputs()
    _, advice = _built_from_inputs(tmp_path, monkeypatch)
    expected = json.loads(
        (gc.GOLDEN_DIR / gc.EXPECTED_DIR / "advice.json").read_text())
    cwd = str(tmp_path.resolve())
    assert gc.strip_volatile(advice, cwd) == gc.strip_volatile(expected, cwd)


@pytest.mark.golden
def test_the_recorded_inputs_build_the_same_solve_state(tmp_path, monkeypatch):
    """The state is compared through its own writer, because that writer is
    what made the expected file: the pool goes to parquet and the scalars to
    JSON, and re-deriving that dict here would be a second opinion."""
    _needs_recorded_inputs()
    from gaffer.artifacts import save_solve_state

    out, _ = _built_from_inputs(tmp_path, monkeypatch)
    save_solve_state(out.state)
    written = json.loads(
        (tmp_path / "reports" / f"solve_state_gw{out.state.gw}.json").read_text())
    expected = json.loads(
        (gc.GOLDEN_DIR / gc.EXPECTED_DIR / "solve_state.json").read_text())
    cwd = str(tmp_path.resolve())
    assert gc.strip_volatile(written, cwd) == gc.strip_volatile(expected, cwd)


@pytest.mark.golden
def test_build_advice_opens_no_file(monkeypatch):
    """Spec §1 part 4, the run-time half.

    Run in the repo root on purpose, and it is the one build here that is:
    ``config.toml`` is under the repo root, so a ``config_in_force()`` that
    crept back onto the build path opens a file *here* and is caught, where
    in a scratch tree it would find nothing and pass. Nothing can be written
    from inside the seal, so the working tree is safe for the length of it.

    The rail asserts the numbers as well as the absence of a traceback,
    because a hidden read can hide behind a swallowed exception —
    ``ladder._hit_bar`` falls back to a printed line and a default bar.

    Two things this seal gets wrong if written the obvious way, both found by
    mutation-testing the ladder's own rail (v17g, T2 review):

    * ``pathlib.Path.read_text()`` resolves ``io.open``, not
      ``builtins.open`` — and ``Path.read_text`` is the idiom every loader in
      ``artifacts.py`` uses, so a builtins-only patch cannot see the reads
      this rail exists to catch;
    * an ``AssertionError`` sentinel is an ``Exception``, and the ladder and
      the served passes are full of ``except Exception`` blocks that would
      swallow it into a printed line and pass.

    Two reads are tolerated, and warmed rather than worked around. Both are
    **shipped package assets** read through ``importlib.resources``:
    ``decision_priors.json``, which ``artifacts.solve_kw_from_state`` reads
    when the board was solved with the priors on, and
    ``scenario_noise.json``, which the σ table reads through
    ``optimize.scenarios.scenario_noise``. Neither can replay anybody's
    gameweek — they are the same bytes in every working directory — so the
    read happens here, before the seal, and the value is served from the
    cache inside it. ``scenario_noise`` has that cache already; the priors
    reader is given one for the length of the test.
    """
    _needs_recorded_inputs()
    # Every module build_advice reaches, imported before open() is taken
    # away: an import that is not yet in sys.modules opens a file.
    import gaffer.advise, gaffer.assets, gaffer.config  # noqa: F401
    import gaffer.ladder, gaffer.served  # noqa: F401
    from gaffer.advise import build_advice
    from gaffer.inputs import load_inputs
    from gaffer.optimize.scenarios import scenario_noise

    # pd.read_parquet opens files, so the recording is loaded before the seal
    # and not inside it.
    inputs = load_inputs(gc.GOLDEN_DIR / gc.INPUTS_DIR)
    expected = json.loads(
        (gc.GOLDEN_DIR / gc.EXPECTED_DIR / "advice.json").read_text())

    scenario_noise()
    warmed = functools.lru_cache(maxsize=1)(gaffer.assets.load_decision_priors)
    warmed()
    monkeypatch.setattr(gaffer.assets, "load_decision_priors", warmed)

    class _Opened(BaseException):
        pass

    def refuse(*a, **kw):
        raise _Opened(f"build_advice opened {a[:1]}")

    monkeypatch.setattr("builtins.open", refuse)
    monkeypatch.setattr(io, "open", refuse)
    try:
        out = build_advice(inputs, gc.golden_config())
    finally:
        # Before any assertion and before pytest formats a traceback: with
        # open() sealed, linecache cannot read the source of the frame it is
        # trying to print, and the report is lost with the failure.
        monkeypatch.undo()
    advice = json.loads(json.dumps(asdict(out.advice), default=str))
    cwd = str(Path.cwd())
    assert gc.strip_volatile(advice, cwd) == gc.strip_volatile(expected, cwd)


@pytest.mark.golden
def test_the_recorded_predictions_regather_the_same_components(tmp_path):
    """v17g §2.5: the Predictions seam is real only if its second adapter
    reproduces the first. Gathers with the recorded client *and* the recorded
    predictions — no network and no ``models/`` — and asks for the one frame
    that seam controls. ``ep_named`` and ``ep_by`` are not compared: the
    recorded adapter has no calibration model, which the adapter's own
    docstring says."""
    _needs_recorded_inputs()
    from gaffer.inputs import RecordedComponents, load_inputs

    root = tmp_path / "scratch"
    gc.build_scratch_tree(root, REPO)
    again = gc.gather_golden(root, gc.RecordedClient(),
                             RecordedComponents(gc.GOLDEN_DIR / gc.INPUTS_DIR))
    recorded = load_inputs(gc.GOLDEN_DIR / gc.INPUTS_DIR)
    pd.testing.assert_frame_equal(again.comp, recorded.comp)


@pytest.mark.golden
def test_gather_inputs_and_build_advice_read_no_view(tmp_path, monkeypatch):
    """v18b ruling 4: both halves read ``cfg`` and never the process-wide
    cached view. The sibling above seals ``open()``; this one seals
    ``config_in_force`` the same way, over the same two calls — but aimed
    at ``gather_inputs`` rather than ``build_advice``, because every read
    ruling 4 exists to catch (``served.price_falls``,
    ``price_timing._owned_price_falls``,
    ``models.availability.apply_availability``,
    ``artifacts.save_availability``) fires on the gather side: ``build_advice``
    itself takes ``price_timing``/``price_fall`` off ``inputs`` and never
    calls :func:`~gaffer.served.price_falls` at all (grep confirms it — the
    only caller left is :func:`~gaffer.served.trace_context`, the loader's
    own present-tense read for a file written before v17f).

    Gathered with the recorded client and :class:`~gaffer.inputs.RecordedComponents`
    — no network and no ``models/`` — and the gathered components frame is
    compared to the recorded one, as the sibling above does; the *build* half
    runs off the recorded Inputs, because the recorded adapter has no
    calibration model and a board built from its gather is not the expected
    board (the sibling's docstring says so). The seal is the assertion for
    both halves; the byte comparison is the build's.

    Patched at the name each consumer bound it (``tests.conftest.patch_view``):
    ``gaffer.price_timing`` binds ``config_in_force`` at import time, so a
    patch on ``gaffer.config`` alone would never reach
    ``_owned_price_falls``; ``served.py``, ``models/availability.py`` and
    ``artifacts.py`` import it lazily inside the function they read it in,
    so patching ``gaffer.config`` catches those three.
    """
    _needs_recorded_inputs()
    import gaffer.config
    import gaffer.price_timing
    from gaffer.advise import build_advice
    from gaffer.inputs import RecordedComponents, load_inputs
    from tests.conftest import patch_view

    root = tmp_path / "scratch"
    gc.build_scratch_tree(root, REPO)

    class _Read(BaseException):
        pass

    def refuse():
        raise _Read("config_in_force read on the build path")

    patch_view(monkeypatch, refuse)
    patch_view(monkeypatch, refuse, gaffer.price_timing)
    try:
        gathered = gc.gather_golden(
            root, gc.RecordedClient(),
            RecordedComponents(gc.GOLDEN_DIR / gc.INPUTS_DIR))
        recorded = load_inputs(gc.GOLDEN_DIR / gc.INPUTS_DIR)
        out = build_advice(recorded, gc.golden_config())
    finally:
        monkeypatch.undo()
    pd.testing.assert_frame_equal(gathered.comp, recorded.comp)
    expected = json.loads(
        (gc.GOLDEN_DIR / gc.EXPECTED_DIR / "advice.json").read_text())
    advice = json.loads(json.dumps(asdict(out.advice), default=str))
    cwd = str(root.resolve())
    assert gc.strip_volatile(advice, cwd) == gc.strip_volatile(expected, cwd)


def test_build_advice_names_no_reader_in_its_source():
    """Spec §1 part 4, the static half. The run-time half above cannot run
    until the board is recorded; this one always can."""
    import inspect

    from gaffer.advise import build_advice

    src = inspect.getsource(build_advice)
    for token in ("open(", "Path(", "client.", "load_", "save_", "store.",
                  "atomic_write"):
        assert token not in src, token


def test_every_inputs_field_is_read_by_build_advice():
    """Spec §2.7: a field nothing reads is a field the golden has to record
    and keep correct for no reader."""
    import dataclasses
    import inspect

    from gaffer.advise import build_advice
    from gaffer.inputs import Inputs

    src = inspect.getsource(build_advice)
    for f in dataclasses.fields(Inputs):
        assert f.name in src, f.name
