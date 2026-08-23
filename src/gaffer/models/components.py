"""Auxiliary scoring components: defcon, saves, bonus, cards.

Every rate here is per-appearance — trained on rows where the player
actually played — so assembly scales them by ``p_play`` from the minutes
model. The per-position points values live in the scoring table, not here:
these models only supply probabilities and expected counts.
"""

from __future__ import annotations

import pandas as pd
from lightgbm import LGBMClassifier, LGBMRegressor

from gaffer.models.minutes import LGB_KW

DEFCON_FEATURES = ["tackles_r3", "tackles_r5", "tackles_r38", "cbi_r3",
                   "cbi_r5", "cbi_r38", "recoveries_r5", "recoveries_r38",
                   "minutes_r5", "opp_elo", "home"]


class DefconModel:
    """P(defensive-contribution threshold hit). Trained only on rows where the
    defcon stat exists (2025/26 onwards); older rows have NaN targets."""

    def __init__(self, feature_cols: list[str] = DEFCON_FEATURES):
        self.feature_cols = feature_cols
        self.clf = LGBMClassifier(**LGB_KW)

    def fit(self, df: pd.DataFrame) -> "DefconModel":
        sub = df[(df["minutes"] > 0) & df["defcon"].notna()
                 & (df["position"] != "GKP")]
        self.cols_ = [c for c in self.feature_cols if c in sub.columns]
        self.clf.fit(sub[self.cols_], (sub["defcon"] > 0).astype(int))
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df[["code", "season_idx", "gw"]].copy()
        out["p_defcon"] = self.clf.predict_proba(df[self.cols_])[:, 1]
        out.loc[df["position"] == "GKP", "p_defcon"] = 0.0
        return out


SAVES_FEATURES = ["saves_r3", "saves_r5", "saves_r38", "opp_elo", "elo_diff",
                  "home"]


class SavesModel:
    """E[saves] per appearance for keepers. Outfielders get 0.0."""

    def __init__(self, feature_cols: list[str] = SAVES_FEATURES):
        self.feature_cols = feature_cols
        self.reg = LGBMRegressor(**LGB_KW)

    def fit(self, df: pd.DataFrame) -> "SavesModel":
        sub = df[(df["position"] == "GKP") & (df["minutes"] > 0)]
        self.cols_ = [c for c in self.feature_cols if c in sub.columns]
        self.reg.fit(sub[self.cols_], sub["saves"])
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df[["code", "season_idx", "gw"]].copy()
        out["e_saves"] = 0.0
        gk = df["position"] == "GKP"
        if gk.any():
            out.loc[gk, "e_saves"] = self.reg.predict(
                df.loc[gk, self.cols_]).clip(0, None)
        return out


BONUS_FEATURES = ["bps_r3", "bps_r5", "bps_r38", "xgi_r5", "bonus_r5",
                  "bonus_r38", "elo_diff", "home"]


class BonusModel:
    """E[bonus]. BPS was rebalanced for 2026/27, so train on the most recent
    season only (pass min_season_idx) and expect weekly refits to adapt."""

    def __init__(self, feature_cols: list[str] = BONUS_FEATURES,
                 min_season_idx: int = 3):
        self.feature_cols = feature_cols
        self.min_season_idx = min_season_idx
        self.reg = LGBMRegressor(**LGB_KW)

    def fit(self, df: pd.DataFrame) -> "BonusModel":
        sub = df[(df["minutes"] > 0) & (df["season_idx"] >= self.min_season_idx)
                 & df["bonus"].notna()]
        self.cols_ = [c for c in self.feature_cols if c in sub.columns]
        self.reg.fit(sub[self.cols_], sub["bonus"])
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df[["code", "season_idx", "gw"]].copy()
        out["e_bonus"] = self.reg.predict(df[self.cols_]).clip(0, 3)
        return out


def card_penalty(row: pd.Series) -> float:
    """Expected points from cards: -1 * yellow rate + -3 * red rate.

    Rates are read defensively: a missing key or a NaN (a player with no
    card history in the rolling window) counts as zero, not NaN — note that
    ``NaN or 0.0`` returns NaN, since NaN is truthy.
    """
    def _rate(key: str) -> float:
        val = row.get(key, 0.0)
        return 0.0 if pd.isna(val) else float(val)

    return -1.0 * _rate("yc_r38") - 3.0 * _rate("rc_r38")
