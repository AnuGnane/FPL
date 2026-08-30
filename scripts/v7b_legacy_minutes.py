"""The pre-v5 minutes head, vendored verbatim for the v7b Q2 ablation.

Provenance: ``git show 01f4fe8^:src/gaffer/models/minutes.py`` — the state of
the module immediately before commit ``01f4fe8`` "feat: ThreeModeModel
replaces the three independent minutes heads". ``LGB_KW`` and the class body
below are copied byte for byte from that revision; the **only** edits are the
class's name (``MinutesModel`` -> ``LegacyMinutesModel``) at its ``class``
statement and in ``fit``'s return annotation. A tidied copy would measure the
tidying, so nothing else — spacing, docstrings, clipping order — is touched.

``apply_availability``, ``RECOVERY`` and everything below the class are
deliberately not copied: fact F1 established that the replay path never calls
them (no availability filtering, no ``predict_modes``).

Used by ``scripts/v7b_replay.py --minutes legacy``, which patches
``gaffer.models.train.ThreeModeModel`` with this class — the name ``train_all``
actually constructs — so the head swap runs on current code instead of a git
worktree checkout.
"""

from __future__ import annotations

import pandas as pd
from lightgbm import LGBMClassifier, LGBMRegressor

LGB_KW = dict(n_estimators=300, learning_rate=0.05, num_leaves=31,
              verbose=-1, random_state=7)


class LegacyMinutesModel:
    """P(plays), P(60+ minutes), E[minutes]. Trained on historical rows;
    live availability (status / chance_of_playing) is applied as a hard
    override at predict time via apply_availability(), never as a trained
    feature (it doesn't exist historically -> train/serve skew)."""

    def __init__(self, feature_cols: list[str]):
        self.feature_cols = feature_cols
        self.play_clf = LGBMClassifier(**LGB_KW)
        self.sixty_clf = LGBMClassifier(**LGB_KW)
        self.min_reg = LGBMRegressor(**LGB_KW)

    def fit(self, df: pd.DataFrame) -> "LegacyMinutesModel":
        X = df[self.feature_cols]
        self.play_clf.fit(X, (df["minutes"] > 0).astype(int))
        self.sixty_clf.fit(X, (df["minutes"] >= 60).astype(int))
        self.min_reg.fit(X, df["minutes"])
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """One row per input row: code, season_idx, gw, p_play, p60, e_min.

        The two classifiers are fit independently, so p60 is clipped to
        p_play — an incoherent p60 > p_play would inflate appearance
        points downstream.
        """
        X = df[self.feature_cols]
        out = df[["code", "season_idx", "gw"]].copy()
        out["p_play"] = self.play_clf.predict_proba(X)[:, 1]
        out["p60"] = self.sixty_clf.predict_proba(X)[:, 1].clip(0, 1)
        out["p60"] = out[["p60", "p_play"]].min(axis=1)
        out["e_min"] = self.min_reg.predict(X).clip(0, 90)
        return out
