import numpy as np
import pandas as pd
from gaffer.models.minutes import MinutesModel, apply_availability
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


def test_minutes_model_separates_starters_from_fringe():
    df = add_player_rolling(_training_frame(), stats=["minutes", "starts"],
                            windows=[3, 5])
    df["home"] = 1.0
    train = df[df.gw <= 15]
    m = MinutesModel(feature_cols=["minutes_r3", "minutes_r5",
                                   "starts_r3", "starts_r5", "home"])
    m.fit(train)
    pred = m.predict(df[df.gw > 15])
    starters = pred[pred.code < 10]
    fringe = pred[pred.code >= 10]
    assert starters["p_play"].mean() > 0.8
    assert fringe["p_play"].mean() < 0.4
    assert ((pred["p60"] <= pred["p_play"] + 1e-9)).all()


def test_availability_override_zeroes_injured():
    pred = pd.DataFrame({"code": [1, 2], "p_play": [0.9, 0.9],
                         "p60": [0.8, 0.8], "e_min": [80.0, 80.0]})
    avail = pd.DataFrame({"code": [1, 2], "status": ["i", "d"],
                          "chance_of_playing": [None, 50]})
    out = apply_availability(pred, avail)
    assert out.loc[out.code == 1, "p_play"].iloc[0] == 0.0
    assert abs(out.loc[out.code == 2, "p_play"].iloc[0] - 0.45) < 1e-9


def test_saved_model_round_trips_identical_predictions(tmp_path, monkeypatch):
    from gaffer.models import persistence

    monkeypatch.setattr(persistence, "MODELS_DIR", tmp_path)
    df = add_player_rolling(_training_frame(), stats=["minutes", "starts"],
                            windows=[3, 5])
    df["home"] = 1.0
    m = MinutesModel(feature_cols=["minutes_r3", "minutes_r5",
                                   "starts_r3", "starts_r5", "home"])
    m.fit(df[df.gw <= 15])
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
