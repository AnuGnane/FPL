import numpy as np
import pandas as pd
from gaffer.models.minutes import ThreeModeModel, apply_availability
from gaffer.features.engineer import add_player_rolling


def _training_frame(n=400, seed=0):
    """Synthetic: regular starter codes get 90s, fringe codes get 0-20."""
    rng = np.random.default_rng(seed)
    rows = []
    for code in range(20):
        starter = code < 10
        for gw in range(1, 21):
            # Starters always feature (p_play 1.0, p60 0.8); fringe players
            # get the odd cameo (p_play 0.2). The gap has to sit clear of the
            # 0.8 / 0.4 thresholds below, or no model can pass them: a
            # calibrated classifier cannot beat the generating base rate.
            minutes = int(rng.choice([90, 90, 90, 90, 60] if starter
                                     else [0, 0, 0, 0, 20]))
            rows.append({"code": code, "season_idx": 0, "gw": gw,
                         "minutes": minutes, "starts": int(minutes >= 60),
                         "kickoff_time": None, "was_home": True})
    return pd.DataFrame(rows)


def _fitted(df, cols):
    return ThreeModeModel(feature_cols=cols).fit(df[df.gw <= 15])


_COLS = ["minutes_r3", "minutes_r5", "starts_r3", "starts_r5", "home"]


def _rolled():
    df = add_player_rolling(_training_frame(), stats=["minutes", "starts"],
                            windows=[3, 5])
    df["home"] = 1.0
    return df


def test_three_mode_model_separates_starters_from_fringe():
    df = _rolled()
    pred = _fitted(df, _COLS).predict(df[df.gw > 15])
    starters = pred[pred.code < 10]
    fringe = pred[pred.code >= 10]
    assert starters["p_play"].mean() > 0.8
    assert fringe["p_play"].mean() < 0.4


def test_predict_returns_exactly_the_old_columns_in_the_old_order():
    """Everything downstream stitches positionally off these three columns.
    predict_components_simple and advise.predict_components both read
    p_play and p60 by name off a frame keyed by (code, season_idx, gw)."""
    df = _rolled()
    pred = _fitted(df, _COLS).predict(df[df.gw > 15])
    assert list(pred.columns)[:3] == ["code", "season_idx", "gw"]
    assert {"p_play", "p60", "e_min"} <= set(pred.columns)
    assert len(pred) == len(df[df.gw > 15])


def test_the_three_modes_are_coherent_by_construction():
    """The whole reason the heads were replaced: p60 <= p_play was patched by
    a clip before, and is now arithmetic. p_play is the complement of DNP."""
    df = _rolled()
    m = _fitted(df, _COLS)
    hold = df[df.gw > 15]
    pred = m.predict(hold)
    modes = m.predict_modes(hold)
    assert np.allclose(modes[["p_dnp", "p_sub", "p_start"]].sum(axis=1), 1.0)
    assert np.allclose(pred["p_play"], modes["p_start"] + modes["p_sub"])
    assert (pred["p60"] <= pred["p_play"] + 1e-9).all()
    assert (pred["e_min"] >= 0).all() and (pred["e_min"] <= 90).all()


def test_e_min_is_the_mode_weighted_average_not_a_free_regression():
    df = _rolled()
    m = _fitted(df, _COLS)
    hold = df[df.gw > 15]
    pred = m.predict(hold)
    modes = m.predict_modes(hold)
    expected = (modes["p_start"] * m.min_start.predict(hold[_COLS])
                + modes["p_sub"] * m.min_sub.predict(hold[_COLS]))
    assert np.allclose(pred["e_min"], expected.clip(0, 90))


def test_a_degenerate_single_mode_frame_still_fits_and_predicts():
    """Early in a season, and in every small backtest window, a frame can hold
    one mode only. LGBM refuses a one-class fit, so the head has to fall back
    to the observed constant rather than taking the refit down."""
    df = _rolled()
    always = df[df.code < 10].copy()
    always["minutes"] = 90.0
    always["starts"] = 1.0
    m = ThreeModeModel(feature_cols=_COLS).fit(always)
    pred = m.predict(always)
    assert np.allclose(pred["p_play"], 1.0)
    assert np.allclose(pred["e_min"], 90.0)


def test_a_two_mode_frame_leaves_the_absent_mode_at_zero():
    """{sub, start} and no DNP: an ever-present squad in a short window. The
    mode head fits on two classes, and ``classes_`` then holds two — the
    missing DNP column must stay at zero rather than the other two shifting
    along it, which would read p_dnp off p_sub."""
    df = _rolled()
    both = df[df.code < 10].copy()
    both["minutes"] = np.where(both["gw"] % 2 == 0, 90.0, 20.0)
    both["starts"] = (both["minutes"] >= 90).astype(float)
    m = ThreeModeModel(feature_cols=_COLS).fit(both)
    assert m.modes_seen == [1, 2]
    modes = m.predict_modes(both)
    assert np.allclose(modes["p_dnp"], 0.0)
    assert np.allclose(modes["p_sub"] + modes["p_start"], 1.0)
    pred = m.predict(both)
    assert np.allclose(pred["p_play"], 1.0)
    assert (pred["e_min"] > 20.0).all() and (pred["e_min"] < 90.0).all()


def test_a_frame_with_no_appearances_at_all_predicts_zero():
    df = _rolled()
    none = df[df.code >= 10].copy()
    none["minutes"] = 0.0
    none["starts"] = 0.0
    m = ThreeModeModel(feature_cols=_COLS).fit(none)
    pred = m.predict(none)
    assert np.allclose(pred["p_play"], 0.0)
    assert np.allclose(pred["p60"], 0.0)
    assert np.allclose(pred["e_min"], 0.0)


def test_mode_labels_read_starts_not_the_60_minute_threshold():
    """A 75-minute substitute is a sub, and a starter hooked at 40 is a
    start. The old p60 head could not tell those apart at all."""
    from gaffer.models.minutes import mode_labels

    df = pd.DataFrame({"minutes": [0.0, 20.0, 75.0, 40.0, 90.0],
                       "starts": [0.0, 0.0, 0.0, 1.0, 1.0]})
    assert mode_labels(df).tolist() == [0, 1, 1, 2, 2]


def test_mode_labels_infer_a_missing_starts_column_from_minutes():
    from gaffer.models.minutes import mode_labels

    df = pd.DataFrame({"minutes": [0.0, 20.0, 75.0],
                       "starts": [float("nan")] * 3})
    assert mode_labels(df).tolist() == [0, 1, 2]


def test_saved_model_round_trips_identical_predictions(tmp_path, monkeypatch):
    from gaffer.models import persistence

    monkeypatch.setattr(persistence, "MODELS_DIR", tmp_path)
    df = _rolled()
    m = _fitted(df, _COLS)
    before = m.predict(df[df.gw > 15])

    persistence.save_model(m, "minutes", meta={"rows": int(len(df))})
    assert persistence.model_exists("minutes")
    after = persistence.load_model("minutes").predict(df[df.gw > 15])

    for col in ["p_play", "p60", "e_min"]:
        assert np.allclose(before[col].to_numpy(), after[col].to_numpy())

    import json
    meta = json.loads((tmp_path / "minutes.meta.json").read_text())
    assert "saved_at" in meta
    assert meta["rows"] == len(df)


def test_availability_override_zeroes_injured():
    pred = pd.DataFrame({"code": [1, 2], "p_play": [0.9, 0.9],
                         "p60": [0.8, 0.8], "e_min": [80.0, 80.0]})
    avail = pd.DataFrame({"code": [1, 2], "status": ["i", "d"],
                          "chance_of_playing": [None, 50]})
    out = apply_availability(pred, avail)
    assert out.loc[out.code == 1, "p_play"].iloc[0] == 0.0
    assert abs(out.loc[out.code == 2, "p_play"].iloc[0] - 0.45) < 1e-9


def test_availability_recovers_over_the_horizon():
    """A flag describes the imminent gameweek. It must bite hardest there and
    relax later, or a one-match ban zeroes a player for the whole horizon and
    the optimizer sells a fully-fit asset."""
    from gaffer.models.minutes import RECOVERY

    gws = [5, 6, 7]
    pred = pd.DataFrame({"code": [1] * 3, "gw": gws,
                         "p_play": [0.9] * 3, "p60": [0.8] * 3,
                         "e_min": [80.0] * 3})
    avail = pd.DataFrame({"code": [1], "status": ["s"],
                          "chance_of_playing": [0]})
    out = apply_availability(pred, avail).set_index("gw")

    assert out.loc[5, "p_play"] == 0.0                      # suspended now
    for h, gw in enumerate(gws):
        expected = 0.9 * (1 - (1 - 0.0) * RECOVERY ** h)
        assert abs(out.loc[gw, "p_play"] - expected) < 1e-9
    assert out.loc[7, "p_play"] > out.loc[6, "p_play"] > out.loc[5, "p_play"]
    # e_min follows the same schedule, and p60 stays under p_play.
    assert abs(out.loc[6, "e_min"] - 80.0 * (1 - RECOVERY)) < 1e-9
    assert (out["p60"] <= out["p_play"] + 1e-9).all()


def test_available_players_are_untouched_across_the_horizon():
    pred = pd.DataFrame({"code": [1, 1], "gw": [5, 6],
                         "p_play": [0.9, 0.9], "p60": [0.8, 0.8],
                         "e_min": [80.0, 80.0]})
    avail = pd.DataFrame({"code": [1], "status": ["a"],
                          "chance_of_playing": [None]})
    out = apply_availability(pred, avail)
    assert (out["p_play"] == 0.9).all() and (out["e_min"] == 80.0).all()
