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
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from gaffer.artifacts import REPORTS
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


def stratified_metrics(pred, actual) -> dict[str, dict[str, float]]:
    """RMSE and MAE per return category plus ``all``, with row counts.

    An empty category reports zeros rather than NaN: the artifact is JSON and
    a NaN there is neither valid JSON nor readable in the UI. ``n`` is the
    field that says whether the numbers mean anything.
    """
    p = np.asarray(pred, dtype="float64")
    a = np.asarray(actual, dtype="float64")
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


def _paired(pred, actual) -> tuple[np.ndarray, np.ndarray]:
    """Prediction/outcome arrays with the incomplete rows dropped.

    Positional, not index-aligned: every ``predict`` in this codebase returns
    one row per input row in input order, and pandas would happily align two
    frames with different indexes into nonsense.
    """
    p = np.asarray(pred, dtype="float64")
    y = np.asarray(actual, dtype="float64")
    ok = ~(np.isnan(p) | np.isnan(y))
    return p[ok], y[ok]


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
    """One probability head's scoreline: log loss plus its reliability curve."""
    return {"log_loss": round(log_loss(pred, actual), 4),
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


def load_evaluation() -> dict:
    """The whole artifact. Missing file is a domain error, not a crash."""
    if not EVALUATION_PATH.exists():
        raise GafferError(
            "no evaluation on disk — run `gaffer evaluate` first")
    return json.loads(EVALUATION_PATH.read_text())


def save_evaluation(key: str, payload: dict) -> Path:
    """Merge ``payload`` in under ``key``, leaving the other keys alone."""
    stored: dict = {}
    if EVALUATION_PATH.exists():
        stored = json.loads(EVALUATION_PATH.read_text())
    stored[key] = payload
    REPORTS.mkdir(exist_ok=True)
    EVALUATION_PATH.write_text(json.dumps(stored, indent=1))
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
    last-five-match mean and ``total_points_r38`` is the season-to-date
    average, the two predictors a human would actually use. A double
    gameweek's two rows carry a near-identical rolling average, so taking the
    first is right where the truth frame has already summed the fixtures.
    """
    b = (hold[["code", "gw", col]].rename(columns={col: "ep"}).dropna()
         .groupby(["code", "gw"], as_index=False).agg(ep=("ep", "first")))
    j = b.merge(truth, on=["code", "gw"], how="inner")
    return stratified_metrics(j["ep"], j["total_points"])


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
    hold_tg = tg[~tg_before].dropna(subset=["elo_diff"]).reset_index(drop=True)
    tp = models["team"].predict(hold_tg)
    return {
        "run_at": run_at(),
        "git_sha": git_sha(),
        "holdout_slots": int(holdout_slots),
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
            "cs": head_metrics(tp["p_cs"], hold_tg["cs"].astype(float)),
        },
        "baselines": {
            "last5": baseline_metrics(hold, "total_points_r5", truth),
            "season_ppg": baseline_metrics(hold, "total_points_r38", truth),
        },
    }


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


def run_decomposition(season: str = "2025-26", start_gw: int = 5) -> dict:
    # Replaced in full by the decomposition task; the CLI imports it eagerly
    # so it has to exist before --decompose does anything.
    raise GafferError("decomposition is not implemented yet")


def format_report(key: str, payload: dict) -> str:
    """The artifact as a table a human can read in a terminal.

    The JSON is the record; this is what makes a run worth watching while it
    happens. The caveat is printed as well as stored on purpose — a bare
    comparison to somebody else's published numbers invites exactly the wrong
    conclusion.
    """
    lines = [f"=== {key} (run_at {payload.get('run_at')}, "
             f"sha {payload.get('git_sha')}) ==="]
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
        lines.append(f"-- head {head}: log loss {m['log_loss']:.4f}, "
                     f"{len(m['reliability'])} reliability bins")
        for b in m["reliability"]:
            lines.append(f"   pred {b['pred']:.3f}  obs {b['obs']:.3f}  "
                         f"n {b['n']}")
    if payload.get("caveat"):
        lines.append(f"CAVEAT: {payload['caveat']}")
    return "\n".join(lines)
