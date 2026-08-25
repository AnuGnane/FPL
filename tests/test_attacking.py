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


def test_attacking_model_handles_all_nan_setpiece_features():
    """pen_taker/setpiece_taker are NaN for every history row until live
    snapshots accumulate; LightGBM must train and predict through that."""
    df = _frame()
    df["pen_taker"] = np.nan
    df["setpiece_taker"] = np.nan
    m = AttackingModel(feature_cols=["xg_r5", "xa_r5", "minutes_r5",
                                     "pen_taker", "setpiece_taker"])
    m.fit(df[df.gw <= 30])
    assert "pen_taker" in m.cols_ and "setpiece_taker" in m.cols_
    pred = m.predict(df[df.gw > 30])
    assert (pred["e_goals"] >= 0).all()
    assert pred["e_goals"].notna().all()


def test_attack_features_include_setpiece_columns():
    from gaffer.models.attacking import ATTACK_FEATURES
    assert "pen_taker" in ATTACK_FEATURES
    assert "setpiece_taker" in ATTACK_FEATURES


def test_attack_features_carry_the_understat_and_shrunken_blocks():
    from gaffer.features.engineer import (SHRUNK_FEATURES, TEAM_US_FEATURES,
                                          understat_feature_columns)
    from gaffer.models.attacking import ATTACK_FEATURES

    cols = set(ATTACK_FEATURES)
    assert set(understat_feature_columns()) <= cols
    assert set(SHRUNK_FEATURES) <= cols
    assert {"opp_us_xga_r5", "opp_ppda_r5"} <= cols
    # FPL's own xg/xa stay: Understat is the marginal signal, not a
    # replacement for the expected-stats the feed already gives us.
    assert "xg_r5" in cols and "xa_r5" in cols


def test_saves_features_carry_the_opponent_team_understat_block():
    from gaffer.models.components import SAVES_FEATURES

    assert {"opp_us_xga_r5", "opp_us_xga_r38"} <= set(SAVES_FEATURES)


def test_attacking_model_fits_with_the_new_columns_all_nan():
    """The degradation rail at the model level: no Understat data means the
    columns are present and empty, and LightGBM must simply ignore them."""
    import numpy as np
    import pandas as pd

    from gaffer.models.attacking import ATTACK_FEATURES, AttackingModel

    rng = np.random.default_rng(0)
    rows = []
    for i in range(200):
        rows.append({"code": 100 + i % 10, "season_idx": 0, "gw": 1 + i % 20,
                     "position": "MID", "minutes": 90,
                     "goals": int(rng.random() < 0.2),
                     "assists": int(rng.random() < 0.2),
                     "xg_r5": rng.random(), "xa_r5": rng.random()})
    df = pd.DataFrame(rows)
    for col in ATTACK_FEATURES:
        if col not in df.columns:
            df[col] = float("nan")
    model = AttackingModel().fit(df)
    out = model.predict(df)
    assert out["e_goals"].notna().all()
