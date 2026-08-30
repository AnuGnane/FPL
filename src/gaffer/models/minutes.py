"""Minutes model: P(plays), P(60+ minutes), E[minutes], from three modes.

Minutes are the gap between free and paid FPL tools, and the thing that gap
is really made of is *which* of three things happened: he did not play, he
came on, or he started. Predicting that trichotomy and deriving the three
downstream numbers from it is strictly better than fitting them separately —
the old three-head model could return p60 > p_play and had to be patched with
a clip, and it had no way at all to tell a 75-minute substitute from a starter
hooked at 40.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier, LGBMRegressor

from gaffer.models.dnp_calibrate import fit_dnp_calibrator

LGB_KW = dict(n_estimators=300, learning_rate=0.05, num_leaves=31,
              verbose=-1, random_state=7)

ENSEMBLE_KW = dict(subsample=0.8, subsample_freq=1, colsample_bytree=0.8)
"""What a *seeded* head turns on so that its seed actually bites.

:data:`LGB_KW` samples neither rows nor columns, and its frames are far below
``subsample_for_bin``, so a LightGBM fit under it is **deterministic**:
changing ``random_state`` alone reproduces the identical model, prediction for
prediction (measured, not assumed). A K-seed ensemble built on
``random_state`` by itself would therefore report a spread of exactly zero and
say nothing at all about the model's uncertainty.

"Seed-bagged" (spec §3) is taken at its word: a seeded member bags its rows
and its columns, and the seed chooses which. The spread across members is then
the real quantity M2 is after — how much this model's estimate moves when the
evidence it happens to see moves.

This is off for ``seed=None``, which is every shipped fit and ensemble member
zero, so the served model is untouched.
"""

DNP_CALIBRATION_DEFAULT = True
"""Whether :meth:`ThreeModeModel.fit` learns a DNP-mode recalibration.

**On by user decision 2026-08-30: the strict Pareto improvement across strata
is accepted despite the arm missing the ambitious pre-registered bar.** The
Z1 record below stands unamended — it is why the flip is a judgement call
rather than a gate pass.

**Gate Z1 failed on its own terms.** Spec §2.3 pre-registered the rule: zeros
RMSE must reach 1.042 or better (a 2% improvement on the 2026-08-29 baseline
of 1.063, i.e. at least to the naive last-5 baseline the model currently
loses to) while haulers RMSE stays at or under 5.171 and all-stratum RMSE at
or under 1.996 — half a percent of headroom each.

``scripts/z1_arms.py`` ran both arms over one memoised training frame. The
off arm reproduced the baseline exactly (zeros 1.063, haulers 5.145, all
1.986), so the harness had not drifted and the comparison is clean. The on
arm scored zeros **1.053**, haulers **5.149**, all **1.992**. Both guards
passed with room to spare — an isotonic recalibration of ``p_dnp`` costs the
other strata essentially nothing — but the zeros improvement was 0.9% where
2% was required. Right sign, insufficient magnitude, so the pre-registered
verdict is FAIL; the constant is True only because the user overrode that
verdict on the Pareto reading above.

The reason is in the M1 diagnostic rather than in the calibrator. The zeros
error mass is not spread evenly over players the model is merely unsure
about; it concentrates in regulars-who-sit — a nailed starter whose
``season_start_share`` and rolling minutes all say "plays 90" and who is then
withdrawn for a reason that only exists in the news feed. A monotone
recalibration cannot find those rows: it can only move a whole decile of
``p_dnp`` at once, and the rows that need moving are sitting in the same
low-``p_dnp`` deciles as the regulars who really do play. The remaining
headroom is news-shaped, which is the N-track's problem (spec §4), not a
calibration problem.

This is the v5 N1 / v6 S1 pattern: the experiment is recorded here rather
than deleted, because the machinery is cheap, correct and one constant away
from being re-measured. A future cycle with a live-status feature in the
minutes frame should re-run ``scripts/z1_arms.py`` before assuming the idea
is dead — what failed is this intervention against *these* features, not the
hypothesis that DNP probabilities are miscalibrated.

Off means off all the way down: ``fit`` does not pay for the inner refit and
``predict_modes`` does not branch, so a run with this False is the pre-v7
model prediction for prediction.
"""

DNP, SUB, START = 0, 1, 2
MODE_COLS = ["p_dnp", "p_sub", "p_start"]
SIXTY_MINUTES = 60


def mode_labels(df: pd.DataFrame) -> pd.Series:
    """{0 DNP, 1 sub, 2 start} from ``starts`` and ``minutes``.

    ``starts`` is the FPL feed's own flag and is present from 2022-23, which
    is every season in ``train_seasons``. Where it is missing the label falls
    back to the 60-minute threshold, which is what the old model used for
    everything and is wrong only for the cameo-heavy tail — better than
    dropping a season.
    """
    mins = pd.to_numeric(df["minutes"], errors="coerce").fillna(0.0)
    starts = (pd.to_numeric(df["starts"], errors="coerce")
              if "starts" in df.columns
              else pd.Series(float("nan"), index=df.index))
    starts = starts.fillna((mins >= SIXTY_MINUTES).astype("float64"))
    label = pd.Series(DNP, index=df.index, dtype="int64")
    label[mins > 0] = SUB
    # ``>= 1`` rather than ``== 1``: the column is a count, and a double
    # gameweek's aggregated row carries a 2.
    label[(mins > 0) & (starts >= 1)] = START
    return label


class _ConstantHead:
    """The value a head takes when its training slice held one answer.

    LightGBM refuses a single-class classification fit, and a regression on a
    single value is a waste of three hundred trees. Both cases are real: a
    backtest window early in a season can hold nothing but starts, and a
    fringe-player slice can hold nothing but DNPs. A constant head keeps the
    refit alive and predicts the only thing the data ever showed.
    """

    def __init__(self, value: float):
        self.value = float(value)

    def predict(self, X) -> np.ndarray:
        return np.full(len(X), self.value, dtype="float64")


class ThreeModeModel:
    """P(DNP), P(sub), P(start) — and p_play, p60, e_min derived from them.

    Same constructor shape, same ``fit``/``predict`` contract and the same
    output columns as the three-head model it replaces, so nothing downstream
    moves: ``train_all`` builds it, ``predict_components_simple`` and
    ``advise.predict_components`` read ``p_play``/``p60`` off it positionally,
    and ``evaluate_current`` scores it.

    Live availability (status / chance_of_playing / news) is still applied as
    a prediction-time override by
    :func:`gaffer.models.availability.apply_availability`, never as a trained
    feature: it does not exist historically, and training on it would be
    train/serve skew of the worst kind.
    """

    def __init__(self, feature_cols: list[str], seed: int | None = None,
                 _fit_dnp: bool = True):
        """``seed`` makes this an ensemble member; ``None`` is the shipped fit.

        The seam exists for the v7 estimation-σ ensemble (spec §3), which
        prices how much the *model's own estimate* moves by refitting the
        LightGBM heads under K seeds and reading the spread. ``None`` leaves
        :data:`LGB_KW` untouched, object for object, so the weekly refit,
        every backtest and every test are byte-identical to pre-v7.

        A seed sets ``random_state`` **and** turns on :data:`ENSEMBLE_KW`,
        without which the seed would be inert — see that constant.
        """
        self.feature_cols = feature_cols
        self.seed = seed
        self._fit_dnp = _fit_dnp
        self.lgb_kw = (dict(LGB_KW) if seed is None
                       else {**LGB_KW, **ENSEMBLE_KW,
                             "random_state": int(seed)})
        self.mode_clf = LGBMClassifier(objective="multiclass", num_class=3,
                                       **self.lgb_kw)
        self.sixty_clf = LGBMClassifier(**self.lgb_kw)
        self.min_start = LGBMRegressor(**self.lgb_kw)
        self.min_sub = LGBMRegressor(**self.lgb_kw)
        self.modes_seen: list[int] = []
        self.dnp_cal = None

    def fit(self, df: pd.DataFrame) -> "ThreeModeModel":
        X = df[self.feature_cols]
        y = mode_labels(df)
        mins = pd.to_numeric(df["minutes"], errors="coerce").fillna(0.0)
        self.modes_seen = sorted(int(m) for m in y.unique())
        if len(self.modes_seen) < 2:
            only = self.modes_seen[0] if self.modes_seen else DNP
            self.mode_clf = _ConstantHead(float(only))
        else:
            self.mode_clf.fit(X, y)

        started = y == START
        subbed = y == SUB
        # P(60+ | start): fit on starters alone, because the unconditional
        # question is already answered by the mode head and mixing subs in
        # would re-learn it badly.
        self.sixty_clf = self._binary(
            X[started], (mins[started] >= SIXTY_MINUTES).astype(int),
            default=1.0)
        self.min_start = self._regressor(X[started], mins[started],
                                         default=90.0)
        self.min_sub = self._regressor(X[subbed], mins[subbed], default=20.0)
        # The recursion guard, mirroring ``train_all``'s ``_fit_cal``: the
        # calibrator's own inner model is built with it False.
        if self._fit_dnp and DNP_CALIBRATION_DEFAULT:
            self.dnp_cal = fit_dnp_calibrator(df, self.feature_cols,
                                              seed=self.seed)
        return self

    def _binary(self, X, y, default: float):
        if len(X) == 0:
            return _ConstantHead(default)
        if y.nunique() < 2:
            return _ConstantHead(float(y.iloc[0]))
        clf = LGBMClassifier(**self.lgb_kw)
        clf.fit(X, y)
        return clf

    def _regressor(self, X, y, default: float):
        if len(X) == 0:
            return _ConstantHead(default)
        if y.nunique() < 2:
            return _ConstantHead(float(y.iloc[0]))
        reg = LGBMRegressor(**self.lgb_kw)
        reg.fit(X, y)
        return reg

    @staticmethod
    def _proba(head, X) -> np.ndarray:
        """P(positive class) from either a real classifier or a constant."""
        if isinstance(head, _ConstantHead):
            return head.predict(X)
        return head.predict_proba(X)[:, 1]

    def predict_modes(self, df: pd.DataFrame) -> pd.DataFrame:
        """``p_dnp``, ``p_sub``, ``p_start``, one row per input row.

        Exposed because it is the honest object: everything ``predict``
        returns is a function of these three, and the shadow log and the
        explainability page both want the trichotomy rather than its
        summaries.

        The DNP recalibration is applied here, at the trichotomy, rather than
        to ``p_play`` downstream — ``p_play`` is a sum of two modes and
        correcting it would leave the start/cameo split incoherent with it.
        ``getattr`` rather than ``self.dnp_cal`` so a model pickled before v7
        still predicts.
        """
        X = df[self.feature_cols]
        out = pd.DataFrame(0.0, index=df.index, columns=MODE_COLS,
                           dtype="float64")
        if isinstance(self.mode_clf, _ConstantHead):
            out[MODE_COLS[int(self.mode_clf.value)]] = 1.0
        else:
            proba = self.mode_clf.predict_proba(X)
            # classes_ holds only the modes the fit actually saw, in
            # LightGBM's own order; a mode absent from training stays at the
            # 0.0 the frame was initialised with rather than shifting the
            # other two along.
            for j, mode in enumerate(self.mode_clf.classes_):
                out[MODE_COLS[int(mode)]] = proba[:, j]
        cal = getattr(self, "dnp_cal", None)
        return out if cal is None else cal.apply(out)

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """One row per input row: code, season_idx, gw, p_play, p60, e_min.

        Every number here is derived, so they cannot contradict each other:
        ``p_play = p_start + p_sub``; ``p60 = p_start * P(60+|start)``,
        because a substitute reaching 60 minutes is rare enough to price at
        zero and pricing it at anything else needs a fourth head nobody has
        measured; ``e_min`` is the mode-weighted mean of the two conditional
        minute regressions. The old ``p60 <= p_play`` clip is gone: it is now
        arithmetic rather than a patch.
        """
        X = df[self.feature_cols]
        modes = self.predict_modes(df)
        out = df[["code", "season_idx", "gw"]].copy()
        out["p_play"] = (modes["p_start"] + modes["p_sub"]).clip(0, 1).values
        out["p60"] = (modes["p_start"].values
                      * self._proba(self.sixty_clf, X)).clip(0, 1)
        e_min = (modes["p_start"].values * self.min_start.predict(X)
                 + modes["p_sub"].values * self.min_sub.predict(X))
        out["e_min"] = np.clip(e_min, 0, 90)
        return out


# Availability moved to models/availability.py in v5: it grew a line-up gate,
# an injury-curve horizon decay and an asset dependency, none of which belong
# in the module that fits the model. Re-exported because it is a published
# seam — advise.py imports it from here, and so does every test written
# before the move.
from gaffer.models.availability import RECOVERY, apply_availability  # noqa: E402,F401
