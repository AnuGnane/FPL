"""The standing evaluation harness: how good is the model, on what yardstick.

Three things live here that nothing else in the codebase had. First, metrics
*stratified by what actually happened* — a single MAE is dominated by the
players who scored nothing, which every model gets right, so it flatters
everything equally and can never tell two models apart where it matters.
Second, calibration-first scoring of the probability heads: a p60 that is
right on average and wrong in every bin is worse than useless to a MILP that
multiplies by it. Third, one persistent artifact (``reports/evaluation.json``)
so a number from three weeks ago is still there to regress against.

Everything expensive is imported inside the function that needs it: the web
layer imports this module just to read the artifact and must not pay for
LightGBM to do it.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from gaffer.artifacts import REPORTS
from gaffer.config import load_config
from gaffer.errors import GafferError

RETURN_CATEGORIES = ["zeros", "blanks", "tickers", "haulers", "all"]
"""OpenFPL's return buckets, defined on *actual* points, plus the pooled cut.

Zeros (0), Blanks (1-2), Tickers (3-4), Haulers (5+). Keeping the exact
boundaries is what makes the published numbers in :data:`REFERENCES`
comparable at all.
"""


def categorize(points) -> np.ndarray:
    """Return bucket per row, from actual points."""
    a = np.asarray(points, dtype="float64")
    out = np.full(a.shape, "haulers", dtype=object)
    out[a <= 0] = "zeros"
    out[(a >= 1) & (a <= 2)] = "blanks"
    out[(a >= 3) & (a <= 4)] = "tickers"
    return out


def _paired(pred, actual) -> tuple[np.ndarray, np.ndarray]:
    """Prediction/outcome arrays with the non-finite rows dropped.

    Positional, not index-aligned: every ``predict`` in this codebase returns
    one row per input row in input order, and pandas would happily align two
    frames with different indexes into nonsense.
    """
    p = np.asarray(pred, dtype="float64")
    y = np.asarray(actual, dtype="float64")
    ok = np.isfinite(p) & np.isfinite(y)
    return p[ok], y[ok]


def stratified_metrics(pred, actual) -> dict[str, dict[str, float]]:
    """RMSE and MAE per return category plus ``all``, with row counts.

    An empty category reports zeros rather than NaN: the artifact is JSON and
    a NaN there is neither valid JSON nor readable in the UI. ``n`` is the
    field that says whether the numbers mean anything.

    Non-finite pairs are dropped for the same reason: a single NaN ``ep`` —
    one player missing a component — would otherwise turn its whole category's
    RMSE and MAE into NaN and take the artifact down with it. Dropping is
    honest here because ``n`` reports how many rows survived.
    """
    p, a = _paired(pred, actual)
    cats = categorize(a)
    out: dict[str, dict[str, float]] = {}
    for name in RETURN_CATEGORIES:
        sel = np.ones(a.shape, dtype=bool) if name == "all" else cats == name
        n = int(sel.sum())
        err = p[sel] - a[sel]
        out[name] = {
            "rmse": round(float(np.sqrt((err ** 2).mean())), 3) if n else 0.0,
            "mae": round(float(np.abs(err).mean()), 3) if n else 0.0,
            "n": n,
        }
    return out


RELIABILITY_BINS = 10
LOG_LOSS_EPS = 1e-15
"""Clip for the log: a head that returns a hard 0 or 1 must not make the
whole metric infinite on a single wrong row."""


def log_loss(pred, actual) -> float:
    """Mean binary cross-entropy. NaN on an empty input, never an exception."""
    p, y = _paired(pred, actual)
    if p.size == 0:
        return float("nan")
    p = np.clip(p, LOG_LOSS_EPS, 1.0 - LOG_LOSS_EPS)
    return float(-(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)).mean())


def reliability(pred, actual, bins: int = RELIABILITY_BINS) -> list[dict]:
    """Reliability curve: per equal-width probability bin, ``n``, the mean
    prediction and the observed frequency.

    A head is calibrated when ``pred`` and ``obs`` match bin by bin, which is
    what the optimizer actually depends on — it multiplies by these numbers.
    Empty bins are omitted rather than emitted as zeros, so the curve never
    dives to the origin for a head whose predictions all sit in one place.
    """
    p, y = _paired(pred, actual)
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1], right=False), 0, bins - 1)
    out = []
    for b in range(bins):
        sel = idx == b
        n = int(sel.sum())
        if n == 0:
            continue
        out.append({"n": n, "pred": round(float(p[sel].mean()), 4),
                    "obs": round(float(y[sel].mean()), 4)})
    return out


def head_metrics(pred, actual) -> dict:
    """One probability head's scoreline: log loss plus its reliability curve.

    A head with nothing to score reports ``log_loss: None`` rather than NaN:
    ``None`` is JSON's null and survives the round trip to the UI, where NaN
    is not JSON at all.
    """
    ll = log_loss(pred, actual)
    return {"log_loss": None if np.isnan(ll) else round(ll, 4),
            "reliability": reliability(pred, actual)}


EVALUATION_PATH = REPORTS / "evaluation.json"
"""One artifact, three independent keys.

``current`` and ``benchmark`` are different protocols and ``decomposition``
is a pair of replays that takes hours; each is written on its own and none of
them may take the others down with it, so writes merge rather than replace.
"""


def run_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_sha() -> str:
    """Short HEAD sha, or ``"unknown"``.

    Which commit produced a number is half of what makes it comparable to the
    next one, and a missing git is never a reason to fail an evaluation.
    """
    try:
        done = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return done.stdout.strip() if done.returncode == 0 else "unknown"


def _reject_constant(name: str) -> None:
    """Refuse the bare ``NaN``/``Infinity`` literals Python's json accepts.

    They are not JSON, nothing else can read them back, and any artifact
    carrying one was written before the encoder learned to refuse them — so
    it is exactly the corrupt-artifact case, handled where that already is.
    """
    raise ValueError(f"{name} is not valid JSON")


def _read_artifact() -> dict:
    """The artifact's JSON, with a decode error stated in domain terms.

    Both callers read the same file and both are reached from the web layer,
    where an escaping ``ValueError`` is a bare 500 that says nothing about
    what to do next.
    """
    try:
        return json.loads(EVALUATION_PATH.read_text(),
                          parse_constant=_reject_constant)
    except ValueError as exc:
        raise GafferError(
            f"{EVALUATION_PATH} is not readable JSON — it may be corrupt or "
            f"mid-write; re-run `gaffer evaluate` to rebuild it ({exc})"
        ) from exc


def load_evaluation() -> dict:
    """The whole artifact. Missing or corrupt file is a domain error."""
    if not EVALUATION_PATH.exists():
        raise GafferError(
            "no evaluation on disk — run `gaffer evaluate` first")
    return _read_artifact()


def save_evaluation(key: str, payload: dict) -> Path:
    """Merge ``payload`` in under ``key``, leaving the other keys alone.

    Written through a sibling temp file and ``os.replace``, which is atomic on
    POSIX: a reader either sees the whole previous artifact or the whole new
    one, never the half-written middle. Evaluation runs take hours and the web
    layer reads this file on every request, so the two do overlap.
    """
    stored: dict = {}
    if EVALUATION_PATH.exists():
        stored = _read_artifact()
    stored[key] = payload
    # allow_nan=False: NaN/Infinity are a Python extension that no other JSON
    # reader accepts. Letting one through here buys a valid-looking artifact
    # that only fails weeks later, as a 500 from /api/quality, a long way from
    # whatever produced the NaN. Serialised before the temp file is opened, so
    # a rejected payload leaves nothing behind at all.
    text = json.dumps(stored, indent=1, allow_nan=False)
    REPORTS.mkdir(exist_ok=True)
    tmp = EVALUATION_PATH.with_name(EVALUATION_PATH.name + ".tmp")
    try:
        tmp.write_text(text)
        os.replace(tmp, EVALUATION_PATH)
    finally:
        tmp.unlink(missing_ok=True)
    return EVALUATION_PATH


HOLDOUT_SLOTS = 10
"""Gameweek slots held out in current mode.

The same ten as :data:`gaffer.models.train.CALIBRATION_HOLDOUT_GWS`, and for
the same reason: long enough to say something, short enough that the inner
model still sees nearly all of the newest season. Splitting on slots rather
than seasons also keeps components whose stats only exist in the newest
season (``tackles``/``cbi``) from losing every eligible training row.
"""

STARTER_MINUTES = 60
"""What counts as a start, matching ``evaluate_predictions``."""


def before_mask(frame: pd.DataFrame, season_idx: int, gw: int) -> pd.Series:
    """Rows strictly before the ``(season_idx, gw)`` slot."""
    return ((frame["season_idx"] < season_idx)
            | ((frame["season_idx"] == season_idx) & (frame["gw"] < gw)))


def holdout_boundary(df: pd.DataFrame,
                     holdout_slots: int = HOLDOUT_SLOTS) -> tuple[int, int]:
    """First held-out ``(season_idx, gw)`` slot, counting from the end."""
    slots = (df[["season_idx", "gw"]].drop_duplicates()
             .sort_values(["season_idx", "gw"]))
    if len(slots) <= holdout_slots:
        raise GafferError(
            f"only {len(slots)} gameweek slots in the frame — need more than "
            f"{holdout_slots} to hold one out")
    row = slots.iloc[-holdout_slots]
    return int(row["season_idx"]), int(row["gw"])


def baseline_metrics(hold: pd.DataFrame, col: str,
                     truth: pd.DataFrame) -> dict[str, dict[str, float]]:
    """A naive predictor scored on exactly the model's yardstick.

    ``col`` is a leakage-safe rolling column: ``total_points_r5`` is the
    last-five-match mean and ``total_points_r38`` is the mean of the player's
    last 38 *matches*, which rolls straight across season boundaries and so is
    not a season-to-date average — early in a season most of its window is
    last season's form. Between them they bracket the two horizons a human
    would eyeball. A double
    gameweek's two rows carry a near-identical rolling average, so taking the
    first is right where the truth frame has already summed the fixtures.
    """
    b = (hold[["code", "gw", col]].rename(columns={col: "ep"}).dropna()
         .groupby(["code", "gw"], as_index=False).agg(ep=("ep", "first")))
    j = b.merge(truth, on=["code", "gw"], how="inner")
    return stratified_metrics(j["ep"], j["total_points"])


def start_truth(hold: pd.DataFrame) -> pd.Series:
    """Did he start, as a 0/1 float, one value per row.

    ``starts`` where the feed recorded it, and ``minutes >= 60`` where it did
    not — the same inference :func:`gaffer.features.engineer._mode_rate_parts`
    makes for the shrunken start rate, and for the same reason: the column
    postdates part of the archive, and a hole would blank the metric for a
    whole season rather than for the rows that are actually unknown.
    """
    mins = pd.to_numeric(hold.get("minutes"), errors="coerce").fillna(0.0)
    inferred = (mins >= STARTER_MINUTES).astype("float64")
    if "starts" not in hold.columns:
        return inferred
    return (pd.to_numeric(hold["starts"], errors="coerce").fillna(inferred)
            .astype("float64"))


def evaluate_current(holdout_slots: int = HOLDOUT_SLOTS) -> dict:
    """Score the model on the last ``holdout_slots`` gameweek slots.

    Components are refit on everything strictly before the boundary and the
    held-out slots are predicted through the same assemble/calibrate seam the
    weekly advice uses, so what is measured here is what a live run would
    have produced. The probability heads are read straight off the models
    rather than off the assembled points: ``p_cs`` in the simple component
    path is a constant, so the clean-sheet head has to be scored against the
    team model's own output on the held-out team-gameweeks.
    """
    from gaffer.assets import load_bootstrap_sample
    from gaffer.data.bootstrap import scoring_table
    from gaffer.models.assemble import apply_calibration, assemble_ep, ep_matrix
    from gaffer.models.team import odds_blend_weight
    from gaffer.models.train import (load_training_frame,
                                     predict_components_simple, train_all)

    df, tg, _ = load_training_frame()
    bs, bg = holdout_boundary(df, holdout_slots)
    df_before, tg_before = before_mask(df, bs, bg), before_mask(tg, bs, bg)
    models = train_all(df[df_before],
                       tg[tg_before].dropna(subset=["elo_diff"]), save=False)

    hold = df[~df_before].reset_index(drop=True)
    scoring = scoring_table(load_bootstrap_sample())
    comp = predict_components_simple(models, hold)
    ep = ep_matrix(apply_calibration(assemble_ep(comp, scoring),
                                     models.get("calibration")))
    truth = hold.groupby(["code", "gw"], as_index=False).agg(
        total_points=("total_points", "sum"), minutes=("minutes", "sum"))
    scored = ep.merge(truth, on=["code", "gw"], how="inner")
    starters = scored[scored["minutes"] >= STARTER_MINUTES]

    mp = models["minutes"].predict(hold)
    # The trichotomy itself, not another function of it: p_play is a sum of
    # two modes, and an arm that sharpens the start/cameo split while leaving
    # the sum alone is invisible in p_play's log loss (v8a spec §3).
    modes = models["minutes"].predict_modes(hold)
    hold_tg = tg[~tg_before].dropna(subset=["elo_diff"]).reset_index(drop=True)
    tp = models["team"].predict(hold_tg)
    return {
        "run_at": run_at(),
        "git_sha": git_sha(),
        "holdout_slots": int(holdout_slots),
        # The weight actually in force for this run — a blended clean sheet
        # is only interpretable next to it.
        "odds_blend_weight": odds_blend_weight(),
        "stratified": {
            "all": stratified_metrics(scored["ep"], scored["total_points"]),
            "starters": stratified_metrics(starters["ep"],
                                           starters["total_points"]),
        },
        "heads": {
            "p_play": head_metrics(mp["p_play"],
                                   (hold["minutes"] > 0).astype(float)),
            "p60": head_metrics(
                mp["p60"], (hold["minutes"] >= STARTER_MINUTES).astype(float)),
            "p_start": head_metrics(modes["p_start"], start_truth(hold)),
            "cs": head_metrics(tp["p_cs"], hold_tg["cs"].astype(float)),
        },
        "baselines": {
            "last5": baseline_metrics(hold, "total_points_r5", truth),
            # Not a season PPG: the window is the last 38 matches wherever
            # they fall, season boundaries included.
            "last38_ppg": baseline_metrics(hold, "total_points_r38", truth),
        },
    }


SHADOW_PLAYED_MINUTES = 0
"""Minutes above which a player counts as having played at all.

The Brier score's outcome is "did he turn out", not "did he start": a
one-minute cameo is a two-point appearance and a returning injury's whole
question. The 60-minute threshold belongs to ``p60``, not here.
"""


def score_news_shadow(shadow: pd.DataFrame,
                      actuals: pd.DataFrame) -> dict:
    """Gate N2's readout: news predictions vs flags-only, on played weeks.

    Brier on "played at all" and MAE on minutes, computed for both sides of
    each shadow row and reported per gameweek and cumulatively. Gameweeks
    with no actuals yet are simply absent — the log is written every week and
    scored whenever the results land.

    This measures the *availability layer* and nothing else: both sides come
    off the same model run, so any difference between the columns is the news
    layer's doing by construction.
    """
    if shadow is None or shadow.empty or actuals is None or actuals.empty:
        return {"run_at": run_at(), "git_sha": git_sha(), "rows": 0,
                "overall": {}, "by_gw": []}
    # Gameweek 5 comes round every year, so the log's key is the season's as
    # well where the column exists. Logs banked before it does keep the old
    # two-part key rather than being dropped.
    key = (["season", "gw", "code"] if "season" in shadow.columns
           else ["gw", "code"])
    cols = key + ["p_play_news", "p_play_flags", "e_min_news", "e_min_flags"]
    truth = (actuals.groupby(["gw", "code"], as_index=False)
             .agg(minutes=("minutes", "sum")))
    joined = (shadow[cols].groupby(key, as_index=False).last()
              .merge(truth, on=["gw", "code"], how="inner"))
    if joined.empty:
        return {"run_at": run_at(), "git_sha": git_sha(), "rows": 0,
                "overall": {}, "by_gw": []}
    played = (joined["minutes"] > SHADOW_PLAYED_MINUTES).astype(float)
    for side in ("news", "flags"):
        joined[f"_brier_{side}"] = (joined[f"p_play_{side}"] - played) ** 2
        joined[f"_ae_{side}"] = (joined[f"e_min_{side}"]
                                 - joined["minutes"]).abs()

    def _summary(frame: pd.DataFrame) -> dict:
        return {
            "brier_news": round(float(frame["_brier_news"].mean()), 4),
            "brier_flags": round(float(frame["_brier_flags"].mean()), 4),
            "mae_news": round(float(frame["_ae_news"].mean()), 3),
            "mae_flags": round(float(frame["_ae_flags"].mean()), 3),
            "rows": int(len(frame)),
        }

    by_gw = []
    for gw in sorted(int(g) for g in joined["gw"].unique()):
        week = joined[joined["gw"] == gw]
        row = {"gw": gw, **_summary(week)}
        upto = joined[joined["gw"] <= gw]
        cum = _summary(upto)
        row["cum_brier_news"] = cum["brier_news"]
        row["cum_brier_flags"] = cum["brier_flags"]
        row["cum_mae_news"] = cum["mae_news"]
        row["cum_mae_flags"] = cum["mae_flags"]
        by_gw.append(row)

    return {"run_at": run_at(), "git_sha": git_sha(),
            "rows": int(len(joined)), "overall": _summary(joined),
            "by_gw": by_gw}


def evaluate_news_shadow() -> dict:
    """:func:`score_news_shadow` over the banked log and the live results.

    The log spans seasons; the truth does not. ``live/player_gw.parquet`` is
    this season's results and carries no season column, so last season's GW5
    row would join this season's GW5 minutes — a different fixture, often a
    different club — and quietly corrupt the N2 readout at the rollover. The
    cut is made here rather than in the scorer, which stays season-agnostic
    and scores whatever it is handed.

    A config that will not load, or a log banked before the season column
    existed, leaves the log whole: the filter sharpens the readout, it is not
    a gate on producing one.
    """
    from gaffer.data import store
    from gaffer.news_shadow import load_shadow

    actuals = (store.load("live/player_gw.parquet")
               if store.exists("live/player_gw.parquet")
               else pd.DataFrame(columns=["gw", "code", "minutes"]))
    shadow = load_shadow()
    try:
        season = str(load_config().current_season)
        if season and shadow is not None and "season" in shadow.columns:
            shadow = shadow[shadow["season"].astype(str) == season]
    except Exception as e:  # noqa: BLE001 — a readout is better than none
        print(f"news-shadow: scoring every season ({e})")
    return score_news_shadow(shadow, actuals)


BENCHMARK_TRAIN_MAX_IDX = 1
"""Newest season the benchmark may train on: season_idx 1 = 2023-24."""

BENCHMARK_TEST_IDX = 2
BENCHMARK_TEST_SEASON = "2024-25"
"""The season OpenFPL published its test numbers on."""

REFERENCES = {
    # OpenFPL, arXiv:2508.09992 — per-return-category RMSE and MAE on
    # 2024-25, the same categories used here. FPL Review's numbers are the
    # ones published alongside them in that paper, not measured by us.
    "openfpl": {
        "zeros": {"rmse": 0.818, "mae": 0.427},
        "blanks": {"rmse": 1.291, "mae": 0.749},
        "tickers": {"rmse": 1.517, "mae": 1.127},
        "haulers": {"rmse": 5.142, "mae": 4.317},
    },
    "fplreview": {
        "zeros": {"rmse": 0.689, "mae": 0.237},
        "blanks": {"rmse": 1.189, "mae": 0.597},
        "tickers": {"rmse": 1.594, "mae": 1.227},
        "haulers": {"rmse": 5.172, "mae": 4.381},
    },
}

BENCHMARK_CAVEAT = (
    "Same test season (2024-25) and the same return categories, but OpenFPL "
    "trained on four seasons (2020-21 to 2023-24) against our two, and the "
    "feature sets differ. Treat these as a yardstick, not a controlled "
    "comparison.")


def benchmark_split(df: pd.DataFrame,
                    max_train_idx: int = BENCHMARK_TRAIN_MAX_IDX,
                    test_idx: int = BENCHMARK_TEST_IDX
                    ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """``(train, test)`` for the published-numbers benchmark.

    A hard season split, not a slot split: the comparison is only meaningful
    if the model has seen nothing at all from the test season during fitting.
    The test frame's own features are still leakage-safe within the season —
    every rolling column shifts one match back — which is exactly the
    walk-forward the benchmark wants.
    """
    return (df[df["season_idx"] <= max_train_idx],
            df[df["season_idx"] == test_idx])


BENCHMARK_ABSENT_RULES = ("defensive_contribution",)
"""Scoring rules the 2024-25 season did not have.

Defensive contribution points arrived in 2025/26. The bundled scoring table
is always the *current* season's, so pricing 2024-25 expected points with it
hands every defender and midfielder points that season never awarded — a
systematic upward bias against the truth the benchmark scores against, and
against the published OpenFPL / FPL Review numbers alongside it.
"""


def benchmark_scoring(scoring: dict) -> dict:
    """``scoring`` restated to the test season's vintage.

    A copy with :data:`BENCHMARK_ABSENT_RULES` removed. ``assemble_ep`` reads
    the rules it may not find through ``s_opt``, which falls back to a no-op
    for a missing key, so dropping one simply drops that term from EP.
    Benchmark mode only: current mode is scored against the current season,
    where the rule is real.
    """
    return {k: v for k, v in scoring.items() if k not in BENCHMARK_ABSENT_RULES}


def evaluate_benchmark(max_train_idx: int = BENCHMARK_TRAIN_MAX_IDX,
                       test_idx: int = BENCHMARK_TEST_IDX) -> dict:
    """Train on the early seasons, predict every gameweek of the test season.

    One fit, then a gameweek at a time at a 1-gameweek horizon. Walking the
    gameweeks rather than predicting the season in one shot is not a
    formality: it is what keeps the loop honest about the horizon it claims,
    and it mirrors the replay's per-gameweek shape.
    """
    from gaffer.assets import load_bootstrap_sample
    from gaffer.data.bootstrap import scoring_table
    from gaffer.models.assemble import apply_calibration, assemble_ep, ep_matrix
    from gaffer.models.train import (load_training_frame,
                                     predict_components_simple, train_all)

    df, tg, _ = load_training_frame()
    train_df, test_df = benchmark_split(df, max_train_idx, test_idx)
    train_tg, _ = benchmark_split(tg, max_train_idx, test_idx)
    models = train_all(train_df, train_tg.dropna(subset=["elo_diff"]),
                       save=False)
    # The bundled table is the current season's; the test season is not.
    scoring = benchmark_scoring(scoring_table(load_bootstrap_sample()))

    parts = []
    for gw in sorted(int(g) for g in test_df["gw"].dropna().unique()):
        rows = test_df[test_df["gw"] == gw].reset_index(drop=True)
        if rows.empty:
            continue
        comp = predict_components_simple(models, rows)
        ep = ep_matrix(apply_calibration(assemble_ep(comp, scoring),
                                         models.get("calibration")))
        truth = rows.groupby(["code", "gw"], as_index=False).agg(
            total_points=("total_points", "sum"),
            minutes=("minutes", "sum"))
        parts.append(ep.merge(truth, on=["code", "gw"], how="inner"))
        print(f"benchmark gw{gw}: {len(parts[-1])} rows", flush=True)

    scored = pd.concat(parts, ignore_index=True)
    starters = scored[scored["minutes"] >= STARTER_MINUTES]
    return {
        "run_at": run_at(),
        "git_sha": git_sha(),
        "test_season": BENCHMARK_TEST_SEASON,
        "stratified": {
            "all": stratified_metrics(scored["ep"], scored["total_points"]),
            "starters": stratified_metrics(starters["ep"],
                                           starters["total_points"]),
        },
        "references": REFERENCES,
        "caveat": BENCHMARK_CAVEAT,
    }


DECOMPOSITION_HORIZONS = (1, 3)
DECOMPOSITION_SOURCES = ("model", "oracle")


def run_decomposition(season: str = "2025-26", start_gw: int = 5) -> dict:
    """Split the replay's shortfall into forecasting error and headroom.

    Four full replays — {model, oracle} x {h1, h3}. The two numbers that come
    out are the ones worth arguing about:

    ``forecast_gap_h3``
        ``oracle_h3 - model_h3``: everything a perfect forecast would add at
        the horizon the tool actually plans on. This is the size of the prize
        for model work.
    ``planning_ceiling``
        ``oracle_h3 - oracle_h1``: what looking three weeks ahead is worth
        when the forecast is already perfect — the absolute ceiling on
        multi-week planning, and usually a good deal smaller than people
        expect.

    Slow: the two model runs retrain every four gameweeks across a season.
    Run it under ``caffeinate -i``; machine sleep has killed long runs here
    before.
    """
    from gaffer import backtest

    cells: dict[str, dict] = {}
    for source in DECOMPOSITION_SOURCES:
        for horizon in DECOMPOSITION_HORIZONS:
            out = backtest.run_backtest(season=season, start_gw=start_gw,
                                        horizon=horizon, ep_source=source)
            cells[f"{source}_h{horizon}"] = {
                "total": int(out["total"]),
                "per_gw": float(out["per_gw"]),
                "hits": int(sum(int(r["hits"]) for r in out["log"])),
            }
            print(f"{source} h{horizon}: {out['total']}", flush=True)

    return {
        "run_at": run_at(),
        "git_sha": git_sha(),
        "season": season,
        "start_gw": int(start_gw),
        "cells": cells,
        "forecast_gap_h3": float(cells["oracle_h3"]["total"]
                                 - cells["model_h3"]["total"]),
        "planning_ceiling": float(cells["oracle_h3"]["total"]
                                  - cells["oracle_h1"]["total"]),
    }


def _format_news_shadow(payload: dict) -> str:
    """Gate N2's table: news against flags, per gameweek and cumulative."""
    if not payload.get("rows"):
        return ("news shadow: nothing to score yet — the log needs a "
                "completed gameweek.")
    lines = [f"news shadow ({payload['rows']} player-gameweeks)",
             "  gw   brier news / flags    mae news / flags"]
    for row in payload["by_gw"]:
        lines.append(
            f"  GW{row['gw']:<3} {row['brier_news']:.4f} / "
            f"{row['brier_flags']:.4f}      {row['mae_news']:.2f} / "
            f"{row['mae_flags']:.2f}")
    o = payload["overall"]
    lines.append(f"  all   {o['brier_news']:.4f} / "
                 f"{o['brier_flags']:.4f}      {o['mae_news']:.2f} / "
                 f"{o['mae_flags']:.2f}")
    return "\n".join(lines)


def format_report(key: str, payload: dict) -> str:
    """The artifact as a table a human can read in a terminal.

    The JSON is the record; this is what makes a run worth watching while it
    happens. The caveat is printed as well as stored on purpose — a bare
    comparison to somebody else's published numbers invites exactly the wrong
    conclusion.
    """
    # The shadow table is its own report with its own header, so it is
    # answered before the generic header is built rather than after.
    if key == "news_shadow":
        return _format_news_shadow(payload)
    lines = [f"=== {key} (run_at {payload.get('run_at')}, "
             f"sha {payload.get('git_sha')}) ==="]
    if payload.get("odds_blend_weight") is not None:
        lines.append(f"odds blend weight w = {payload['odds_blend_weight']:.2f}")
    if key == "decomposition":
        lines.append(f"{payload.get('season')} from GW{payload.get('start_gw')}")
        for name, cell in payload["cells"].items():
            lines.append(f"{name:10s} total {cell['total']:5d}  "
                         f"per_gw {cell['per_gw']:6.2f}  "
                         f"hits {cell['hits']}")
        lines.append(f"forecast_gap_h3   {payload['forecast_gap_h3']:8.1f}  "
                     "points better forecasting could still win")
        lines.append(f"planning_ceiling  {payload['planning_ceiling']:8.1f}  "
                     "most multi-week planning can ever be worth")
        return "\n".join(lines)

    for cut, table in payload.get("stratified", {}).items():
        lines.append(f"-- {cut}")
        for cat in RETURN_CATEGORIES:
            m = table[cat]
            lines.append(f"   {cat:9s} rmse {m['rmse']:7.3f}  "
                         f"mae {m['mae']:7.3f}  n {m['n']}")
    for name, table in payload.get("baselines", {}).items():
        lines.append(f"-- baseline {name}")
        for cat in RETURN_CATEGORIES:
            m = table[cat]
            lines.append(f"   {cat:9s} rmse {m['rmse']:7.3f}  "
                         f"mae {m['mae']:7.3f}  n {m['n']}")
    for source, table in payload.get("references", {}).items():
        lines.append(f"-- {source} (published)")
        for cat, m in table.items():
            lines.append(f"   {cat:9s} rmse {m['rmse']:7.3f}  "
                         f"mae {m['mae']:7.3f}")
    for head, m in payload.get("heads", {}).items():
        ll = m["log_loss"]
        lines.append(f"-- head {head}: log loss "
                     f"{'n/a' if ll is None else format(ll, '.4f')}, "
                     f"{len(m['reliability'])} reliability bins")
        for b in m["reliability"]:
            lines.append(f"   pred {b['pred']:.3f}  obs {b['obs']:.3f}  "
                         f"n {b['n']}")
    if payload.get("caveat"):
        lines.append(f"CAVEAT: {payload['caveat']}")
    return "\n".join(lines)
