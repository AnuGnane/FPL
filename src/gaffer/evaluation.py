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
