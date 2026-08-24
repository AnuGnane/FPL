"""Milestone: model quality vs naive baselines on held-out 2025-26 GW30-38.

Trains every component on everything strictly before 2025-26 GW30, then
scores the model's expected points against two baselines a human would
actually use — last-5-gameweek average and season-to-date average — on the
same held-out rows. The held-out feature rows are built from the full frame
on purpose: at GW35 the tool really does know GW30-34, and the models
themselves never saw a row from GW30 onwards during fitting.
"""

from gaffer.assets import load_bootstrap_sample
from gaffer.data.bootstrap import scoring_table
from gaffer.models.assemble import assemble_ep, ep_matrix
from gaffer.models.components import card_penalty
from gaffer.models.train import (evaluate_predictions, load_training_frame,
                                 train_all)

HOLDOUT_SEASON, HOLDOUT_FROM = 3, 30      # season_idx 3 = 2025-26

df_full, tg_full, elo_final = load_training_frame()
train_df = df_full[(df_full.season_idx < HOLDOUT_SEASON) |
                   ((df_full.season_idx == HOLDOUT_SEASON) &
                    (df_full.gw < HOLDOUT_FROM))]
train_tg = tg_full[(tg_full.season_idx < HOLDOUT_SEASON) |
                   ((tg_full.season_idx == HOLDOUT_SEASON) &
                    (tg_full.gw < HOLDOUT_FROM))]
models = train_all(train_df, train_tg, save=False)

holdout = df_full[(df_full.season_idx == HOLDOUT_SEASON) &
                  (df_full.gw >= HOLDOUT_FROM)].reset_index(drop=True)
mp = models["minutes"].predict(holdout)
ap = models["attacking"].predict(holdout)
dp = models["defcon"].predict(holdout)
sp = models["saves"].predict(holdout)
bp = models["bonus"].predict(holdout)
tg_holdout = tg_full[(tg_full.season_idx == HOLDOUT_SEASON) &
                     (tg_full.gw >= HOLDOUT_FROM)].dropna(subset=["elo_diff"])
tp = models["team"].predict(tg_holdout)
tp["opp_code"] = tg_holdout["opp_code"].values

# Positional assembly, not a merge: (code, season_idx, gw) is not unique in a
# double gameweek — player_gw holds one row per player-MATCH — so merging the
# per-player predictions would fan each DGW pair out to n**2 rows. Every
# predict() returns one row per input row in input order, so column copies are
# exact. The team merge is genuinely many-to-one and stays a merge.
keys = ["code", "season_idx", "gw"]
comp = holdout[keys + ["position", "team_code", "opp_code"]].copy()
comp["p_play"] = mp["p_play"].values
comp["p60"] = mp["p60"].values
comp["e_goals"] = ap["e_goals"].values
comp["e_assists"] = ap["e_assists"].values
comp["p_defcon"] = dp["p_defcon"].values
comp["e_saves"] = sp["e_saves"].values
comp["e_bonus"] = bp["e_bonus"].values
# opp_code is part of the join key so a double gameweek's two fixtures match
# the right team prediction each: (team_code, gw) alone is not unique there.
comp = comp.merge(tp.rename(columns={"code": "team_code"}),
                  on=["team_code", "season_idx", "gw", "opp_code"], how="left",
                  validate="many_to_one")
comp["p_cs"] = comp["p_cs"].fillna(0.25)
comp["e_gc"] = comp["e_gc"].fillna(1.4)
comp["e_cards"] = holdout.apply(card_penalty, axis=1).values
scoring = scoring_table(load_bootstrap_sample())
ep = ep_matrix(assemble_ep(comp, scoring))

# One truth row per player-gameweek, matching ep_matrix's DGW summing. Left
# per-fixture, a double gameweek would score the model's summed ep twice
# against half its points while the per-fixture baselines went unpenalised.
truth = holdout.groupby(["code", "gw"], as_index=False).agg(
    total_points=("total_points", "sum"), minutes=("minutes", "sum"))


def baseline(col: str):
    """Naive predictor from a rolling column, one row per player-gameweek.

    A baseline carries one value per match, and a DGW's two matches share a
    near-identical rolling average, so taking the first is fine.
    """
    b = holdout[["code", "gw", col]].rename(columns={col: "ep"}).dropna()
    return b.groupby(["code", "gw"], as_index=False).agg(ep=("ep", "first"))


print("MODEL   :", evaluate_predictions(ep, truth))
print("LAST-5  :", evaluate_predictions(baseline("total_points_r5"), truth))
print("SEASON  :", evaluate_predictions(baseline("total_points_r38"), truth))
