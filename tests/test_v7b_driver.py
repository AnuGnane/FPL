"""v7b measurement drivers: the vendored head and the replay flag surface."""

import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, "scripts")

from v7b_legacy_minutes import LGB_KW as LEGACY_LGB_KW  # noqa: E402
from v7b_legacy_minutes import LegacyMinutesModel  # noqa: E402

from gaffer.models.minutes import LGB_KW, ThreeModeModel  # noqa: E402
from gaffer.models.train import MINUTES_FEATURES  # noqa: E402


def _frame(n: int = 240) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    df = pd.DataFrame({c: rng.normal(size=n) for c in MINUTES_FEATURES})
    df["minutes"] = rng.integers(0, 91, size=n)
    df["code"] = np.arange(n) % 40
    df["season_idx"] = 3
    df["gw"] = np.arange(n) % 6 + 1
    return df


def test_the_vendored_head_carries_the_original_hyperparameters():
    assert LEGACY_LGB_KW == LGB_KW


def test_the_vendored_head_matches_the_shipped_predict_contract():
    df = _frame()
    legacy = LegacyMinutesModel(MINUTES_FEATURES).fit(df).predict(df)
    current = ThreeModeModel(MINUTES_FEATURES).fit(df).predict(df)
    assert list(legacy.columns) == list(current.columns)
    assert len(legacy) == len(df)
    assert (legacy["p60"] <= legacy["p_play"] + 1e-9).all()


def test_the_vendored_head_is_not_the_shipped_head():
    # If these ever agreed, the ablation would measure nothing.
    df = _frame()
    legacy = LegacyMinutesModel(MINUTES_FEATURES).fit(df).predict(df)
    current = ThreeModeModel(MINUTES_FEATURES).fit(df).predict(df)
    assert not np.allclose(legacy["p60"], current["p60"])


import gaffer.backtest as bt  # noqa: E402
import gaffer.features.engineer as eng  # noqa: E402
import gaffer.models.train as tr  # noqa: E402
import gaffer.optimize.scenarios as sc  # noqa: E402

import v7b_replay  # noqa: E402


def test_the_defaults_are_exactly_the_s2_configuration():
    cfg = v7b_replay.arm_config(["--arm", "heur", "--tag", "x"])
    assert cfg.arm == "heur"
    assert cfg.seed_base == 20260827
    assert cfg.chips is True
    assert cfg.priors == "current"
    assert cfg.minutes == "current"
    assert cfg.frame == "current"
    assert cfg.log_path == "live/backtest_log_v7b_x.parquet"
    assert cfg.report_path == "reports/v7b_x.json"


def test_every_default_toggle_patches_nothing():
    cfg = v7b_replay.arm_config(["--arm", "raw", "--tag", "rail"])
    before = (tr.ThreeModeModel, tr.cup_matches, eng.add_shrunken_modes,
              bt.load_decision_priors)
    undo = v7b_replay.apply_patches(cfg)
    try:
        assert (tr.ThreeModeModel, tr.cup_matches, eng.add_shrunken_modes,
                bt.load_decision_priors) == before
    finally:
        undo()


@pytest.mark.parametrize("flag,value,module,name", [
    (["--minutes", "legacy"], LegacyMinutesModel, tr, "ThreeModeModel"),
    (["--frame", "v4c"], None, tr, "cup_matches"),
    (["--priors", "off"], None, bt, "load_decision_priors"),
])
def test_each_non_default_toggle_bites_and_unwinds(flag, value, module, name):
    cfg = v7b_replay.arm_config(["--arm", "raw", "--tag", "t"] + flag)
    original = getattr(module, name)
    undo = v7b_replay.apply_patches(cfg)
    patched = getattr(module, name)
    assert patched is not original
    if value is None:
        assert patched() is None
    else:
        assert patched is value
    undo()
    assert getattr(module, name) is original


def test_v4c_frame_also_neutralises_shrunken_modes():
    cfg = v7b_replay.arm_config(["--arm", "raw", "--tag", "t",
                                 "--frame", "v4c"])
    df = pd.DataFrame({"a": [1, 2]})
    undo = v7b_replay.apply_patches(cfg)
    try:
        assert eng.add_shrunken_modes(df) is df
    finally:
        undo()


def test_the_seed_is_the_base_plus_the_gameweek():
    seen = {}

    def fake_run_scenarios(pool, state, xm, n, seed, **kw):
        seen["seed"] = seed
        seen["n"] = n
        raise RuntimeError("stop")

    cfg = v7b_replay.arm_config(["--arm", "heur", "--tag", "t",
                                 "--seed-base", "20260825"])
    gate = v7b_replay.make_gate(cfg, {"xmins": {(1, 5): 60.0}},
                                lambda pool, state, **kw: "plan",
                                run_scenarios=fake_run_scenarios)
    state = type("S", (), {"owned_codes": [1], "wildcard_gw": None,
                           "free_transfers": 1, "gws": [5]})()
    with pytest.raises(RuntimeError):
        gate(pd.DataFrame({"code": [1]}), state)
    assert seen == {"seed": 20260830, "n": 40}


def test_the_gate_stands_aside_on_the_solves_production_leaves_raw():
    gate = v7b_replay.make_gate(
        v7b_replay.arm_config(["--arm", "heur", "--tag", "t"]),
        {"xmins": {(1, 5): 60.0}}, lambda pool, state, **kw: "raw",
        run_scenarios=lambda *a, **k: pytest.fail("must not sweep"))
    for kwargs in ({"owned_codes": []}, {"wildcard_gw": 7},
                   {"free_transfers": 15}):
        base = {"owned_codes": [1], "wildcard_gw": None,
                "free_transfers": 1, "gws": [5]}
        state = type("S", (), {**base, **kwargs})()
        assert gate(pd.DataFrame({"code": [1]}), state) == "raw"


def test_a_raw_arm_never_installs_a_gate():
    cfg = v7b_replay.arm_config(["--arm", "raw", "--tag", "t"])
    assert v7b_replay.gate_wanted(cfg) is False
    assert v7b_replay.gate_wanted(
        v7b_replay.arm_config(["--arm", "heur", "--tag", "t"])) is True


def test_a_noise_asset_is_required_for_a_table_arm_and_refused_otherwise():
    with pytest.raises(SystemExit):
        v7b_replay.arm_config(["--arm", "composite", "--tag", "t"])
    with pytest.raises(SystemExit):
        v7b_replay.arm_config(["--arm", "heur", "--tag", "t",
                               "--noise-asset", "reports/x.json"])


import v7b_probe  # noqa: E402


def test_identical_component_frames_compare_equal():
    a = pd.DataFrame({"code": [1, 2], "p_play": [0.5, 0.9],
                      "p60": [0.4, 0.8], "gw": [5, 5]})
    assert v7b_probe.frames_identical(a, a.copy()) is True


def test_a_single_changed_cell_is_caught():
    a = pd.DataFrame({"code": [1, 2], "p_play": [0.5, 0.9],
                      "p60": [0.4, 0.8], "gw": [5, 5]})
    b = a.copy()
    b.loc[1, "p60"] = 0.8 + 1e-12
    assert v7b_probe.frames_identical(a, b) is False


def test_the_xmins_summary_reports_the_noise_scale_it_implies():
    comp = pd.DataFrame({"code": [1, 2], "gw": [5, 5],
                         "p_play": [1.0, 1.0], "p60": [1.0, 0.0]})
    out = v7b_probe.xmins_summary(comp)
    assert out["n"] == 2
    assert out["mean_xmins"] == pytest.approx(67.5)
    # (92 - xmins) / 134, the heuristic scale the gate would apply
    assert out["mean_noise_scale"] == pytest.approx(
        ((92 - 90) / 134 + (92 - 45) / 134) / 2)


def test_seed_bases_derive_one_arm_per_base():
    """Each base owns its log and its report: two bases sharing either would
    read each other's hits and transfers and the trio would be one draw."""
    configs, bases, tag = v7b_replay.arm_configs(
        ["--arm", "raw", "--tag", "q", "--seed-bases", "1,2,3"])
    assert bases == [1, 2, 3]
    assert tag == "q"
    assert [c.tag for c in configs] == ["q-s1", "q-s2", "q-s3"]
    assert [c.seed_base for c in configs] == [1, 2, 3]
    assert [c.log_path for c in configs] == [
        "live/backtest_log_v7b_q-s1.parquet",
        "live/backtest_log_v7b_q-s2.parquet",
        "live/backtest_log_v7b_q-s3.parquet"]
    assert [c.report_path for c in configs] == [
        "reports/v7b_q-s1.json", "reports/v7b_q-s2.json",
        "reports/v7b_q-s3.json"]


def test_seed_bases_tolerate_spaces_in_the_list():
    configs, bases, _ = v7b_replay.arm_configs(
        ["--arm", "raw", "--tag", "q", "--seed-bases", "1, 2 ,3"])
    assert bases == [1, 2, 3]
    assert [c.tag for c in configs] == ["q-s1", "q-s2", "q-s3"]


def test_a_single_seed_base_still_derives_one_unsuffixed_arm():
    """The single-seed path must be byte-identical to today's: same tag, same
    log, same report, no aggregate."""
    configs, bases, tag = v7b_replay.arm_configs(
        ["--arm", "raw", "--tag", "q", "--seed-base", "20260825"])
    assert bases is None
    assert tag == "q"
    assert [c.tag for c in configs] == ["q"]
    assert configs[0].seed_base == 20260825
    assert configs[0].log_path == "live/backtest_log_v7b_q.parquet"
    assert configs[0].report_path == "reports/v7b_q.json"


def test_the_two_seed_flags_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        v7b_replay.arm_configs(["--arm", "raw", "--tag", "q",
                                "--seed-base", "1", "--seed-bases", "1,2"])


def test_a_one_element_seed_bases_list_is_refused():
    """K >= 2 or use --seed-base: a "multi-seed" run of one is the single-draw
    verdict convention 1 exists to stop."""
    with pytest.raises(SystemExit):
        v7b_replay.arm_configs(["--arm", "raw", "--tag", "q",
                                "--seed-bases", "20260825"])


def test_a_non_numeric_seed_base_is_refused():
    with pytest.raises(SystemExit):
        v7b_replay.arm_configs(["--arm", "raw", "--tag", "q",
                                "--seed-bases", "20260825,tuesday"])


import json  # noqa: E402
from pathlib import Path  # noqa: E402


def _fake_backtest(monkeypatch, totals):
    """Drive ``main`` over a stubbed replay: one canned total per call."""
    seen = []
    pending = list(totals)

    def run_backtest(season, start_gw, horizon, chips):
        seen.append((season, start_gw, horizon, chips))
        return {"total": pending.pop(0), "chips_played": {}}

    def load(rel):
        return pd.DataFrame({"chip": ["", "bboost"], "points": [40, 60],
                             "hits": [0, 4], "transfers": [1, 2]})

    monkeypatch.setattr(v7b_replay.bt, "run_backtest", run_backtest)
    monkeypatch.setattr(v7b_replay.bt_store, "load", load)
    return seen


def test_the_multi_seed_run_replays_every_base_and_reports_each(
        tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    seen = _fake_backtest(monkeypatch, [1800, 1900, 1850])
    out = v7b_replay.main(["--arm", "raw", "--tag", "t",
                           "--seed-bases", "1,2,3"])
    assert len(seen) == 3
    printed = capsys.readouterr().out.splitlines()
    arm_lines = [ln for ln in printed if ln.startswith("V7B_ARM_DONE")]
    assert [ln.split()[1] for ln in arm_lines] == ["t-s1", "t-s2", "t-s3"]
    assert [json.loads(ln.split(" ", 2)[2])["total"] for ln in arm_lines] == \
        [1800, 1900, 1850]
    for tag in ("t-s1", "t-s2", "t-s3"):
        banked = json.loads(Path(f"reports/v7b_{tag}.json").read_text())
        assert banked["hits"] == 4 and banked["transfers"] == 3
        assert banked["config"]["tag"] == tag
    done = [ln for ln in printed if ln.startswith("MULTISEED_DONE")]
    assert len(done) == 1
    assert done[0].split()[1] == "t"
    assert json.loads(done[0].split(" ", 2)[2]) == out
    assert out == {"totals": [1800, 1900, 1850], "mean": 1850.0,
                   "spread": 100, "range": [1800, 1900],
                   "seed_bases": [1, 2, 3]}


def test_a_single_seed_run_prints_one_line_and_no_aggregate(
        tmp_path, monkeypatch, capsys):
    """The pre-v7c behaviour, unchanged: one arm, one report, one line."""
    monkeypatch.chdir(tmp_path)
    _fake_backtest(monkeypatch, [1876])
    out = v7b_replay.main(["--arm", "raw", "--tag", "t",
                           "--seed-base", "20260901"])
    printed = capsys.readouterr().out.splitlines()
    assert [ln.split()[:2] for ln in printed if ln.startswith("V7B_")] == \
        [["V7B_ARM_DONE", "t"]]
    assert not [ln for ln in printed if ln.startswith("MULTISEED_DONE")]
    assert out["total"] == 1876
    assert out["config"]["seed_base"] == 20260901
    assert Path("reports/v7b_t.json").exists()


def test_the_multi_seed_loop_leaves_the_backtest_module_as_it_found_it(
        tmp_path, monkeypatch):
    """Three bases in one process: a gate stacked on a gate, or an arm store
    left pointing at the previous base's log, would corrupt every run after
    the first."""
    monkeypatch.chdir(tmp_path)
    _fake_backtest(monkeypatch, [1800, 1900, 1850])
    before = (v7b_replay.bt.store, v7b_replay.bt.solve_plan,
              v7b_replay.bt.predict_components_simple)
    v7b_replay.main(["--arm", "raw", "--tag", "t", "--seed-bases", "1,2,3"])
    assert (v7b_replay.bt.store, v7b_replay.bt.solve_plan,
            v7b_replay.bt.predict_components_simple) == before


def test_the_aggregate_is_the_mean_spread_and_range_of_the_totals():
    """Convention 1's arithmetic: verdicts read mean +/- spread, and the v7b
    trio's own spread (115 pts) dwarfs every arm gap ever gated on."""
    outs = [{"total": 1876}, {"total": 1901}, {"total": 1786}]
    assert v7b_replay.multiseed_summary(
        outs, [20260901, 20260915, 20260825]) == {
            "totals": [1876, 1901, 1786], "mean": 1854.3, "spread": 115,
            "range": [1786, 1901],
            "seed_bases": [20260901, 20260915, 20260825]}
