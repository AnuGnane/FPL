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


# Game rules, not exposed anywhere in the API: a defender scores the
# defensive contribution on 10+ CBIT (clearances, blocks, interceptions,
# tackles); a midfielder or forward needs 12+ CBIRT, which adds recoveries.
DEF_CBIT_THRESHOLD = 10
MID_FWD_CBIRT_THRESHOLD = 12

# Fallback rate when no row carries the component stats at all — the measured
# threshold-hit rate over real 2025/26 outfield appearances. A frame from
# before 2025/26 has no defcon signal to learn from, and a flat prior is
# honest about that where a crash or a hard zero would not be.
DEFCON_PRIOR = 0.13


def defcon_target(df: pd.DataFrame) -> pd.Series:
    """Did each row hit its position's defensive-contribution threshold?

    The stored ``defcon`` column is a raw action *count*, not a flag, so the
    threshold has to be applied here from the component stats. Rows whose
    components are missing (pre-2025/26, where these stats did not exist)
    come back 0 and are excluded from training by ``fit``, never trained on
    as negatives.
    """
    cbit = df["tackles"].fillna(0) + df["cbi"].fillna(0)
    cbirt = cbit + df["recoveries"].fillna(0)
    hit = (df["position"] == "DEF").where(df["position"].notna(), False)
    return (hit & (cbit >= DEF_CBIT_THRESHOLD)
            | ~hit & (cbirt >= MID_FWD_CBIRT_THRESHOLD)).astype(int)


class DefconModel:
    """P(defensive-contribution threshold hit). Trained only on rows where the
    component stats exist (2025/26 onwards); older rows lack them entirely."""

    def __init__(self, feature_cols: list[str] = DEFCON_FEATURES):
        self.feature_cols = feature_cols
        self.clf = LGBMClassifier(**LGB_KW)

    def fit(self, df: pd.DataFrame) -> "DefconModel":
        sub = df[(df["minutes"] > 0) & df["tackles"].notna()
                 & df["cbi"].notna() & (df["position"] != "GKP")]
        self.cols_ = [c for c in self.feature_cols if c in sub.columns]
        # No row carries the component stats (a frame entirely before
        # 2025/26, which the calibration refit can hand us). LightGBM raises
        # on an empty design matrix, so fall back to the flat prior.
        self.constant_ = DEFCON_PRIOR if sub.empty else None
        if self.constant_ is None:
            self.clf.fit(sub[self.cols_], defcon_target(sub))
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df[["code", "season_idx", "gw"]].copy()
        if getattr(self, "constant_", None) is not None:
            out["p_defcon"] = self.constant_
        else:
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
    """E[bonus] per appearance, trained on the newest seasons only.

    The floor survives the 2026/27 re-derivation on purpose:
    :func:`gaffer.features.bps.apply_new_bps` can only restate seasons that
    carry ``cbi`` counts (2025-26 onward), and nothing records how often a
    player was tackled, so older seasons keep an old-rules bonus target.
    :func:`gaffer.models.train.bonus_season_floor` picks the newest window
    with enough rows to fit on — which is exactly the restated-or-new part
    of the history.
    """

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
