"""``density_pub_7d``'s head half: does the minutes head gain from fixture density?

GUIDE §12.4's residual ("``density_pub_7d`` is built on both seams and fed to
no head, kept for a later re-measure with a replay half of its own") and the
v20 spec §4 ("``density_pub_7d``'s re-measure: … a minutes- or
attacking-head arm with its own K ≥ 5"). This is the head half, read-only
(holiday F-32); the replay half is the Mac's, and only if this one passes.

The holdout is ``fit_calibration``'s: the last ``CALIBRATION_HOLDOUT_GWS``
gameweek slots, with both fits on the rows strictly before the first of them.
The control is ``ThreeModeModel`` on ``MINUTES_FEATURES`` as shipped; the
branch is the same head on ``MINUTES_FEATURES + engineer.DENSITY_FEATURES``
(``density_pub_7d`` and ``density_pub_missing``, both already on every frame
``feature_columns()`` builds, so nothing new is engineered here). The head is
the shipped one, its own DNP calibrator included, so ``p_play`` is what the
fitted head predicts before the live availability override.

Scored on every held-out row: the log loss and Brier of ``p_play`` against
"played at all" (``minutes > 0``) and the MAE of ``e_min`` against realised
minutes, both sides, overall and on the congested subset, the rows with
``density_pub_7d >= CONGESTED_AT`` (2: a second publicly scheduled match
within seven days). The branch head's column list rides in the line as the
lever check (CONVENTIONS §10): a branch whose list lacks ``density_pub_7d``
measured nothing.

The pass rule, written here before the script has run on real data, in
v20b's shape: the branch passes iff its overall log loss is lower than the
control's by at least ``LOG_GAIN`` (0.002) **and** its log loss on the
congested subset is no higher than the control's. An empty congested subset
cannot be read and gives ``no reading``. The verdict reads the unrounded
floats; Brier and MAE are reported, not gated. A pass makes the replay half a
candidate for Anu, never a feature change here.

Read-only. It writes nothing, edits nothing under ``models/`` or
``features/`` and turns nothing on. A missing or unreadable feature frame
prints the line with ``n=0`` and a reason, never a traceback, because the
night shift transcribes the line whatever it says.

    uv run python scripts/density_head.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from lightgbm.basic import LightGBMError

from gaffer.data import store
from gaffer.features.engineer import DENSITY_FEATURES
from gaffer.models.minutes import ThreeModeModel
from gaffer.models.train import (
    CALIBRATION_HOLDOUT_GWS,
    CALIBRATION_MIN_SLOTS,
    MINUTES_FEATURES,
    load_training_frame,
)

LOG_GAIN = 0.002
"""The pre-registered pass rule's overall bar (holiday F-32's default)."""

CONGESTED_AT = 2
"""``density_pub_7d`` at or above this is the congested subset."""

DENSITY_COL = "density_pub_7d"

EPS = 1e-6
"""Probabilities are clipped to ``[EPS, 1 - EPS]`` for the log loss only, so
a head that says 1.0 for a player who sat is scored rather than infinite."""

PLAYER_GW_PATH = "history/player_gw.parquet"


def _empty(reason: str) -> dict:
    return {"n": 0, "n_train": 0, "n_congested": 0, "holdout_slots": 0,
            "control_cols": None, "branch_cols": None,
            "control": None, "branch": None,
            "verdict": "no reading", "reason": reason}


def _r(v: float | None) -> float | None:
    return None if v is None else round(v, 6)


def split_holdout(df: pd.DataFrame
                  ) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """``fit_calibration``'s split, or ``None`` where that function would
    return an identity model (as ``scripts/c2_pplay_bins.py`` splits)."""
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


def congested(rows: pd.DataFrame) -> np.ndarray:
    """The congested subset's mask; a missing density reads as not
    congested, since ``density_pub_missing`` flags exactly those rows."""
    dens = pd.to_numeric(rows[DENSITY_COL], errors="coerce")
    return (dens >= CONGESTED_AT).fillna(False).to_numpy(dtype=bool)


def _log_loss(p: np.ndarray, y: np.ndarray) -> float | None:
    if not len(p):
        return None
    p = np.clip(p, EPS, 1 - EPS)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _side(pred: pd.DataFrame, hold: pd.DataFrame, mask: np.ndarray) -> dict:
    p = pred["p_play"].to_numpy(dtype="float64")
    e = pred["e_min"].to_numpy(dtype="float64")
    mins = (pd.to_numeric(hold["minutes"], errors="coerce").fillna(0.0)
            .to_numpy(dtype="float64"))
    y = (mins > 0).astype("float64")

    def cut(m: np.ndarray) -> dict:
        if not m.any():
            return {"log_loss": None, "brier": None, "mae_min": None}
        return {"log_loss": _log_loss(p[m], y[m]),
                "brier": float(np.mean((p[m] - y[m]) ** 2)),
                "mae_min": float(np.mean(np.abs(e[m] - mins[m])))}

    return {"all": cut(np.ones(len(hold), dtype=bool)), "congested": cut(mask)}


def _verdict(control: dict, branch: dict) -> tuple[str, str | None]:
    c_all, b_all = control["all"]["log_loss"], branch["all"]["log_loss"]
    c_con, b_con = (control["congested"]["log_loss"],
                    branch["congested"]["log_loss"])
    if c_con is None or b_con is None:
        return "no reading", (f"no held-out row has {DENSITY_COL} >= "
                              f"{CONGESTED_AT}")
    failed = []
    if c_all - b_all < LOG_GAIN:
        failed.append("log_loss")
    if b_con > c_con:
        failed.append("congested")
    return ("pass" if not failed else "fail: " + ", ".join(failed)), None


def _rounded(side: dict) -> dict:
    return {cut: {k: _r(v) for k, v in vals.items()}
            for cut, vals in side.items()}


def density_reading(df: pd.DataFrame | None,
                    control_cols: list[str] | None = None,
                    branch_cols: list[str] | None = None) -> dict:
    """The ``DENSITY_HEAD`` payload over a player-gameweek feature frame.

    ``control_cols`` defaults to ``MINUTES_FEATURES`` and ``branch_cols`` to
    the control plus ``DENSITY_FEATURES``; the tests pass small lists."""
    if df is None or df.empty:
        return _empty("feature frame is empty")
    control_cols = (list(control_cols) if control_cols is not None
                    else list(MINUTES_FEATURES))
    branch_cols = (list(branch_cols) if branch_cols is not None
                   else control_cols + [c for c in DENSITY_FEATURES
                                        if c not in control_cols])
    # The branch list holds the control's, so one check names any column
    # either fit would otherwise fail on as a bare KeyError.
    missing = [c for c in branch_cols if c not in df.columns]
    if missing:
        return _empty(f"feature frame has no {', '.join(missing)}")
    split = split_holdout(df)
    if split is None:
        return _empty(f"too few gameweek slots for the holdout "
                      f"(needs more than {CALIBRATION_MIN_SLOTS})")
    train, hold = split
    mask = congested(hold)
    control = _side(ThreeModeModel(control_cols).fit(train).predict(hold),
                    hold, mask)
    branch = _side(ThreeModeModel(branch_cols).fit(train).predict(hold),
                   hold, mask)
    verdict, reason = _verdict(control, branch)
    return {
        "n": int(len(hold)), "n_train": int(len(train)),
        "n_congested": int(mask.sum()),
        "holdout_slots": CALIBRATION_HOLDOUT_GWS,
        "control_cols": control_cols, "branch_cols": branch_cols,
        "control": _rounded(control), "branch": _rounded(branch),
        "verdict": verdict, "reason": reason}


def main() -> int:
    """Read the feature frame and print the ``DENSITY_HEAD`` verdict line."""
    try:
        if not store.exists(PLAYER_GW_PATH):
            payload = _empty(f"no feature frame: "
                             f"{store.DATA_DIR / PLAYER_GW_PATH} is missing")
        else:
            df, _, _ = load_training_frame()
            payload = density_reading(df)
    except (OSError, ValueError, KeyError, TypeError, LightGBMError) as exc:
        # A corrupt parquet raises ArrowInvalid (a ValueError); a frame
        # missing a column raises KeyError, in the feature build or the fit;
        # a degenerate fit raises LightGBMError.
        payload = _empty(f"feature frame unreadable: {type(exc).__name__}")
    print(f"DENSITY_HEAD {json.dumps(payload, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
