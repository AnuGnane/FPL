"""Train every component from the stored history, and score predictions.

One entry point builds the feature frames (``load_training_frame``) and one
fits every model over them (``train_all``), so the weekly refit and a
backtest run through identical code — the only difference is the
truncation arguments. ``evaluate_predictions`` is deliberately model-free:
it takes ``[code, gw, ep]`` from anywhere, which is what lets the milestone
script score naive baselines on exactly the same yardstick as the model.
"""

from __future__ import annotations

import pandas as pd

from gaffer.data import store
from gaffer.data.elo import compute_elo
from gaffer.features.engineer import add_context, add_player_rolling
from gaffer.models.attacking import ATTACK_FEATURES, AttackingModel
from gaffer.models.components import BonusModel, DefconModel, SavesModel
from gaffer.models.minutes import MinutesModel
from gaffer.models.persistence import save_model
from gaffer.models.team import (TEAM_FEATURES, TeamModel, add_team_rolling,
                                build_team_gw)

MINUTES_FEATURES = ["minutes_r1", "minutes_r3", "minutes_r5", "minutes_r10",
                    "starts_r1", "starts_r3", "starts_r5", "starts_r10",
                    "days_rest", "home"]


def load_training_frame(max_season_idx: int | None = None,
                        max_gw: int | None = None
                        ) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """player_gw history (+ live season appended if present) with features,
    plus team_gw with features and final elo map. Optionally truncated for
    backtesting (strictly before max_season_idx/max_gw)."""
    player_gw = store.load("history/player_gw.parquet")
    fixtures = store.load("history/fixtures.parquet")
    if store.exists("live/player_gw.parquet"):
        live = store.load("live/player_gw.parquet")
        live["season_idx"] = player_gw["season_idx"].max() + 1
        player_gw = pd.concat([player_gw, live], ignore_index=True)
    if store.exists("live/fixtures.parquet"):
        lfx = store.load("live/fixtures.parquet")
        fixtures = pd.concat([fixtures, lfx], ignore_index=True)
    if max_season_idx is not None:
        keep = (player_gw["season_idx"] < max_season_idx) | (
            (player_gw["season_idx"] == max_season_idx)
            & (player_gw["gw"] < (max_gw or 99)))
        player_gw = player_gw[keep]
        fixtures = fixtures[(fixtures["season_idx"] < max_season_idx) | (
            (fixtures["season_idx"] == max_season_idx)
            & (fixtures["gw"] < (max_gw or 99)))]

    elo = compute_elo(fixtures)
    elo_final = elo.attrs["final"]
    df = add_player_rolling(player_gw)
    df = add_context(df, elo, elo_final)
    tg = add_team_rolling(build_team_gw(fixtures))
    own = elo.rename(columns={"elo_pre": "team_elo_own"})
    tg = tg.merge(own, on=["season_idx", "gw", "code"], how="left")
    opp = elo.rename(columns={"code": "opp_code", "elo_pre": "opp_elo"})
    tg = tg.merge(opp, on=["season_idx", "gw", "opp_code"], how="left")
    tg["elo_diff"] = tg["team_elo_own"] - tg["opp_elo"]
    return df, tg, elo_final


def train_all(df: pd.DataFrame, tg: pd.DataFrame, save: bool = True) -> dict:
    """Fit every component on the given frames.

    ``BonusModel`` is pinned to the newest season present because BPS was
    rebalanced; on a truncated backtest frame that is the newest season the
    backtest is allowed to see, not the newest on disk.
    """
    minutes = MinutesModel(MINUTES_FEATURES).fit(df)
    team = TeamModel(TEAM_FEATURES).fit(tg.dropna(subset=["elo_diff"]))
    attacking = AttackingModel(ATTACK_FEATURES).fit(df)
    defcon = DefconModel().fit(df)
    saves = SavesModel().fit(df)
    bonus = BonusModel(min_season_idx=int(df["season_idx"].max())).fit(df)
    models = {"minutes": minutes, "team": team, "attacking": attacking,
              "defcon": defcon, "saves": saves, "bonus": bonus}
    if save:
        for name, m in models.items():
            save_model(m, name, meta={"rows": len(df)})
    return models


def evaluate_predictions(pred: pd.DataFrame, truth: pd.DataFrame) -> dict:
    """pred: [code, gw, ep]; truth: [code, gw, total_points, minutes].

    ``mae_starters`` is the headline: MAE over every row is dominated by
    non-playing squad filler that any model gets right, so it flatters
    everything. ``captain_pts`` and ``top15_pts`` measure the decision the
    tool actually makes — the ranking — rather than the calibration.
    """
    j = pred.merge(truth, on=["code", "gw"], how="inner")
    starters = j[j["minutes"] >= 60]
    err = (j["ep"] - j["total_points"]).abs()
    err_st = (starters["ep"] - starters["total_points"]).abs()
    cap = (j.sort_values("ep", ascending=False).groupby("gw").head(1))
    top15 = (j.sort_values("ep", ascending=False).groupby("gw").head(15))
    return {
        "mae_all": round(float(err.mean()), 3),
        "mae_starters": round(float(err_st.mean()), 3),
        "rmse_starters": round(float(((starters["ep"] - starters["total_points"]) ** 2)
                                     .mean() ** 0.5), 3),
        "captain_pts": round(float(cap["total_points"].mean()), 2),
        "top15_pts": round(float(top15.groupby("gw")["total_points"].sum().mean()), 1),
        "n": len(j),
    }
