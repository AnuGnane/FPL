"""Minutes model: P(plays), P(60+ minutes), E[minutes].

Minutes are the gap between free and paid FPL tools, so this gets three
heads rather than one regression: appearance points key off ``p_play``
and ``p60`` separately, and attacking rates are scaled by ``p_play``.
"""

from __future__ import annotations

import pandas as pd
from lightgbm import LGBMClassifier, LGBMRegressor

LGB_KW = dict(n_estimators=300, learning_rate=0.05, num_leaves=31,
              verbose=-1, random_state=7)


class MinutesModel:
    """P(plays), P(60+ minutes), E[minutes]. Trained on historical rows;
    live availability (status / chance_of_playing) is applied as a hard
    override at predict time via apply_availability(), never as a trained
    feature (it doesn't exist historically -> train/serve skew)."""

    def __init__(self, feature_cols: list[str]):
        self.feature_cols = feature_cols
        self.play_clf = LGBMClassifier(**LGB_KW)
        self.sixty_clf = LGBMClassifier(**LGB_KW)
        self.min_reg = LGBMRegressor(**LGB_KW)

    def fit(self, df: pd.DataFrame) -> "MinutesModel":
        X = df[self.feature_cols]
        self.play_clf.fit(X, (df["minutes"] > 0).astype(int))
        self.sixty_clf.fit(X, (df["minutes"] >= 60).astype(int))
        self.min_reg.fit(X, df["minutes"])
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """One row per input row: code, season_idx, gw, p_play, p60, e_min.

        The two classifiers are fit independently, so p60 is clipped to
        p_play — an incoherent p60 > p_play would inflate appearance
        points downstream.
        """
        X = df[self.feature_cols]
        out = df[["code", "season_idx", "gw"]].copy()
        out["p_play"] = self.play_clf.predict_proba(X)[:, 1]
        out["p60"] = self.sixty_clf.predict_proba(X)[:, 1].clip(0, 1)
        out["p60"] = out[["p60", "p_play"]].min(axis=1)
        out["e_min"] = self.min_reg.predict(X).clip(0, 90)
        return out


def apply_availability(pred: pd.DataFrame, avail: pd.DataFrame) -> pd.DataFrame:
    """avail: code, status, chance_of_playing (from live bootstrap).
    status i/s/u/n (injured/suspended/unavailable/not in squad) -> factor from
    chance_of_playing (None means 0). 'd' (doubtful) -> chance_of_playing.
    'a' -> 1.0."""
    out = pred.merge(avail, on="code", how="left")
    cop = out["chance_of_playing"].astype("float") / 100.0
    factor = pd.Series(1.0, index=out.index)
    flagged = out["status"].isin(["i", "s", "u", "n", "d"])
    factor[flagged] = cop[flagged].fillna(0.0)
    for col in ["p_play", "p60"]:
        out[col] = out[col] * factor
    out["e_min"] = out["e_min"] * factor
    return out.drop(columns=["status", "chance_of_playing"])
