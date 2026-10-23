"""C2's reading: is the minutes head's top ``p_play`` bin over-confident?

ROADMAP candidate 4 (GUIDE §12.5 item 4). The 2026-09-01 research's C2 row
read 0.936 predicted against 0.912 observed in the top ``p_play`` bin
(n=1519), with "log score on ``p_play``" as the target (holiday F-17).

The holdout is ``fit_calibration``'s: the last ``CALIBRATION_HOLDOUT_GWS``
gameweek slots, with the minutes head fitted on the rows strictly before the
first of them. The head is the shipped one, ``ThreeModeModel`` on
``MINUTES_FEATURES`` with ``DNP_CALIBRATION_DEFAULT`` as it stands, so
"raw" below means ``p_play`` as the fitted head predicts it, its own DNP
calibrator included, before the live availability override (which needs news
history this reading does not have). The step is an isotonic map
``p_play -> P(minutes > 0)`` fitted on the training rows' out-of-fold
predictions (one minutes refit per left-out training season, each predicting
its season from the others) and applied to the held-out rows' raw
``p_play``, bounded to ``[STEP_BOUND, 1 - STEP_BOUND]``: an isotonic map ends
in blocks of exactly 0 and 1, and one held-out row landing in such a block
and going the other way would add more than the whole bar to the log loss,
so the verdict could turn on a single row. The line counts the held-out rows
the step sends to a bound.

The line carries the reliability table over ten equal-width bins of the raw
``p_play`` (n, mean raw, mean stepped, observed share of ``minutes > 0``),
the log loss and Brier of the raw and the stepped ``p_play``, and the
verdict.

The pass rule, written here before the script has run on real data: the step
passes iff the holdout log loss falls by at least ``LOG_GAIN`` (0.001) and no
bin's ``|predicted - observed|`` widens by more than ``BIN_SLACK`` (0.01).
Bins are fixed by the raw ``p_play``, so each bin compares the same rows
before and after the step; every non-empty bin counts. The log score here is
reported as log loss (lower is better), so "improves by 0.001" is
``raw - step >= 0.001``.

Read-only. It writes nothing, edits nothing under ``models/`` and turns
nothing on: serving the step is a model-cycle arm, the Mac's. A missing or
unreadable feature frame prints the line with ``n=0`` and a reason, never a
traceback, because the night shift transcribes the line whatever it says.

    uv run python scripts/c2_pplay_bins.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from lightgbm.basic import LightGBMError
from sklearn.isotonic import IsotonicRegression

from gaffer.data import store
from gaffer.models.minutes import (  # holiday F-81: one definition, in the model
    STEP_BOUND,
    ThreeModeModel,
    _played,
    out_of_fold,
)
from gaffer.models.train import (
    CALIBRATION_HOLDOUT_GWS,
    CALIBRATION_MIN_SLOTS,
    MINUTES_FEATURES,
    load_training_frame,
)

N_BINS = 10
LOG_GAIN = 0.001
BIN_SLACK = 0.01
"""The pre-registered pass rule (holiday F-17's default)."""

EPS = 1e-6
"""Probabilities are clipped to ``[EPS, 1 - EPS]`` for the log loss only, so
a head that says 1.0 for a player who sat is scored rather than infinite."""

PLAYER_GW_PATH = "history/player_gw.parquet"


def _empty(reason: str) -> dict:
    return {"n": 0, "n_train": 0, "holdout_slots": 0, "oof_folds": 0,
            "bins": None, "raw": None, "step": None,
            "verdict": "no reading", "reason": reason}


def _r(v: float | None) -> float | None:
    return None if v is None else round(v, 6)


def split_holdout(df: pd.DataFrame
                  ) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """``fit_calibration``'s split, or ``None`` where that function would
    return an identity model."""
    slots = (df[["season_idx", "gw"]].drop_duplicates()
             .sort_values(["season_idx", "gw"]))
    if len(slots) <= CALIBRATION_MIN_SLOTS:
        return None
    bs, bg = slots.iloc[-CALIBRATION_HOLDOUT_GWS][["season_idx", "gw"]]
    before = ((df["season_idx"] < bs)
              | ((df["season_idx"] == bs) & (df["gw"] < bg)))
    train, hold = df[before], df[~before]
    if train.empty or hold.empty:
        return None
    return train.reset_index(drop=True), hold.reset_index(drop=True)


def _log_loss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, EPS, 1 - EPS)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def reliability(raw: np.ndarray, step: np.ndarray | None,
                y: np.ndarray) -> list[dict]:
    """Ten equal-width bins of the raw ``p_play``; the top edge is closed so
    a 1.0 lands in the last bin."""
    idx = np.minimum((raw * N_BINS).astype(int), N_BINS - 1)
    out = []
    for b in range(N_BINS):
        m = idx == b
        n = int(m.sum())
        out.append({
            "bin": f"{b / N_BINS:.1f}-{(b + 1) / N_BINS:.1f}", "n": n,
            "raw": float(raw[m].mean()) if n else None,
            "step": (float(step[m].mean()) if n and step is not None
                     else None),
            "observed": float(y[m].mean()) if n else None})
    return out


def _verdict(raw_ll: float, step_ll: float | None,
             bins: list[dict]) -> tuple[str, str | None]:
    if step_ll is None:
        return "no reading", "no out-of-fold season to fit the step on"
    failed = []
    if raw_ll - step_ll < LOG_GAIN:
        failed.append("log_loss")
    for b in bins:
        if not b["n"]:
            continue
        before = abs(b["raw"] - b["observed"])
        after = abs(b["step"] - b["observed"])
        if after - before > BIN_SLACK:
            failed.append(f"bin_{b['bin']}")
    return ("pass" if not failed else "fail: " + ", ".join(failed)), None


def pplay_reading(df: pd.DataFrame | None,
                  feature_cols: list[str] | None = None) -> dict:
    """The ``C2_PPLAY`` payload over a player-gameweek feature frame."""
    if df is None or df.empty:
        return _empty("feature frame is empty")
    split = split_holdout(df)
    if split is None:
        return _empty(f"too few gameweek slots for the holdout "
                      f"(needs more than {CALIBRATION_MIN_SLOTS})")
    train, hold = split
    cols = list(feature_cols) if feature_cols is not None else MINUTES_FEATURES

    raw = (ThreeModeModel(cols).fit(train).predict(hold)["p_play"]
           .to_numpy(dtype="float64"))
    y = _played(hold)
    oof_p, oof_y, folds = out_of_fold(train, cols, ThreeModeModel)
    step = None
    if folds:
        iso = IsotonicRegression(y_min=STEP_BOUND, y_max=1 - STEP_BOUND,
                                 out_of_bounds="clip").fit(oof_p, oof_y)
        step = iso.predict(raw)

    bins = reliability(raw, step, y)
    raw_ll = _log_loss(raw, y)
    step_ll = None if step is None else _log_loss(step, y)
    verdict, reason = _verdict(raw_ll, step_ll, bins)
    return {
        "n": int(len(hold)), "n_train": int(len(train)),
        "holdout_slots": CALIBRATION_HOLDOUT_GWS, "oof_folds": folds,
        "bins": [{**b, "raw": _r(b["raw"]), "step": _r(b["step"]),
                  "observed": _r(b["observed"])} for b in bins],
        "raw": {"log_loss": _r(raw_ll), "brier": _r(_brier(raw, y))},
        "step": (None if step is None else
                 {"log_loss": _r(step_ll), "brier": _r(_brier(step, y)),
                  "at_bound": int(((step <= STEP_BOUND)
                                   | (step >= 1 - STEP_BOUND)).sum())}),
        "verdict": verdict, "reason": reason}


def main() -> int:
    """Read the feature frame and print the ``C2_PPLAY`` verdict line on the
    top bin."""
    try:
        if not store.exists(PLAYER_GW_PATH):
            payload = _empty(f"no feature frame: "
                             f"{store.DATA_DIR / PLAYER_GW_PATH} is missing")
        else:
            df, _, _ = load_training_frame()
            payload = pplay_reading(df)
    except (OSError, ValueError, KeyError, TypeError, LightGBMError) as exc:
        # A corrupt parquet raises ArrowInvalid (a ValueError); a frame
        # missing a column raises KeyError, in the feature build or the fit;
        # a degenerate fit raises LightGBMError.
        payload = _empty(f"feature frame unreadable: {type(exc).__name__}")
    print(f"C2_PPLAY {json.dumps(payload, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
