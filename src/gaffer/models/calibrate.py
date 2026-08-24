"""Post-assembly EP calibration: a per-position starter-bias correction.

The assembled expected points carry a known level bias (v1 holdout: 60+-minute
starters under-predicted by ~1.1 pts). This corrects it with one additive
delta per position group, scaled by ``p60``.

An earlier version fit isotonic regression per position instead. It fixed the
level but wrecked the thing the tool is actually for. Two measured failures on
the 2025/26 GW30-38 holdout:

* The fitted curves plateaued — DEF mapped every input above ep 4.4 to the
  same 5.37, GKP was near-constant across its whole range. Each gameweek's
  top ten collapsed from ten distinct ep values to under five, with a mean of
  2.7 players tied at the maximum, so the captain pick became arbitrary among
  ties and ``captain_pts`` fell from 5.33 to 3.67.
* It was fit on appearances but applied to every row, so its low end floored
  at 1.6-3.1 points. Non-playing filler that truly scores zero was predicted
  at two-plus points and ``mae_all`` doubled.

An additive shift avoids both. Adding a constant within a position is
strictly order-preserving, so it cannot create a tie or compress a gap; and
gating on ``p60`` means the correction reaches nailed starters in full and
bench filler not at all, which is exactly where the bias was measured. An
unfitted (or absent) model is the identity, so old model directories keep
working.
"""
from __future__ import annotations

import pandas as pd

POSITION_GROUPS = ["GKP", "DEF", "MID", "FWD"]
MIN_ROWS = 200


class CalibrationModel:
    def __init__(self) -> None:
        # position -> additive points correction for a nailed starter.
        self.by_pos: dict[str, float] = {}

    def fit(self, ep: pd.Series, actual: pd.Series,
            position: pd.Series) -> "CalibrationModel":
        """Learn mean(actual - ep) per position group.

        The caller restricts the rows to appearances (see
        ``train.fit_calibration``). That is the right population precisely
        because :meth:`apply` gates on ``p60``: the delta is measured on
        players who played and is handed out in proportion to how likely a
        player is to play.
        """
        resid = actual.to_numpy(dtype=float) - ep.to_numpy(dtype=float)
        pos = position.to_numpy()
        for group in POSITION_GROUPS:
            mask = pos == group
            if mask.sum() >= MIN_ROWS:
                self.by_pos[group] = float(resid[mask].mean())
        return self

    def apply(self, assembled: pd.DataFrame) -> pd.DataFrame:
        """Shift ``ep`` by ``p60 * delta[position]``.

        Takes the whole assembled frame rather than loose columns so ``ep``,
        ``position`` and ``p60`` cannot drift out of alignment. A position
        with no fitted delta, or a row with a missing ``p60``, is left
        exactly as it was.
        """
        if not self.by_pos:
            return assembled
        out = assembled.copy()
        delta = out["position"].map(self.by_pos).astype(float)
        p60 = pd.to_numeric(out["p60"], errors="coerce")
        out["ep"] = out["ep"] + (delta * p60).fillna(0.0)
        return out
