"""Post-assembly EP calibration.

The assembled expected points carry a known level bias (v1 holdout: 60+-minute
starters under-predicted by ~1.1 pts). An isotonic regression per position
group maps assembled ep -> expected actual points. It is fit on out-of-sample
predictions (see train.fit_calibration) so it corrects the pipeline's real
bias, not training-set noise. An unfitted (or absent) model is the identity,
so old model directories keep working.
"""
from __future__ import annotations

import pandas as pd
from sklearn.isotonic import IsotonicRegression

POSITION_GROUPS = ["GKP", "DEF", "MID", "FWD"]
MIN_ROWS = 200


class CalibrationModel:
    def __init__(self) -> None:
        self.by_pos: dict[str, IsotonicRegression] = {}

    def fit(self, ep: pd.Series, actual: pd.Series,
            position: pd.Series) -> "CalibrationModel":
        for pos in POSITION_GROUPS:
            mask = (position == pos).to_numpy()
            if mask.sum() >= MIN_ROWS:
                iso = IsotonicRegression(out_of_bounds="clip")
                iso.fit(ep.to_numpy()[mask], actual.to_numpy()[mask])
                self.by_pos[pos] = iso
        return self

    def apply(self, ep: pd.Series, position: pd.Series) -> pd.Series:
        out = ep.to_numpy(dtype=float).copy()
        for pos, iso in self.by_pos.items():
            mask = (position == pos).to_numpy()
            if mask.any():
                out[mask] = iso.predict(ep.to_numpy()[mask])
        return pd.Series(out, index=ep.index)
