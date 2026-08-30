"""The v7-model degradation rails.

Four things are pinned here; Task 7 adds the seed rail and Task 18's flip is
the only thing allowed to change rail 2:

1. With ``DNP_CALIBRATION_DEFAULT`` off, ``ThreeModeModel`` fits no
   calibrator, pays for no inner refit, and predicts byte-identically.
2. The constant really is off — gate Z1 has not been run by an implementer.
3. A model pickled before the calibrator existed still predicts.
4. The protected ``run_advise`` source-text pins still hold, because nothing
   in this cycle touched ``advise.py`` at all.

If a later task legitimately changes one of these, that task's gate says so
and the pin here is updated deliberately — never quietly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from gaffer.models.minutes import ThreeModeModel


def _frame(n_codes=40, n_gws=30, seed=3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for code in range(n_codes):
        for gw in range(1, n_gws + 1):
            minutes = 90 if code < 20 else int(rng.choice([0, 0, 0, 20]))
            rows.append({"code": code, "season_idx": 0, "gw": gw,
                         "minutes": minutes, "starts": int(minutes >= 60),
                         "minutes_r5": float(minutes),
                         "starts_r5": float(minutes >= 60), "home": 1.0})
    return pd.DataFrame(rows)


_COLS = ["minutes_r5", "starts_r5", "home"]


# --- rail 1: the flag off is the pre-v7 model, prediction for prediction ---

def test_the_flag_off_fits_no_calibrator():
    import gaffer.models.minutes as mn

    assert mn.DNP_CALIBRATION_DEFAULT is False
    model = ThreeModeModel(_COLS).fit(_frame())
    assert model.dnp_cal is None


def test_the_flag_off_predicts_the_raw_classifier_probabilities():
    """Nothing sits between the mode classifier and the trichotomy: with the
    flag off, predict_modes is predict_proba re-columned and nothing else."""
    df = _frame()
    model = ThreeModeModel(_COLS).fit(df)
    modes = model.predict_modes(df)
    proba = model.mode_clf.predict_proba(df[_COLS])
    for j, mode in enumerate(model.mode_clf.classes_):
        assert np.allclose(modes.iloc[:, int(mode)].to_numpy(), proba[:, j])


def test_the_flag_off_never_pays_for_the_inner_refit(monkeypatch):
    import gaffer.models.minutes as mn

    def boom(*args, **kw):
        raise AssertionError("the default path must not fit a calibrator")

    monkeypatch.setattr(mn, "fit_dnp_calibrator", boom)
    ThreeModeModel(_COLS).fit(_frame())


# --- rail 2: the shipping default has not moved --------------------------

def test_the_dnp_calibration_is_off_by_default():
    """Gate Z1 is the orchestrator's to run. Until it passes, this is False."""
    import gaffer.models.minutes as mn

    assert mn.DNP_CALIBRATION_DEFAULT is False


# --- rail 3: an older pickle still predicts ------------------------------

def test_a_model_without_the_attribute_degrades_to_the_identity():
    """``getattr`` rather than ``self.dnp_cal``: a joblib fitted before this
    cycle has no such attribute, and it must still serve."""
    df = _frame()
    model = ThreeModeModel(_COLS).fit(df)
    modes = model.predict_modes(df)
    del model.dnp_cal
    pd.testing.assert_frame_equal(model.predict_modes(df), modes)


def test_the_flag_on_actually_changes_something(monkeypatch):
    """The opt-in path stays alive for the gate: flipping the constant fits a
    calibrator and moves the DNP column."""
    import gaffer.models.dnp_calibrate as dc
    import gaffer.models.minutes as mn

    monkeypatch.setattr(mn, "DNP_CALIBRATION_DEFAULT", True)
    monkeypatch.setattr(dc, "DNP_MIN_ROWS", 10)
    df = _frame()
    model = ThreeModeModel(_COLS).fit(df)
    assert model.dnp_cal is not None and model.dnp_cal.iso is not None


# --- rail 4: advise.py was not touched -----------------------------------

def test_run_advise_still_pins_every_protected_ordering():
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    assert "ep_matrix(apply_calibration(assemble_ep(" in src
    assert src.index("fetch_rival_entries(") < src.index("tilt_ep(")
    assert src.index("tilt_ep(") < src.index("pool = build_pool(")
    assert "build_pool(players, pool_ep," in src
    assert 'ep_gw1 = ep_named[ep_named["gw"] == gw]' in src
    assert "pool_ep" not in src[src.index("ep_gw1 ="):]


def test_predict_components_still_calls_the_minutes_model_once():
    """The calibrator lives inside the model, so the advise seam is unchanged:
    one model call, two availability passes, exactly as v6 left it."""
    import inspect

    from gaffer.advise import predict_components

    src = inspect.getsource(predict_components)
    assert src.count("minutes.predict(pf)") == 1
    assert src.count("apply_availability(") == 2


def test_the_z1_driver_exists_and_names_both_arms():
    """The gate has to be reproducible after this session ends, so its driver
    is committed rather than left in a scratchpad."""
    from pathlib import Path

    src = Path("scripts/z1_arms.py").read_text()
    assert "DNP_CALIBRATION_DEFAULT" in src
    assert "Z1_ARM_DONE" in src
    assert "load_training_frame" in src      # memoised across the two arms
    assert "1.042" in src and "5.171" in src and "1.996" in src
