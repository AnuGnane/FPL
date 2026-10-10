"""v20b's head half: does the bonus head gain from seeing goals?

v20 spec §2 v20b "Head half". The holdout is ``fit_calibration``'s: the last
``CALIBRATION_HOLDOUT_GWS`` gameweek slots, with every fit on the rows
strictly before the first of them. The control is ``BonusModel`` on its eight
``BONUS_FEATURES``; the branch is the same head, wrapped here, with five more
inputs: ``e_goals`` and ``e_assists`` from an attacking fit, and
``pos_DEF``/``pos_MID``/``pos_FWD`` (GKP the base) (holiday F-15).

The spec says "refit every component". ``BONUS_FEATURES`` reads no other
head's output, so only the attacking and bonus fits can move this reading;
the minutes, team, defcon and saves heads are not fitted, which is the one
departure from the spec's wording and the reason for it. The branch's
training rows see attacking columns out of fold, one attacking refit per
left-out season of the bonus window (ruling 5's default); the held-out rows
see an attacking fit on every training row, as a live run would.

Scored on the held-out appearances (``minutes > 0``), both sides: Pearson
``corr(e_bonus, bonus)`` overall and per position, the level
``mean(e_bonus) - mean(bonus)``, and ``corr`` on the rows that scored. The
pass rule, pre-registered in the spec: overall ``corr`` up by at least 0.05,
no position's ``corr`` down by more than 0.02, and the level within 0.02 of
the control's. The lever check rides in the same line: the branch's column
count (thirteen) beside the control's (eight), and ``corr(e_goals,
e_bonus)`` on the branch's predicted rows.

Read-only. It writes nothing, edits nothing under ``models/`` and turns
nothing on (``BONUS_SEES_ATTACK`` is the arm's, the Mac's). A missing or
unreadable feature frame prints the line with ``n=0`` and a reason, never a
traceback, because the night shift transcribes the line into the spec's §6
whatever it says.

    uv run python scripts/v20b_head.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from lightgbm.basic import LightGBMError

from gaffer.data import store
from gaffer.models.attacking import AttackingModel
from gaffer.models.components import BONUS_FEATURES, BonusModel
from gaffer.models.train import (
    CALIBRATION_HOLDOUT_GWS,
    CALIBRATION_MIN_SLOTS,
    attacking_features,
    bonus_season_floor,
    load_training_frame,
)

POSITIONS = ("GKP", "DEF", "MID", "FWD")
POS_DUMMIES = ["pos_DEF", "pos_MID", "pos_FWD"]
ATTACK_COLS = ["e_goals", "e_assists"]
BRANCH_FEATURES = list(BONUS_FEATURES) + ATTACK_COLS + POS_DUMMIES

CORR_GAIN = 0.05
POSITION_SLACK = 0.02
LEVEL_SLACK = 0.02
"""The spec's pass rule (v20 spec §2 v20b "Head half")."""

PLAYER_GW_PATH = "history/player_gw.parquet"


class BranchBonusModel(BonusModel):
    """``BonusModel`` with the arm's five extra inputs, in the script only:
    ``models/`` is not edited for a head-half reading."""

    def __init__(self, min_season_idx: int = 3):
        super().__init__(feature_cols=BRANCH_FEATURES,
                         min_season_idx=min_season_idx)


def _empty(reason: str) -> dict:
    return {"n": 0, "n_train": 0, "holdout_slots": 0, "oof_folds": 0,
            "cols_main": None, "cols_branch": None,
            "corr_egoals_ebonus": None, "main": None, "branch": None,
            "verdict": "no reading", "reason": reason}


def _corr(a: np.ndarray, b: np.ndarray) -> float | None:
    """Pearson, or ``None`` where it is undefined (fewer than two rows or a
    constant side), so an empty position is no reading rather than a NaN."""
    if len(a) < 2 or np.std(a) == 0 or np.std(b) == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def _r(v: float | None) -> float | None:
    return None if v is None else round(v, 6)


def split_holdout(df: pd.DataFrame
                  ) -> tuple[pd.DataFrame, pd.DataFrame, int] | None:
    """``fit_calibration``'s split: the rows strictly before the first of the
    last ``CALIBRATION_HOLDOUT_GWS`` slots, and the rest; ``None`` where that
    function would return an identity model."""
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
    return (train.reset_index(drop=True), hold.reset_index(drop=True),
            CALIBRATION_HOLDOUT_GWS)


def with_positions(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in POS_DUMMIES:
        out[col] = (out["position"] == col[4:]).astype(float)
    return out


def attach_attack(train: pd.DataFrame, hold: pd.DataFrame, floor: int,
                  attack_cols: list[str]
                  ) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """``e_goals``/``e_assists`` on both frames. Each bonus-window season of
    the training rows is predicted by an attacking fit on every other
    training season; older rows, which the bonus fit never reads, keep 0.0.
    The held-out rows are predicted by a fit on every training row."""
    train = train.copy()
    for col in ATTACK_COLS:
        train[col] = 0.0
    folds = 0
    for season in sorted(train.loc[train["season_idx"] >= floor,
                                   "season_idx"].unique()):
        rest = train[train["season_idx"] != season]
        mask = (train["season_idx"] == season).to_numpy()
        if not (rest["minutes"] > 0).any():
            # One season of history: nothing left to fit on, so these rows
            # keep 0.0 and the fold is not counted.
            continue
        pred = AttackingModel(attack_cols).fit(rest).predict(train[mask])
        for col in ATTACK_COLS:
            train.loc[mask, col] = pred[col].to_numpy()
        folds += 1
    full = AttackingModel(attack_cols).fit(train).predict(hold)
    hold = hold.copy()
    for col in ATTACK_COLS:
        hold[col] = full[col].to_numpy()
    return train, hold, folds


def _side(e_bonus: np.ndarray, rows: pd.DataFrame) -> dict:
    bonus = rows["bonus"].to_numpy(dtype="float64")
    pos = rows["position"].to_numpy()
    scored = (rows["goals"].to_numpy() > 0) if "goals" in rows else None
    return {
        "corr": _corr(e_bonus, bonus),
        "corr_by_position": {p: _corr(e_bonus[pos == p], bonus[pos == p])
                             for p in POSITIONS},
        "level": float(np.mean(e_bonus) - np.mean(bonus)),
        "corr_scorers": (None if scored is None
                         else _corr(e_bonus[scored], bonus[scored])),
    }


def _verdict(main: dict, branch: dict) -> tuple[str, str | None]:
    if main["corr"] is None or branch["corr"] is None:
        return "no reading", "overall corr undefined on the holdout"
    failed = []
    if branch["corr"] - main["corr"] < CORR_GAIN:
        failed.append("overall_corr")
    for p in POSITIONS:
        m, b = main["corr_by_position"][p], branch["corr_by_position"][p]
        # A position the control reads and the branch cannot (a constant
        # prediction) has collapsed, so it fails rather than being skipped.
        if m is not None and (b is None or b - m < -POSITION_SLACK):
            failed.append(f"corr_{p}")
    if abs(branch["level"] - main["level"]) > LEVEL_SLACK:
        failed.append("level")
    return ("pass" if not failed else "fail: " + ", ".join(failed)), None


def _rounded(side: dict) -> dict:
    """Six places for the printed line only; the verdict reads the raw
    floats, so a real but small move is never rounded into a tie."""
    return {"corr": _r(side["corr"]),
            "corr_by_position": {p: _r(v) for p, v
                                 in side["corr_by_position"].items()},
            "level": _r(side["level"]), "corr_scorers": _r(side["corr_scorers"])}


def head_reading(df: pd.DataFrame | None,
                 attack_cols: list[str] | None = None) -> dict:
    """The ``V20B_HEAD`` payload over a player-gameweek feature frame."""
    if df is None or df.empty:
        return _empty("feature frame is empty")
    split = split_holdout(df)
    if split is None:
        return _empty(f"too few gameweek slots for the holdout "
                      f"(needs more than {CALIBRATION_MIN_SLOTS})")
    train, hold, slots = split
    cols = list(attack_cols) if attack_cols is not None else attacking_features()
    floor = bonus_season_floor(train)
    train, hold, folds = attach_attack(with_positions(train),
                                       with_positions(hold), floor, cols)
    hold = hold[(hold["minutes"] > 0) & hold["bonus"].notna()].reset_index(
        drop=True)
    if hold.empty:
        return _empty("no held-out appearance with a bonus")

    main_model = BonusModel(min_season_idx=floor).fit(train)
    branch_model = BranchBonusModel(min_season_idx=floor).fit(train)
    e_main = main_model.predict(hold)["e_bonus"].to_numpy()
    e_branch = branch_model.predict(hold)["e_bonus"].to_numpy()

    main, branch = _side(e_main, hold), _side(e_branch, hold)
    verdict, reason = _verdict(main, branch)
    return {"n": int(len(hold)),
            "n_train": int(((train["minutes"] > 0)
                            & (train["season_idx"] >= floor)
                            & train["bonus"].notna()).sum()),
            "holdout_slots": slots, "oof_folds": folds,
            "cols_main": len(main_model.cols_),
            "cols_branch": len(branch_model.cols_),
            "corr_egoals_ebonus": _r(_corr(hold["e_goals"].to_numpy(),
                                           e_branch)),
            "main": _rounded(main), "branch": _rounded(branch),
            "verdict": verdict, "reason": reason}


def main() -> int:
    try:
        if not store.exists(PLAYER_GW_PATH):
            payload = _empty(f"no feature frame: "
                             f"{store.DATA_DIR / PLAYER_GW_PATH} is missing")
        else:
            df, _, _ = load_training_frame()
            payload = head_reading(df)
    except (OSError, ValueError, KeyError, TypeError, LightGBMError) as exc:
        # A corrupt parquet raises ArrowInvalid (a ValueError); a frame
        # missing a column raises KeyError, in the feature build or the fit;
        # a degenerate fit raises LightGBMError.
        payload = _empty(f"feature frame unreadable: {type(exc).__name__}")
    print(f"V20B_HEAD {json.dumps(payload, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
