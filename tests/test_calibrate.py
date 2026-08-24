import joblib
import numpy as np
import pandas as pd
from gaffer.models.calibrate import CalibrationModel


def _fit_rows(n=1200, bias=1.1, seed=7):
    """Fitting rows: appearances the model under-predicts by ``bias``."""
    rng = np.random.default_rng(seed)
    ep = pd.Series(rng.uniform(1, 8, n))
    actual = ep + bias + rng.normal(0, 2, n)   # model under-predicts by `bias`
    pos = pd.Series(np.where(np.arange(n) % 2 == 0, "MID", "FWD"))
    return ep, actual, pos


def _assembled(ep, position, p60):
    return pd.DataFrame({"ep": ep, "position": position, "p60": p60})


def test_fit_learns_the_under_prediction_as_a_per_position_delta():
    ep, actual, pos = _fit_rows()
    cal = CalibrationModel().fit(ep, actual, pos)
    assert set(cal.by_pos) == {"MID", "FWD"}
    for pos_name, delta in cal.by_pos.items():
        assert isinstance(delta, float)
        assert abs(delta - 1.1) < 0.2, pos_name


def test_apply_shifts_a_nailed_starter_by_the_full_delta():
    ep, actual, pos = _fit_rows()
    cal = CalibrationModel().fit(ep, actual, pos)
    out = cal.apply(_assembled([4.0], ["MID"], [1.0]))
    assert abs(out["ep"].iloc[0] - (4.0 + cal.by_pos["MID"])) < 1e-9


def test_apply_leaves_bench_filler_untouched():
    """The whole point of the p60 gate: a player who will not start keeps his
    near-zero ep instead of being lifted by a starter-only correction."""
    ep, actual, pos = _fit_rows()
    cal = CalibrationModel().fit(ep, actual, pos)
    out = cal.apply(_assembled([0.2], ["MID"], [0.0]))
    assert out["ep"].iloc[0] == 0.2


def test_apply_scales_the_delta_by_p60():
    ep, actual, pos = _fit_rows()
    cal = CalibrationModel().fit(ep, actual, pos)
    out = cal.apply(_assembled([3.0], ["FWD"], [0.5]))
    assert abs(out["ep"].iloc[0] - (3.0 + 0.5 * cal.by_pos["FWD"])) < 1e-9


def test_apply_creates_no_ties_within_a_position():
    """Isotonic calibration plateaued and collapsed the top of the ranking
    into ties; an additive shift is strictly order-preserving."""
    ep, actual, pos = _fit_rows()
    cal = CalibrationModel().fit(ep, actual, pos)
    raw = [4.0, 4.5, 5.0, 6.0, 9.0, 12.0]
    out = cal.apply(_assembled(raw, ["MID"] * 6, [1.0] * 6))["ep"]
    assert out.is_monotonic_increasing
    assert out.nunique() == len(raw)
    # Gaps are preserved exactly, not compressed.
    np.testing.assert_allclose(np.diff(out.to_numpy()), np.diff(raw))


def test_unfitted_model_is_identity():
    frame = _assembled([1.0, 5.0], ["MID", "FWD"], [0.9, 0.9])
    out = CalibrationModel().apply(frame)
    pd.testing.assert_frame_equal(out, frame)


def test_unseen_position_passes_through():
    ep, actual, pos = _fit_rows()          # only MID/FWD are fitted
    cal = CalibrationModel().fit(ep, actual, pos)
    out = cal.apply(_assembled([3.0, 5.0], ["GKP", "GKP"], [1.0, 1.0]))
    assert list(out["ep"]) == [3.0, 5.0]


def test_missing_p60_leaves_the_row_alone():
    ep, actual, pos = _fit_rows()
    cal = CalibrationModel().fit(ep, actual, pos)
    out = cal.apply(_assembled([3.0], ["MID"], [np.nan]))
    assert out["ep"].iloc[0] == 3.0


def test_small_group_not_fitted():
    ep, actual, pos = _fit_rows(n=100)   # below MIN_ROWS per group
    cal = CalibrationModel().fit(ep, actual, pos)
    assert cal.by_pos == {}


def test_model_round_trips_through_joblib(tmp_path):
    ep, actual, pos = _fit_rows()
    cal = CalibrationModel().fit(ep, actual, pos)
    path = tmp_path / "calibration.joblib"
    joblib.dump(cal, path)
    loaded = joblib.load(path)
    frame = _assembled([2.0, 6.0], ["MID", "FWD"], [1.0, 0.7])
    pd.testing.assert_frame_equal(loaded.apply(frame), cal.apply(frame))
