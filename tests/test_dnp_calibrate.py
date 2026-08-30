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


def _slotted(n_codes=80, n_gws=30, seed=1) -> pd.DataFrame:
    """A frame whose fringe players stop playing entirely after slot 20.

    The leakage rail's whole point: a calibrator that peeked past the boundary
    would learn the late-season DNP rate, and the test can see the difference.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for code in range(n_codes):
        fringe = code >= 40
        for gw in range(1, n_gws + 1):
            if fringe and gw > 20:
                minutes = 0
            elif fringe:
                minutes = int(rng.choice([0, 0, 90]))
            else:
                minutes = 90
            rows.append({"code": code, "season_idx": 0, "gw": gw,
                         "minutes": minutes, "starts": int(minutes >= 60),
                         "minutes_r5": float(minutes),
                         "starts_r5": float(minutes >= 60),
                         "home": 1.0})
    return pd.DataFrame(rows)


_FIT_COLS = ["minutes_r5", "starts_r5", "home"]


def test_the_fitter_holds_out_the_last_slots_and_fits_on_them(monkeypatch):
    import gaffer.models.dnp_calibrate as dc

    seen = {}
    real = dc.DnpCalibrator.fit

    def spy(self, p_dnp, is_dnp):
        seen["rows"] = len(np.asarray(p_dnp))
        return real(self, p_dnp, is_dnp)

    monkeypatch.setattr(dc.DnpCalibrator, "fit", spy)
    monkeypatch.setattr(dc, "DNP_MIN_ROWS", 10)
    dc.fit_dnp_calibrator(_slotted(), _FIT_COLS, holdout_slots=10)
    # 80 codes x the last 10 of 30 slots.
    assert seen["rows"] == 800


def test_the_inner_model_never_sees_a_held_out_slot(monkeypatch):
    """Spec §7's walk-forward-leakage rail: the model that produces the
    predictions the calibrator learns from must be fit strictly before them."""
    import gaffer.models.dnp_calibrate as dc
    from gaffer.models.minutes import ThreeModeModel

    seen = {}
    real = ThreeModeModel.fit

    def spy(self, df):
        seen["max_gw"] = int(df["gw"].max())
        return real(self, df)

    monkeypatch.setattr(ThreeModeModel, "fit", spy)
    monkeypatch.setattr(dc, "DNP_MIN_ROWS", 10)
    dc.fit_dnp_calibrator(_slotted(), _FIT_COLS, holdout_slots=10)
    assert seen["max_gw"] == 20        # slots 21-30 are the holdout


def test_a_frame_with_too_few_slots_returns_the_identity():
    from gaffer.models.dnp_calibrate import fit_dnp_calibrator

    thin = _slotted(n_codes=80, n_gws=8)
    assert fit_dnp_calibrator(thin, _FIT_COLS, holdout_slots=10).iso is None


def test_the_fitter_does_not_recurse_into_itself(monkeypatch):
    """The inner ThreeModeModel must be built with the recursion guard, or
    fitting one calibrator would fit an unbounded tower of them."""
    import gaffer.models.dnp_calibrate as dc
    from gaffer.models.minutes import ThreeModeModel

    built = []
    real = ThreeModeModel.__init__

    def spy(self, feature_cols, *args, **kw):
        built.append(kw.get("_fit_dnp", True))
        return real(self, feature_cols, *args, **kw)

    monkeypatch.setattr(ThreeModeModel, "__init__", spy)
    monkeypatch.setattr(dc, "DNP_MIN_ROWS", 10)
    dc.fit_dnp_calibrator(_slotted(), _FIT_COLS, holdout_slots=10)
    assert built == [False]
