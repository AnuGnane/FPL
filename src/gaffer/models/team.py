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
from gaffer.models.persistence import load_params, params_exist

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
the model's own output.

0.7 was a guess. It is now only the *fallback*: with historical closing odds
on disk, :func:`fit_blend_weight` estimates the weight by log loss on
walk-forward predictions and :func:`odds_blend_weight` serves the fitted value
instead. The constant still applies wherever there is no artifact — a fresh
clone, or a train that never saw a football-data file. It leans on the market
(which prices team news the rolling features cannot see) while keeping the
model as a floor for fixtures the feed misprices or covers thinly.
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


def blend_team_odds(team_preds: pd.DataFrame,
                    weight: float | None = None) -> pd.DataFrame:
    """Blend market odds into team predictions where odds exist.

    ``p_cs``: independent-Poisson P(concede 0) = ``exp(-mu_against)``, the
    same independence assumption ``invert_odds`` used to recover the mus, so
    the two ends of the odds path agree.

    ``weight`` defaults to :func:`odds_blend_weight` — the value fitted at
    train time on historical closing odds and stored in the artifact bundle,
    falling back to :data:`ODDS_BLEND_WEIGHT` when no artifact exists. Pass it
    explicitly to pin a number, which is what the tests and the explainability
    path do.

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
    w = odds_blend_weight() if weight is None else float(weight)
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


BLEND_PARAMS_NAME = "blend"
BLEND_GRID_STEP = 0.01


def fit_blend_weight(frame: pd.DataFrame,
                     step: float = BLEND_GRID_STEP) -> float:
    """The convex weight on the market, fitted by log loss.

    ``frame`` is :func:`gaffer.models.dixon_coles.walk_forward_cs`'s output:
    out-of-sample ``p_cs_model``, market ``p_cs_odds`` and the realized
    ``cs``. One scalar over ``[0, 1]``, so a grid at 0.01 is both exhaustive
    and instant — no optimizer, no local minimum to worry about.

    Log loss rather than Brier or accuracy because calibration is the thing
    the number is for: the MILP multiplies this probability by points, so
    being right on average and wrong in every bin is the failure mode that
    matters. An empty or unusable frame falls back to
    :data:`ODDS_BLEND_WEIGHT`, which is exactly what it was there for.

    The winner is picked by the *one-standard-error rule*, not the raw
    argmin: among the grid, take the smallest ``w`` whose mean loss sits
    within one standard error of the best. Two reasons, both about the fit
    being a weaker guide than it looks. First, the loss curve over ``w`` is
    nearly flat near its floor, so the argmin routinely wins by a margin a
    bootstrap on the per-row loss difference cannot separate from zero —
    left alone it lands on an extreme (``w = 1``, the market alone) on
    evidence that thin. Second, and worse, the fit and the serve do not see
    the same market: the fit uses football-data's *closing average* odds
    across books, while prediction time uses a single-book snapshot taken
    before the deadline. Closing average is the sharper source, so a weight
    fitted on it overstates how much to trust what we actually serve. The
    1-SE rule spends that uncertainty on the conservative side — less
    market, more model — which is the side that degrades gracefully.
    """
    cols = ["p_cs_odds", "p_cs_model", "cs"]
    if frame is None or frame.empty or any(c not in frame for c in cols):
        return ODDS_BLEND_WEIGHT
    sub = frame[cols].apply(pd.to_numeric, errors="coerce").dropna()
    if sub.empty:
        return ODDS_BLEND_WEIGHT
    odds = sub["p_cs_odds"].to_numpy(dtype="float64")
    model = sub["p_cs_model"].to_numpy(dtype="float64")
    y = sub["cs"].to_numpy(dtype="float64")
    grid = [round(i * step, 2) for i in range(int(round(1.0 / step)) + 1)]
    # Per-row losses, kept whole: the 1-SE band needs the *paired* spread of
    # the difference against the argmin, which a mean-only sweep throws away.
    per_row = []
    for w in grid:
        p = np.clip(w * odds + (1.0 - w) * model, 1e-12, 1.0 - 1e-12)
        per_row.append(-(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))
    means = np.array([float(r.mean()) for r in per_row])
    best = int(np.argmin(means))
    n = len(y)
    if n < 2:
        return grid[best]
    for i, w in enumerate(grid):
        if i == best:
            break
        diff = per_row[i] - per_row[best]
        se = float(np.std(diff, ddof=1)) / np.sqrt(n)
        if means[i] - means[best] <= se:
            return w
    return grid[best]


def odds_blend_weight() -> float:
    """The fitted weight from the artifact bundle, else the constant.

    Read at prediction time rather than baked into the pickle so a refit of
    the weight alone is possible, and so the number is greppable on disk when
    a blended clean sheet looks wrong.
    """
    if not params_exist(BLEND_PARAMS_NAME):
        return ODDS_BLEND_WEIGHT
    stored = load_params(BLEND_PARAMS_NAME).get("odds_blend_weight")
    return ODDS_BLEND_WEIGHT if stored is None else float(stored)
