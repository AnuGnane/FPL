"""The v7-model degradation rails.

Four things are pinned here; Task 7 adds the seed rail and Task 18's flip is
the only thing allowed to change rail 2:

1. With ``DNP_CALIBRATION_DEFAULT`` forced off, ``ThreeModeModel`` fits no
   calibrator, pays for no inner refit, and predicts byte-identically.
2. The constant is on — flipped by explicit user decision on 2026-08-30,
   accepting Z1's across-the-board improvement over its missed 2% bar.
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

def test_the_flag_off_fits_no_calibrator(monkeypatch):
    import gaffer.models.minutes as mn

    monkeypatch.setattr(mn, "DNP_CALIBRATION_DEFAULT", False)
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

    monkeypatch.setattr(mn, "DNP_CALIBRATION_DEFAULT", False)
    monkeypatch.setattr(mn, "fit_dnp_calibrator", boom)
    ThreeModeModel(_COLS).fit(_frame())


# --- rail 2: the shipping default has not moved --------------------------

def test_the_dnp_calibration_is_on_by_default():
    """Flipped on by explicit user decision, 2026-08-30: gate Z1 missed its
    2% zeros bar but improved every stratum, and the user accepted that
    Pareto reading over the pre-registered verdict."""
    import gaffer.models.minutes as mn

    assert mn.DNP_CALIBRATION_DEFAULT is True


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


def test_the_s2_driver_is_committed_and_uses_the_shipping_path():
    """The gate must measure what shipping would do: the estimation arm flips
    CALIBRATED_NOISE_DEFAULT and stubs the loader, which is exactly what Task
    18 does permanently — not a bespoke table= thread the live path lacks."""
    from pathlib import Path

    src = Path("scripts/s2_replay.py").read_text()
    assert "CALIBRATED_NOISE_DEFAULT" in src
    assert "load_scenario_noise" in src
    assert "scenario_noise.cache_clear()" in src
    assert "S2_ARM_DONE" in src
    assert "20260827 + gw" in src          # the S1 seed, unchanged
    assert "n=40" in src
    # Per-arm log: two concurrent arms must not race on the one parquet
    # run_backtest hard-codes, or each would report the other's hits.
    assert "backtest_log_s2_" in src
    assert 'pd.read_parquet("data/live/backtest_log.parquet")' not in src


# --- the serving rail: only the estimation table may be served -------------


def test_a_residual_table_is_refused_with_the_flag_on(monkeypatch, capsys):
    """The flag means "serve the estimation sigma", not "serve whatever JSON
    is at that path". v6's residual table is a differently-scaled quantity
    (sigma ~2-5 against ~0.02-0.3) and gate S1 measured it losing 24 points,
    so a stale or hand-restored residual asset must degrade to the heuristic
    rather than quietly reinstate the failed arm."""
    import gaffer.optimize.scenarios as sc

    residual = {"source": "residual", "global": 1.953,
                "ep_edges": [0.0, 2.0], "xmins_edges": [0.0, 30.0],
                "sigma": {"0_0": 2.1}}
    monkeypatch.setattr(sc, "CALIBRATED_NOISE_DEFAULT", True)
    monkeypatch.setattr(sc, "load_scenario_noise", lambda: residual)
    sc.scenario_noise.cache_clear()
    try:
        assert sc.scenario_noise() is None
        out = capsys.readouterr().out
        assert "residual" in out and "estimation" in out
    finally:
        sc.scenario_noise.cache_clear()


def test_the_estimation_table_is_still_served(monkeypatch):
    """The guard is a source check, not a new off switch."""
    import gaffer.optimize.scenarios as sc

    payload = {"source": "estimation", "global": 0.0692,
               "ep_edges": [0.0, 2.0], "xmins_edges": [0.0, 30.0],
               "sigma": {"0_0": 0.018}}
    monkeypatch.setattr(sc, "CALIBRATED_NOISE_DEFAULT", True)
    monkeypatch.setattr(sc, "load_scenario_noise", lambda: payload)
    sc.scenario_noise.cache_clear()
    try:
        assert sc.scenario_noise() is payload
    finally:
        sc.scenario_noise.cache_clear()
