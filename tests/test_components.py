import numpy as np
import pandas as pd
from gaffer.models.components import (DEF_CBIT_THRESHOLD,
                                      MID_FWD_CBIRT_THRESHOLD, BonusModel,
                                      DefconModel, SavesModel, card_penalty,
                                      defcon_target)


def _defcon_frame(seed=3):
    """Raw per-match defensive counts, not a pre-computed flag.

    That is what the stored table actually holds, so the model has to apply
    the FPL threshold itself: a tackler's tackles+cbi clears 10 most weeks,
    a fringe defender's almost never does.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for code in range(20):
        tackler = code < 10
        for gw in range(1, 40):
            tackles = rng.integers(3, 6) if tackler else rng.integers(0, 2)
            cbi = rng.integers(5, 9) if tackler else rng.integers(0, 3)
            rows.append({
                "code": code, "season_idx": 3, "gw": gw, "position": "DEF",
                "minutes": 90, "tackles": float(tackles), "cbi": float(cbi),
                "recoveries": float(rng.integers(2, 8)),
                "tackles_r5": 3.0 if tackler else 0.5,
                "cbi_r5": 6.0 if tackler else 1.0, "recoveries_r5": 5.0,
                "minutes_r5": 90.0,
            })
    return pd.DataFrame(rows)


def test_defcon_target_applies_position_thresholds():
    df = _defcon_frame()
    df["position"] = ["DEF" if i % 2 else "MID" for i in range(len(df))]
    target = defcon_target(df)
    cbit = df["tackles"] + df["cbi"]
    is_def = df["position"] == "DEF"
    assert (target[is_def] == (cbit[is_def] >= DEF_CBIT_THRESHOLD)).all()
    cbirt = cbit + df["recoveries"]
    assert (target[~is_def] == (cbirt[~is_def] >= MID_FWD_CBIRT_THRESHOLD)).all()


def test_defcon_model_ranks_tacklers_higher():
    df = _defcon_frame()
    m = DefconModel(feature_cols=["tackles_r5", "cbi_r5", "recoveries_r5",
                                  "minutes_r5"])
    m.fit(df[df.gw <= 30])
    pred = m.predict(df[df.gw > 30])
    assert pred[pred.code < 10]["p_defcon"].mean() > \
           pred[pred.code >= 10]["p_defcon"].mean() * 2


def test_defcon_fit_ignores_rows_without_defcon_data():
    df = _defcon_frame()
    old = df.copy()
    old["season_idx"] = 2                          # pre-2025/26 rows:
    old[["tackles", "cbi", "recoveries"]] = np.nan  # the stats did not exist
    df = pd.concat([df, old], ignore_index=True)
    m = DefconModel(feature_cols=["tackles_r5", "cbi_r5", "recoveries_r5",
                                  "minutes_r5"])
    m.fit(df)     # must not raise on NaN targets
    assert (defcon_target(old) == 0).all()


def test_card_penalty():
    row = pd.Series({"yc_r38": 0.2, "rc_r38": 0.0})
    assert card_penalty(row) == -0.2


def test_card_penalty_handles_nan():
    row = pd.Series({"yc_r38": np.nan, "rc_r38": np.nan})
    assert card_penalty(row) == 0.0
