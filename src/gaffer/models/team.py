"""Team model: P(clean sheet) and E[goals conceded] per team-fixture.

Defensive returns in FPL are a team property, not a player one: every
GKP/DEF/MID in the same XI shares one clean sheet. So the team side is
modelled once here and combined downstream with each player's p60 (the
CS point only lands on 60+ minutes) and the position scoring table.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier, LGBMRegressor

from gaffer.models.minutes import LGB_KW

TEAM_ROLL_STATS = ["gf", "ga", "cs"]
TEAM_WINDOWS = (5, 10, 38)

TEAM_FEATURES = ["elo_diff", "home", "team_gf_r5", "team_ga_r5", "team_cs_r10",
                 "team_gf_r38", "team_ga_r38",
                 "odds_e_goals_for", "odds_e_goals_against"]

ODDS_COLS = ["odds_e_goals_for", "odds_e_goals_against"]

ODDS_AGAINST_COL = "odds_e_goals_against"

ODDS_BLEND_WEIGHT = 0.7
"""How much of the blended team output comes from the market.

Odds cannot enter as a *feature*: bookmakers only price upcoming fixtures, so
every historical training row is NaN on the odds columns and LightGBM never
learns a split on them — a populated prediction-time value would change
nothing. They enter at prediction time instead, as a weighted blend against
the model's own output. 0.7 leans on the market (it prices team news the
rolling features cannot see) while keeping the model as a floor for fixtures
the feed misprices or covers thinly.
"""


def build_team_gw(fixtures: pd.DataFrame) -> pd.DataFrame:
    """Fixtures (one row per match) -> one row per team per match.

    Columns: season_idx, gw, kickoff_time, code, opp_code, home, gf, ga, cs.
    Every match contributes two rows, so a team's own goals-against is the
    opponent's goals-for and vice versa.
    """
    home = pd.DataFrame({
        "season_idx": fixtures["season_idx"], "gw": fixtures["gw"],
        "kickoff_time": fixtures["kickoff_time"],
        "code": fixtures["home_code"], "opp_code": fixtures["away_code"],
        "home": 1.0, "gf": fixtures["home_goals"], "ga": fixtures["away_goals"],
    })
    away = pd.DataFrame({
        "season_idx": fixtures["season_idx"], "gw": fixtures["gw"],
        "kickoff_time": fixtures["kickoff_time"],
        "code": fixtures["away_code"], "opp_code": fixtures["home_code"],
        "home": 0.0, "gf": fixtures["away_goals"], "ga": fixtures["home_goals"],
    })
    tg = pd.concat([home, away], ignore_index=True)
    tg["cs"] = (tg["ga"] == 0).astype(int)
    return tg


def add_team_rolling(tg: pd.DataFrame, stats: list[str] = TEAM_ROLL_STATS,
                     windows: tuple[int, ...] = TEAM_WINDOWS) -> pd.DataFrame:
    """Rolling team form from past matches only.

    Same leakage discipline as ``features.engineer.add_player_rolling``:
    ``shift(1)`` before the window, so a gameweek's features never see its
    own result. Built as one concat block rather than column-by-column
    inserts to avoid fragmenting the frame.
    """
    # kickoff_time breaks the tie between a double gameweek's two fixtures,
    # which otherwise share (code, season_idx, gw) and order arbitrarily.
    sort_cols = ["code", "season_idx", "gw"]
    if "kickoff_time" in tg.columns:
        sort_cols.append("kickoff_time")
    tg = tg.sort_values(sort_cols).reset_index(drop=True)
    g = tg.groupby("code", sort=False)
    feats: dict[str, pd.Series] = {}
    for stat in stats:
        shifted = g[stat].shift(1)
        for w in windows:
            feats[f"team_{stat}_r{w}"] = (
                shifted.groupby(tg["code"]).rolling(w, min_periods=1).mean()
                .reset_index(level=0, drop=True))
    return pd.concat([tg, pd.DataFrame(feats, index=tg.index)], axis=1)


def blend_team_odds(team_preds: pd.DataFrame) -> pd.DataFrame:
    """Blend market odds into team predictions where odds exist.

    ``p_cs``: independent-Poisson P(concede 0) = ``exp(-mu_against)``, the
    same independence assumption ``invert_odds`` used to recover the mus, so
    the two ends of the odds path agree.

    Rows without odds keep the pure model output — a fixture the feed did not
    cover, or a week with no API key at all, must degrade to the model rather
    than to a blend against NaN. A frame with no odds column whatsoever comes
    back untouched, so any caller that never joins odds on is safe to route
    through here.

    One row per team-fixture is assumed: apply this *before* the many-to-one
    merge onto player rows, or the blend lands once per player.
    """
    if ODDS_AGAINST_COL not in team_preds.columns:
        return team_preds
    out = team_preds.copy()
    has = out[ODDS_AGAINST_COL].notna()
    mu = out.loc[has, ODDS_AGAINST_COL].astype(float)
    w = ODDS_BLEND_WEIGHT
    out.loc[has, "p_cs"] = w * np.exp(-mu) + (1 - w) * out.loc[has, "p_cs"]
    out.loc[has, "e_gc"] = w * mu + (1 - w) * out.loc[has, "e_gc"]
    return out


class TeamModel:
    """P(clean sheet) and E[goals conceded] for a team-fixture.

    Two heads rather than one: the CS point is a threshold event
    (``ga == 0``) while the GKP/DEF ``-0.5`` per goal deduction needs the
    conditional mean, and a single regressor serves neither well.
    """

    def __init__(self, feature_cols: list[str] = TEAM_FEATURES):
        self.feature_cols = feature_cols
        self.cs_clf = LGBMClassifier(**LGB_KW)
        self.gc_reg = LGBMRegressor(**LGB_KW)

    @staticmethod
    def _with_odds(tg: pd.DataFrame) -> pd.DataFrame:
        """Guarantee the odds columns exist, as NaN when absent.

        Bookmaker odds only cover upcoming fixtures, so history frames and
        any caller predating Task 8 arrive without these columns. Filling
        them here — the one point every fit and predict passes through —
        keeps LightGBM's feature schema identical on both sides, rather
        than letting ``fit``'s intersect silently drop a feature ``predict``
        would then supply. The caller's frame is never mutated.
        """
        missing = [c for c in ODDS_COLS if c not in tg.columns]
        if not missing:
            return tg
        tg = tg.copy()
        for col in missing:
            tg[col] = float("nan")
        return tg

    def fit(self, tg: pd.DataFrame) -> "TeamModel":
        tg = self._with_odds(tg)
        # Rolling columns are absent on early frames / callers that skip
        # add_team_rolling; intersect rather than KeyError.
        cols = [c for c in self.feature_cols if c in tg.columns]
        self.cols_ = cols
        self.cs_clf.fit(tg[cols], tg["cs"])
        self.gc_reg.fit(tg[cols], tg["ga"])
        return self

    def predict(self, tg: pd.DataFrame) -> pd.DataFrame:
        """One row per input row: code, season_idx, gw, p_cs, e_gc."""
        out = tg[["code", "season_idx", "gw"]].copy()
        tg = self._with_odds(tg)
        out["p_cs"] = self.cs_clf.predict_proba(tg[self.cols_])[:, 1]
        out["e_gc"] = self.gc_reg.predict(tg[self.cols_]).clip(0, None)
        return out
