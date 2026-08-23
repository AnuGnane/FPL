import numpy as np
import pandas as pd
from gaffer.models.components import DefconModel, SavesModel, BonusModel, card_penalty


def _defcon_frame(seed=3):
    rng = np.random.default_rng(seed)
    rows = []
    for code in range(20):
        tackler = code < 10
        for gw in range(1, 40):
            rows.append({
                "code": code, "season_idx": 3, "gw": gw, "position": "DEF",
                "minutes": 90, "tackles_r5": 3.0 if tackler else 0.5,
                "cbi_r5": 6.0 if tackler else 1.0, "recoveries_r5": 5.0,
                "minutes_r5": 90.0, "defcon": 2 if (tackler and rng.random() < .6)
                                             else (2 if rng.random() < .05 else 0),
            })
    return pd.DataFrame(rows)


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
    df.loc[df.season_idx < 3, "defcon"] = np.nan   # pre-2025/26 rows
    m = DefconModel(feature_cols=["tackles_r5", "cbi_r5", "recoveries_r5",
                                  "minutes_r5"])
    m.fit(df)     # must not raise on NaN targets


def test_card_penalty():
    row = pd.Series({"yc_r38": 0.2, "rc_r38": 0.0})
    assert card_penalty(row) == -0.2


def test_card_penalty_handles_nan():
    row = pd.Series({"yc_r38": np.nan, "rc_r38": np.nan})
    assert card_penalty(row) == 0.0
