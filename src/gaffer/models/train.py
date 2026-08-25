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

from gaffer.assets import load_bootstrap_sample
from gaffer.data import store
from gaffer.data.bootstrap import scoring_table
from gaffer.data.elo import compute_elo
from gaffer.features.bps import FIRST_NEW_RULES_SEASON, apply_new_bps
from gaffer.data.understat import UNDERSTAT_PLAYER_PATH, UNDERSTAT_TEAM_PATH
from gaffer.features.engineer import (ROTATION_FEATURES, US_STATS, add_context,
                                      add_player_rolling, add_rotation,
                                      add_setpiece, add_shrunken_rates,
                                      add_understat_rolling,
                                      add_understat_team_rolling,
                                      merge_understat_team)
from gaffer.models.assemble import assemble_ep
from gaffer.models.attacking import ATTACK_FEATURES, AttackingModel
from gaffer.models.calibrate import CalibrationModel
from gaffer.models.components import (BonusModel, DefconModel, SavesModel,
                                      card_penalty)
from gaffer.models.minutes import MinutesModel
from gaffer.data.match_odds import MATCH_ODDS_PATH
from gaffer.models.persistence import save_model, save_params
from gaffer.models.dixon_coles import DixonColesModel, walk_forward_cs
from gaffer.models.team import (BLEND_PARAMS_NAME, TEAM_FEATURES, TeamModel,
                                add_team_rolling, build_team_gw,
                                fit_blend_weight)

MINUTES_FEATURES = ["minutes_r1", "minutes_r3", "minutes_r5", "minutes_r10",
                    "starts_r1", "starts_r3", "starts_r5", "starts_r10",
                    "days_rest", "home"] + ROTATION_FEATURES
"""Feature set for :class:`MinutesModel`.

The ``starts_r*`` means answer "is he a starter?" on a season-long timescale
and react to a change of role far too slowly: they blend across the season
boundary, so a player benched in the opener under a new manager still reads
like a nailed-on starter. :data:`ROTATION_FEATURES` were added to close that
gap and measured at a last-10-slot holdout: p_play log-loss 0.27703 ->
0.27322 and p60 0.26025 -> 0.25627 (paired t = -3.35 / -3.32, and the same
direction on the two earlier 10-slot windows). Downstream over the same
holdout, mae_starters 2.446 -> 2.436, 60-minute bias -0.471 -> -0.458,
captain 5.2 -> 5.9, top15 76.0 -> 74.7 (paired t = -0.67 over ten
gameweeks — noise). ``season_start_share`` lands second in the p_play
classifier's importances and the ``starts_r*`` means fall away behind it,
which is the substitution the change was after.
"""

# Team-level clean sheet / goals conceded held at league-average constants
# by the simple component path (backtest replay, calibration fitting). It
# keeps those runs to one model refit per window and removes a source of
# variance that neither of them measures.
DEFAULT_P_CS = 0.25
DEFAULT_E_GC = 1.4

# Calibration is fit on the last this-many (season_idx, gw) slots, predicted
# by components refit on everything before them. Ten slots is a compromise:
# long enough to clear CalibrationModel.MIN_ROWS per position group, short
# enough that the inner model sees nearly all of the newest season. A frame
# with no more than CALIBRATION_MIN_SLOTS slots in total cannot spare the
# holdout and gets an identity calibration instead.
CALIBRATION_HOLDOUT_GWS = 10
CALIBRATION_MIN_SLOTS = 14
# The delta is a *conditional* bias, E[actual - ep | 60+ minutes], because
# apply() scales it by p60. Same threshold the scoring uses for the 60-minute
# appearance point, and the same one evaluate_predictions calls a starter.
CALIBRATION_MIN_MINUTES = 60

BONUS_MIN_ROWS = 2000
"""Appearance rows the bonus model needs before a season stands alone.

Roughly three gameweeks of a full league, which is where the BPS signal
stops being noise.
"""


def bonus_season_floor(df: pd.DataFrame, min_rows: int = BONUS_MIN_ROWS) -> int:
    """Largest season_idx such that seasons >= it hold at least min_rows
    appearance rows (minutes > 0). Keeps BonusModel on recent-rules data
    (BPS rebalance) without starving it early in a new season.

    Pinning the floor to the newest season is right in March and disastrous
    in August: on GW2 of a new season it would fit bonus on a few hundred
    rows. Widening the window until there is enough data trades a little
    rules staleness for a model that exists.
    """
    seasons = sorted(df["season_idx"].unique(), reverse=True)
    played = df["minutes"] > 0
    for floor in seasons:
        if int(((df["season_idx"] >= floor) & played).sum()) >= min_rows:
            return int(floor)
    return int(seasons[-1])


def first_new_rules_idx(player_gw: pd.DataFrame) -> int:
    """Lowest ``season_idx`` scored under the 2026/27 BPS rules.

    The oldest stored season labelled :data:`FIRST_NEW_RULES_SEASON` or later
    if history already holds one, otherwise one past the newest stored season
    — where the live frame, itself new-rules, will land.

    This is the *rules boundary*, not the live season's index. The two agree
    only until a new-rules season is archived into history; after that the
    boundary stays on the archived season while the live frame moves on.
    """
    if "season" in player_gw.columns:
        new = player_gw[player_gw["season"].astype("string")
                        >= FIRST_NEW_RULES_SEASON]
        if not new.empty:
            return int(new["season_idx"].min())
    return int(player_gw["season_idx"].max()) + 1


def attach_understat(df: pd.DataFrame) -> pd.DataFrame:
    """Join the Understat parquets onto player rows and build their features.

    The join key is ``(code, UK match date)``: Understat carries no gameweek
    number, and a date plus a player is unique even in a double gameweek. A
    player-match with no Understat row keeps NaN stats, which LightGBM splits
    on natively — no imputation, deliberately, because "we have no shot data
    for him" is genuinely different from "he had no shots".

    With no parquet on disk at all the feature columns are still created,
    empty, so the model's schema is identical whether or not the scrape ever
    ran.
    """
    if store.exists(UNDERSTAT_PLAYER_PATH):
        us = store.load(UNDERSTAT_PLAYER_PATH)
    else:
        us = pd.DataFrame()
    if not us.empty:
        keyed = us.rename(columns={"minutes": "us_minutes"})
        keyed = keyed[["code", "date", "us_minutes"] + US_STATS]
        keyed["date"] = pd.to_datetime(keyed["date"], errors="coerce").dt.date
        keyed = keyed.drop_duplicates(subset=["code", "date"])
        df = df.copy()
        df["_date"] = pd.to_datetime(df["kickoff_time"], errors="coerce",
                                     utc=True).dt.tz_convert(
                                         "Europe/London").dt.date
        df = df.merge(keyed.rename(columns={"date": "_date"}),
                      on=["code", "_date"], how="left", validate="many_to_one")
        df = df.drop(columns=["_date"])
    df = add_understat_rolling(df)
    df = merge_understat_team(df, understat_team_rolled())
    return add_shrunken_rates(df)


def understat_team_rolled() -> pd.DataFrame | None:
    """The rolled Understat team frame, or ``None`` when there is no parquet.

    Shared by training and by ``advise``'s prediction frame, so both sides see
    the same team-level numbers.
    """
    if not store.exists(UNDERSTAT_TEAM_PATH):
        return None
    ut = store.load(UNDERSTAT_TEAM_PATH)
    return add_understat_team_rolling(ut) if not ut.empty else None


def load_training_frame(max_season_idx: int | None = None,
                        max_gw: int | None = None
                        ) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """player_gw history (+ live season appended if present) with features,
    plus team_gw with features and final elo map. Optionally truncated for
    backtesting (strictly before max_season_idx/max_gw).

    ``bps``/``bonus`` arrive restated under the 2026/27 rules (see
    :mod:`gaffer.features.bps`); the stored values survive as
    ``bps_old``/``bonus_old``.
    """
    player_gw = store.load("history/player_gw.parquet")
    fixtures = store.load("history/fixtures.parquet")
    # Two different numbers, both fixed before the concat. ``current_idx`` is
    # the index the live frame is about to be given: one past the newest
    # season on disk, always, so a live season never lands on top of an
    # archived one. ``rules_idx`` is where the 2026/27 rules start, which is
    # the archived new-rules season's own index once one exists; until then
    # history is entirely old-rules and the boundary sits one past it, so that
    # in the pre-ingestion state (no live frame yet, e.g. before the season's
    # first data_checked gameweek) the newest stored season is still restated
    # rather than mistaken for the current one. They coincide only while no
    # new-rules season has been archived.
    current_idx = int(player_gw["season_idx"].max()) + 1
    rules_idx = first_new_rules_idx(player_gw)
    if store.exists("live/player_gw.parquet"):
        live = store.load("live/player_gw.parquet")
        live["season_idx"] = current_idx
        player_gw = pd.concat([player_gw, live], ignore_index=True)
    if store.exists("live/fixtures.parquet"):
        lfx = store.load("live/fixtures.parquet")
        fixtures = pd.concat([fixtures, lfx], ignore_index=True)
    # Restate BPS and bonus under the 2026/27 rules *before* anything reads
    # them, so the bonus target and the bps_r*/bonus_r* rolling features all
    # mean one thing. Re-deriving before truncation rather than after keeps
    # every fixture's ranking whole; truncation only ever drops entire
    # gameweeks, so the two orders agree anyway.
    player_gw = apply_new_bps(player_gw, current_idx=rules_idx,
                              fixtures=fixtures)
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
    df = add_rotation(df)
    df = add_setpiece(df)
    df = add_context(df, elo, elo_final)
    df = attach_understat(df)
    tg = add_team_rolling(build_team_gw(fixtures))
    own = elo.rename(columns={"elo_pre": "team_elo_own"})
    tg = tg.merge(own, on=["season_idx", "gw", "code"], how="left")
    opp = elo.rename(columns={"code": "opp_code", "elo_pre": "opp_elo"})
    tg = tg.merge(opp, on=["season_idx", "gw", "opp_code"], how="left")
    tg["elo_diff"] = tg["team_elo_own"] - tg["opp_elo"]
    return df, tg, elo_final


def predict_components_simple(models: dict, rows: pd.DataFrame) -> pd.DataFrame:
    """Every component prediction for one gameweek's player-fixture rows.

    Stitched positionally: each ``predict`` returns one row per input row in
    input order, and a double gameweek makes ``(code, gw)`` non-unique.

    Team clean sheet / goals conceded are the constants above rather than
    the team model — see :data:`DEFAULT_P_CS`.
    """
    rows = rows.reset_index(drop=True)
    comp = rows[["code", "season_idx", "gw", "position", "team_code"]].copy()
    comp["e_cards"] = rows.apply(card_penalty, axis=1).values

    mp = models["minutes"].predict(rows)
    for col in ["p_play", "p60"]:
        comp[col] = mp[col].values
    for name, cols in (("attacking", ["e_goals", "e_assists"]),
                       ("defcon", ["p_defcon"]),
                       ("saves", ["e_saves"]),
                       ("bonus", ["e_bonus"])):
        out = models[name].predict(rows)
        for col in cols:
            comp[col] = out[col].values
    comp["p_cs"] = DEFAULT_P_CS
    comp["e_gc"] = DEFAULT_E_GC
    return comp


def fit_calibration(df: pd.DataFrame, tg: pd.DataFrame,
                    scoring: dict[str, dict[str, float]]) -> CalibrationModel:
    """Fit the EP calibration on genuinely out-of-sample predictions.

    The last :data:`CALIBRATION_HOLDOUT_GWS` gameweek slots present are held
    out: every component is refit on the rows strictly before them, those
    slots are predicted and assembled, and the calibration learns the
    assembled-ep -> actual-points map from those predictions. Fitting on
    in-sample predictions would learn the components' training-set optimism
    instead of the bias a live run actually has.

    Splitting by gameweek slot rather than by season matters for more than
    freshness. Some component stats exist only in the newest season —
    ``tackles``/``cbi`` arrived in 2025/26 — so holding out a whole season
    left :class:`DefconModel` with zero eligible rows in the inner fit and
    crashed the refit outright. A slot boundary keeps most of the newest
    season on the training side, and the inner model is one season fresher
    than a season-wise split would leave it, so the bias it is measured for
    is closer to the production model's.

    Only 60-minute appearances are used. The correction decomposes as
    ``expected bias = P(60+ minutes) * E[bias | 60+ minutes]``, and
    :meth:`CalibrationModel.apply` supplies the first factor from ``p60``,
    so what is fit here has to be the second. Fitting on every appearance
    would mix cameos into the conditional and double-count the gate.

    The inner refit assembles EP through the *simple* component path, whose
    clean sheet and goals conceded are held at the constants above rather than
    run through the team model, so the delta learned here absorbs that path's
    level error along with the components' own. ``advise`` then composes the
    delta with the real team model and the bookmaker blend. That mismatch is
    an accepted approximation, measured at gate A: the calibrated model beat
    both baselines on all five shared metrics and moved the 60-minute starter
    bias from -1.11 to -0.483.

    A frame with too few distinct slots to leave a meaningful inner training
    set returns an unfitted (identity) model.
    """
    slots = (df[["season_idx", "gw"]].drop_duplicates()
             .sort_values(["season_idx", "gw"]))
    if len(slots) <= CALIBRATION_MIN_SLOTS:
        return CalibrationModel()
    # First held-out slot; rows strictly before it train the inner model.
    bs, bg = slots.iloc[-CALIBRATION_HOLDOUT_GWS][["season_idx", "gw"]]

    def _before(f: pd.DataFrame) -> pd.Series:
        return ((f["season_idx"] < bs)
                | ((f["season_idx"] == bs) & (f["gw"] < bg)))

    before = _before(df)
    train_df, hold = df[before], df[~before]
    if train_df.empty or hold.empty:
        return CalibrationModel()

    inner = train_all(train_df, tg[_before(tg)], save=False, _fit_cal=False)
    hold = hold.reset_index(drop=True)
    comp = predict_components_simple(inner, hold)
    assembled = assemble_ep(comp, scoring)

    # ep and position both come off ``assembled``, which is row-for-row
    # ``comp``, which is row-for-row ``hold`` — so ``actual`` lines up
    # positionally. Every frame here has a fresh RangeIndex.
    started = (hold["minutes"] >= CALIBRATION_MIN_MINUTES).to_numpy()
    ep = assembled.loc[started, "ep"].reset_index(drop=True)
    position = assembled.loc[started, "position"].reset_index(drop=True)
    actual = hold.loc[started, "total_points"].reset_index(drop=True)
    return CalibrationModel().fit(ep, actual, position)


TEAM_MODEL = "dixon_coles"
"""Which class predicts team clean sheets and goals conceded.

``"dixon_coles"`` is the shipped head: one fitted scoreline distribution per
fixture, which the v4b measurement showed beats the GBM pair on CS log loss.
``"gbm"`` restores :class:`gaffer.models.team.TeamModel`, kept for one cycle
so a regression is a one-constant revert rather than an archaeology exercise.
"""


def build_team_model():
    """The team head, constructed in exactly one place.

    Both classes expose the same ``fit(team_gw)`` / ``predict(team_gw) ->
    [code, season_idx, gw, p_cs, e_gc]`` contract, so nothing downstream —
    ``advise.predict_components`` and its protected ``blend_team_odds(``
    before ``comp.merge(tp`` seam included — can tell which one it is holding.
    """
    if TEAM_MODEL == "dixon_coles":
        return DixonColesModel()
    return TeamModel(TEAM_FEATURES)


def train_all(df: pd.DataFrame, tg: pd.DataFrame, save: bool = True,
              _fit_cal: bool = True) -> dict:
    """Fit every component on the given frames.

    ``BonusModel`` is held to the newest seasons present because BPS was
    rebalanced, but only as far back as :func:`bonus_season_floor` says is
    needed to have data to fit on. On a truncated backtest frame the window
    is measured against the newest season the backtest is allowed to see,
    not the newest on disk.

    ``_fit_cal`` is the recursion guard for :func:`fit_calibration`, which
    calls back in here to refit the components on its own inner split. It
    doubles the cost of a full refit; that is a weekly job, so it is fine.
    """
    minutes = MinutesModel(MINUTES_FEATURES).fit(df)
    team = build_team_model().fit(tg.dropna(subset=["elo_diff"]))
    attacking = AttackingModel(ATTACK_FEATURES).fit(df)
    defcon = DefconModel().fit(df)
    saves = SavesModel().fit(df)
    bonus = BonusModel(min_season_idx=bonus_season_floor(df)).fit(df)
    models = {"minutes": minutes, "team": team, "attacking": attacking,
              "defcon": defcon, "saves": saves, "bonus": bonus}
    if _fit_cal:
        models["calibration"] = fit_calibration(
            df, tg, scoring_table(load_bootstrap_sample()))
    if save:
        # The odds blend weight is a training output like any other: fitted on
        # the closing-odds record, stored beside the pickles, read back by
        # blend_team_odds at prediction time. No football-data file on disk
        # means walk_forward_cs returns nothing and fit_blend_weight hands
        # back the module constant, which is the pre-v4b behaviour exactly.
        match_odds = (store.load(MATCH_ODDS_PATH)
                      if store.exists(MATCH_ODDS_PATH)
                      else pd.DataFrame())
        weight = fit_blend_weight(walk_forward_cs(tg, match_odds))
        save_params(BLEND_PARAMS_NAME, {"odds_blend_weight": weight,
                                        "rows": len(match_odds)})
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
