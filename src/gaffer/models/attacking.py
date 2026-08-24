"""Attacking models: E[goals] and E[assists] per appearance.

Trained per position group on rows with ``minutes > 0``, so the outputs are
per-appearance rates rather than per-fixture expectations; assembly (Task 14)
multiplies them by ``p_play`` from the minutes model and by the per-position
goal/assist points from the scoring table.

GKP and DEF share a group (both rare scorers with a similar profile); MID and
FWD each get their own.
"""

from __future__ import annotations

import pandas as pd
from lightgbm import LGBMRegressor

from gaffer.models.minutes import LGB_KW

ATTACK_FEATURES = [
    "xg_r1", "xg_r3", "xg_r5", "xg_r10", "xg_r38",
    "xa_r1", "xa_r3", "xa_r5", "xa_r10", "xa_r38",
    "xgi_r5", "xgi_r10", "goals_r5", "goals_r38", "assists_r5", "assists_r38",
    "bps_r5", "minutes_r5", "starts_r5",
    "team_elo", "opp_elo", "elo_diff", "home", "days_rest",
    # Defenders take corners, so every position group gets these.
    "pen_taker", "setpiece_taker",
]


class AttackingModel:
    """One goals + one assists regressor per position group, trained on
    appearances only (minutes > 0)."""

    def __init__(self, feature_cols: list[str] = ATTACK_FEATURES):
        self.feature_cols = feature_cols
        self.models: dict[tuple[str, str], LGBMRegressor] = {}

    def _groups(self, df: pd.DataFrame):
        yield "GKP_DEF", df[df["position"].isin(["GKP", "DEF"])]
        yield "MID", df[df["position"] == "MID"]
        yield "FWD", df[df["position"] == "FWD"]

    def fit(self, df: pd.DataFrame) -> "AttackingModel":
        played = df[df["minutes"] > 0]
        self.cols_ = [c for c in self.feature_cols if c in df.columns]
        for grp, sub in self._groups(played):
            # Tiny backtest slices can lack a whole position group; skip it
            # and let predict fall back to 0.0 for those rows.
            if sub.empty:
                continue
            for target in ("goals", "assists"):
                model = LGBMRegressor(**LGB_KW)
                model.fit(sub[self.cols_], sub[target])
                self.models[(grp, target)] = model
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.reset_index(drop=True)
        out = df[["code", "season_idx", "gw"]].copy()
        out["e_goals"] = 0.0
        out["e_assists"] = 0.0
        for grp, sub in self._groups(df):
            if sub.empty:
                continue
            for target, col in (("goals", "e_goals"), ("assists", "e_assists")):
                model = self.models.get((grp, target))
                if model is None:
                    continue
                pred = model.predict(sub[self.cols_])
                out.loc[sub.index, col] = pred.clip(0, None)
        return out
