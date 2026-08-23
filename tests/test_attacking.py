import numpy as np
import pandas as pd
from gaffer.models.attacking import AttackingModel

def _frame(seed=2):
    rng = np.random.default_rng(seed)
    rows = []
    for code in range(30):
        good = code < 15          # high-xG players score more
        for gw in range(1, 40):
            xg_r5 = 0.6 if good else 0.05
            rows.append({
                "code": code, "season_idx": 0, "gw": gw, "position": "FWD",
                "minutes": 90, "xg_r5": xg_r5, "xa_r5": 0.1, "xgi_r5": xg_r5 + 0.1,
                "minutes_r5": 90.0, "elo_diff": 0.0, "home": 1.0,
                "goals": int(rng.random() < (0.55 if good else 0.05)),
                "assists": int(rng.random() < 0.1),
            })
    return pd.DataFrame(rows)

def test_attacking_model_ranks_high_xg_players_higher():
    df = _frame()
    m = AttackingModel(feature_cols=["xg_r5", "xa_r5", "xgi_r5", "minutes_r5",
                                    "elo_diff", "home"])
    m.fit(df[df.gw <= 30])
    pred = m.predict(df[df.gw > 30])
    assert pred[pred.code < 15]["e_goals"].mean() > \
           pred[pred.code >= 15]["e_goals"].mean() * 2
    assert (pred["e_goals"] >= 0).all()


def test_unfitted_position_group_predicts_zero():
    """Tiny backtest slices can lack whole position groups: fit must skip
    them and predict must return 0.0 rather than KeyError."""
    train = _frame()  # FWD only
    m = AttackingModel(feature_cols=["xg_r5", "xa_r5", "xgi_r5", "minutes_r5",
                                     "elo_diff", "home"])
    m.fit(train)
    assert ("GKP_DEF", "goals") not in m.models
    assert ("MID", "goals") not in m.models
    assert ("FWD", "goals") in m.models

    mixed = train[train.gw > 30].copy().reset_index(drop=True)
    mixed.loc[mixed.code >= 15, "position"] = "DEF"
    pred = m.predict(mixed)
    defs = pred[mixed["position"] == "DEF"]
    fwds = pred[mixed["position"] == "FWD"]
    assert (defs["e_goals"] == 0.0).all()
    assert (defs["e_assists"] == 0.0).all()
    assert (fwds["e_goals"] > 0).any()
