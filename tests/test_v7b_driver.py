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
