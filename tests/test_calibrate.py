import joblib
import numpy as np
import pandas as pd
from gaffer.models.calibrate import CalibrationModel


def _frame(n=1200, bias=1.1, seed=7):
    rng = np.random.default_rng(seed)
    ep = pd.Series(rng.uniform(1, 8, n))
    actual = ep + bias + rng.normal(0, 2, n)   # model under-predicts by `bias`
    pos = pd.Series(np.where(np.arange(n) % 2 == 0, "MID", "FWD"))
    return ep, actual, pos


def test_fit_corrects_constant_bias():
    ep, actual, pos = _frame()
    cal = CalibrationModel().fit(ep, actual, pos)
    out = cal.apply(ep, pos)
    resid = (actual - out).mean()
    assert abs(resid) < 0.15          # raw bias was 1.1


def test_unfitted_model_is_identity():
    ep, _, pos = _frame(n=50)
    out = CalibrationModel().apply(ep, pos)
    pd.testing.assert_series_equal(out, ep.astype(float))


def test_unseen_position_passes_through():
    ep, actual, pos = _frame()
    cal = CalibrationModel().fit(ep, actual, pos)
    gk_ep = pd.Series([3.0, 5.0])
    out = cal.apply(gk_ep, pd.Series(["GKP", "GKP"]))
    pd.testing.assert_series_equal(out, gk_ep)


def test_small_group_not_fitted():
    ep, actual, pos = _frame(n=100)   # below MIN_ROWS per group
    cal = CalibrationModel().fit(ep, actual, pos)
    assert cal.by_pos == {}


def test_model_round_trips_through_joblib(tmp_path):
    ep, actual, pos = _frame()
    cal = CalibrationModel().fit(ep, actual, pos)
    path = tmp_path / "calibration.joblib"
    joblib.dump(cal, path)
    loaded = joblib.load(path)
    pd.testing.assert_series_equal(loaded.apply(ep, pos), cal.apply(ep, pos))
