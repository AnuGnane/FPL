import numpy as np
import pandas as pd

from gaffer.models.dnp_calibrate import DNP_MIN_ROWS, DnpCalibrator


def _modes(p_dnp, p_sub=None, p_start=None) -> pd.DataFrame:
    p_dnp = np.asarray(p_dnp, dtype=float)
    rest = 1.0 - p_dnp
    p_sub = rest * 0.4 if p_sub is None else np.asarray(p_sub, dtype=float)
    p_start = rest * 0.6 if p_start is None else np.asarray(p_start,
                                                            dtype=float)
    return pd.DataFrame({"p_dnp": p_dnp, "p_sub": p_sub, "p_start": p_start})


def _overconfident(n=2000, seed=0):
    """A head that says 0.6 where the truth is 0.3 — v7's hypothesis."""
    rng = np.random.default_rng(seed)
    p = rng.uniform(0.0, 1.0, n)
    y = (rng.uniform(0.0, 1.0, n) < (p * 0.5)).astype(float)
    return p, y


def test_an_unfitted_calibrator_is_the_identity():
    modes = _modes([0.1, 0.9])
    pd.testing.assert_frame_equal(DnpCalibrator().apply(modes), modes)


def test_too_few_rows_leaves_the_calibrator_unfitted():
    p, y = _overconfident(n=DNP_MIN_ROWS - 1)
    assert DnpCalibrator().fit(p, y).iso is None


def test_a_single_outcome_class_leaves_the_calibrator_unfitted():
    p = np.linspace(0.0, 1.0, DNP_MIN_ROWS + 10)
    assert DnpCalibrator().fit(p, np.zeros_like(p)).iso is None


def test_the_calibrator_pulls_an_over_forecast_down():
    p, y = _overconfident()
    cal = DnpCalibrator().fit(p, y)
    out = cal.apply(_modes([0.6]))
    assert 0.2 < float(out["p_dnp"].iloc[0]) < 0.45


def test_the_calibrator_is_monotone_so_no_two_players_swap_order():
    p, y = _overconfident()
    cal = DnpCalibrator().fit(p, y)
    out = cal.apply(_modes(np.linspace(0.01, 0.99, 50)))
    assert (out["p_dnp"].diff().dropna() >= -1e-12).all()


def test_the_three_modes_still_sum_to_one_after_calibration():
    p, y = _overconfident()
    cal = DnpCalibrator().fit(p, y)
    out = cal.apply(_modes(np.linspace(0.0, 1.0, 21)))
    total = out["p_dnp"] + out["p_sub"] + out["p_start"]
    assert np.allclose(total.to_numpy(), 1.0, atol=1e-9)


def test_the_sub_start_ratio_is_preserved_where_there_is_mass_to_share():
    p, y = _overconfident()
    cal = DnpCalibrator().fit(p, y)
    out = cal.apply(_modes([0.5]))
    assert np.isclose(float(out["p_start"].iloc[0] / out["p_sub"].iloc[0]),
                      0.6 / 0.4)


def test_a_certain_dnp_row_puts_its_freed_mass_on_the_sub_mode():
    p, y = _overconfident()
    cal = DnpCalibrator().fit(p, y)
    out = cal.apply(_modes([1.0], p_sub=[0.0], p_start=[0.0]))
    freed = 1.0 - float(out["p_dnp"].iloc[0])
    assert np.isclose(float(out["p_sub"].iloc[0]), freed)
    assert float(out["p_start"].iloc[0]) == 0.0


def test_apply_does_not_mutate_its_input():
    p, y = _overconfident()
    modes = _modes([0.3, 0.7])
    before = modes.copy()
    DnpCalibrator().fit(p, y).apply(modes)
    pd.testing.assert_frame_equal(modes, before)
