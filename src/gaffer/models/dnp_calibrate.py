"""Isotonic recalibration of the minutes model's DNP-mode probability.

The v7-model diagnosis (spec §1): the zeros stratum's RMSE is 1.063 against a
naive last-5 baseline's 1.042, and the direction of the miss is systematic —
players who end up playing nothing are forecast points they were never going
to score. That is a ``p_dnp`` that is too low, and the cheapest honest fix for
a probability that is too low is to learn the map from what the head says to
what actually happens.

Isotonic rather than Platt because the map is not assumed to be a sigmoid and
because monotonicity is the one property that must not be lost: it guarantees
no two players swap places in DNP risk, so nothing the optimizer ranks can be
reordered by a calibration artefact. ``models/calibrate.py`` records an
isotonic failure at gate A, but that was isotonic on *assembled expected
points*, where plateaus collapsed the captaincy ranking into ties. A plateau
in ``p_dnp`` passes through three attacking heads, ``p60`` and a scoring table
before it reaches an EP ordering, so that failure mode does not transfer.

Calibrating one leg of a trichotomy means the other two have to move. The
freed (or claimed) mass is rescaled across ``p_sub`` and ``p_start`` in
proportion, so a player's start-versus-cameo split — which the calibration
says nothing about — is left exactly as the model had it. The single
degenerate case, a row the model priced as a certain DNP, has no ratio to
preserve; its freed mass goes to ``p_sub``, because a fringe player the
calibration has just admitted might play is a substitute, not a starter.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

DNP_MIN_ROWS = 500
"""Out-of-sample rows the fit needs before its curve is trusted.

Isotonic is non-parametric and will happily interpolate noise: below this the
curve is a memory of the holdout rather than a calibration of the head, and an
unfitted calibrator (the identity) is the better answer.
"""

DNP_HOLDOUT_SLOTS = 10
"""Gameweek slots held out to fit on, matching
:data:`gaffer.models.train.CALIBRATION_HOLDOUT_GWS` and
:data:`gaffer.evaluation.HOLDOUT_SLOTS` — the same compromise for the same
reason, and it keeps every out-of-sample window in this codebase the same
length."""

_MASS_EPS = 1e-12


class DnpCalibrator:
    """``p_dnp -> calibrated p_dnp``, with the trichotomy renormalised."""

    def __init__(self) -> None:
        self.iso: IsotonicRegression | None = None

    def fit(self, p_dnp, is_dnp) -> "DnpCalibrator":
        """Learn the map on genuinely out-of-sample predictions.

        The caller supplies predictions made by a model that never saw these
        rows (see :func:`fit_dnp_calibrator`). Fitting on in-sample
        predictions would learn the mode classifier's training-set confidence
        rather than the miscalibration a live run actually carries.

        Returns an unfitted (identity) calibrator rather than raising when
        there is too little to learn from: a thin backtest window must still
        produce a usable model.
        """
        p = np.asarray(p_dnp, dtype="float64")
        y = np.asarray(is_dnp, dtype="float64")
        ok = np.isfinite(p) & np.isfinite(y)
        p, y = p[ok], y[ok]
        if p.size < DNP_MIN_ROWS or np.unique(y).size < 2:
            return self
        iso = IsotonicRegression(y_min=0.0, y_max=1.0, increasing=True,
                                 out_of_bounds="clip")
        iso.fit(p, y)
        self.iso = iso
        return self

    def apply(self, modes: pd.DataFrame) -> pd.DataFrame:
        """A copy of the mode frame with ``p_dnp`` calibrated and the other
        two modes rescaled so the three still sum to one.

        Takes the whole frame rather than a loose column for the same reason
        :meth:`gaffer.models.calibrate.CalibrationModel.apply` does: the three
        probabilities are one object and must not drift apart.
        """
        if self.iso is None:
            return modes
        out = modes.copy()
        raw = pd.to_numeric(out["p_dnp"], errors="coerce").to_numpy(
            dtype="float64")
        finite = np.isfinite(raw)
        cal = np.clip(self.iso.predict(np.where(finite, raw, 0.0)), 0.0, 1.0)
        cal = np.where(finite, cal, raw)
        rest = 1.0 - raw
        wide = rest > _MASS_EPS
        scale = np.divide(1.0 - cal, rest, out=np.ones_like(rest), where=wide)
        # A row with no mass outside p_dnp has no ratio to preserve; the mass
        # the calibration frees goes to the substitute mode.
        freed = np.where(wide, 0.0, 1.0 - cal)
        out["p_dnp"] = cal
        out["p_sub"] = (out["p_sub"].to_numpy(dtype="float64") * scale
                        + freed)
        out["p_start"] = out["p_start"].to_numpy(dtype="float64") * scale
        return out


def fit_dnp_calibrator(df: pd.DataFrame, feature_cols: list[str],
                       holdout_slots: int = DNP_HOLDOUT_SLOTS,
                       seed: int | None = None) -> DnpCalibrator:
    """Fit the calibrator on out-of-sample DNP predictions.

    The same shape as :func:`gaffer.models.train.fit_calibration`, and for the
    same reason. The last ``holdout_slots`` ``(season_idx, gw)`` slots are held
    out, an inner :class:`~gaffer.models.minutes.ThreeModeModel` is fit on the
    rows strictly before them, and the calibration learns its map from that
    model's predictions on slots it never saw. Spec §2.2's no-leakage
    requirement — "calibrator for slot t fits on slots < t" — is met by
    construction at the slot boundary, and it composes with the harness: when
    ``evaluate_current`` fits on rows before *its* boundary, this inner split
    sits entirely inside that, so nothing the gate scores can have leaked in.

    ``_fit_dnp=False`` on the inner model is the recursion guard, exactly as
    ``_fit_cal=False`` is in ``train_all``.

    The import is function-local because ``minutes`` imports this module at
    module scope for the flag and the fitter; deferring the reverse edge keeps
    the cycle from ever being real at import time.
    """
    from gaffer.models.minutes import DNP, ThreeModeModel, mode_labels

    slots = (df[["season_idx", "gw"]].drop_duplicates()
             .sort_values(["season_idx", "gw"]))
    if len(slots) <= holdout_slots:
        return DnpCalibrator()
    row = slots.iloc[-holdout_slots]
    bs, bg = int(row["season_idx"]), int(row["gw"])
    before = ((df["season_idx"] < bs)
              | ((df["season_idx"] == bs) & (df["gw"] < bg)))
    inner_df, hold = df[before], df[~before]
    if inner_df.empty or hold.empty:
        return DnpCalibrator()
    inner = ThreeModeModel(feature_cols, seed=seed,
                           _fit_dnp=False).fit(inner_df)
    modes = inner.predict_modes(hold)
    return DnpCalibrator().fit(
        modes["p_dnp"], (mode_labels(hold) == DNP).astype("float64"))
