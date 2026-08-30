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
