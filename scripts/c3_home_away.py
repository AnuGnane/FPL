"""C3's reading: does the attacking head gain from home/away rolling splits?

ROADMAP candidate 5 (GUIDE §12.5 item 5). The 2026-09-01 research's C3 row
proposed home-only and away-only rolling splits, with "stratified buckets" as
the target (holiday F-20).

The holdout is ``fit_calibration``'s: the last ``CALIBRATION_HOLDOUT_GWS``
gameweek slots, with every fit on the rows strictly before the first of them.
The control is ``AttackingModel`` on its own features (``attacking_features()``
as it stands); the branch is the same head, wrapped here, with
``SPLIT_COLUMNS`` added.

The splits. For each stat in ``SPLIT_STATS`` (``xg``, ``xa``, ``goals``,
``assists``: the per-match columns behind the head's ``xg_r*``, ``xa_r*``,
``goals_r*`` and ``assists_r*`` inputs) and ``SPLIT_WINDOW`` (5), two
columns: ``{stat}_home_r5``, the mean over the player's last five home rows
strictly before this row, and ``{stat}_away_r5``, the same over away rows.
Both sit on every row, home or away, so the head sees the venue it plays at
(``home``) beside both histories. Rows are ordered as
``engineer.add_player_rolling`` orders them (code, season, gameweek, kickoff
where present) and roll across the season boundary as it does; a row's own
match never enters its columns (the inclusive mean of a venue's rows is
shifted one row and carried forward within the player). A player with no
earlier row at a venue reads NaN there, which LightGBM handles.

Scored on the held-out appearances (``minutes > 0``, the rows the head is
trained on): the RMSE of ``e_goals + e_assists`` against realised
``goals + assists``, both sides, for every ``evaluation.RETURN_CATEGORIES``
bucket of the realised ``total_points`` (``evaluation.categorize``; ``all``
pooled), over all held-out rows and over home and away rows separately.

The pass rule, written here before the script has run on real data: the
splits pass iff the pooled RMSE (all rows, bucket ``all``) falls by at least
``RMSE_GAIN`` (0.002) and no bucket's RMSE over all rows (zeros, blanks,
tickers, haulers) rises by more than ``BUCKET_SLACK`` (0.005). An empty
bucket does not count. The verdict reads the unrounded floats; the home and
away cuts are reported, not gated.

Read-only. It writes nothing, edits nothing under ``models/`` and turns
nothing on: a feature arm is a model-cycle arm, the Mac's. A missing or
unreadable feature frame prints the line with ``n=0`` and a reason, never a
traceback, because the night shift transcribes the line whatever it says.

    uv run python scripts/c3_home_away.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from lightgbm.basic import LightGBMError

from gaffer.data import store
from gaffer.evaluation import RETURN_CATEGORIES, categorize
from gaffer.features.engineer import (  # noqa: F401 — re-exported, holiday F-92
    SPLIT_COLUMNS,
    SPLIT_STATS,
    SPLIT_WINDOW,
    VENUES,
    add_venue_splits,
)
from gaffer.models.attacking import AttackingModel
from gaffer.models.train import (
    CALIBRATION_HOLDOUT_GWS,
    CALIBRATION_MIN_SLOTS,
    attacking_features,
    load_training_frame,
)

RMSE_GAIN = 0.002
BUCKET_SLACK = 0.005
"""The pass rule, pre-registered above (holiday F-20)."""

BUCKETS = [c for c in RETURN_CATEGORIES if c != "all"]
PLAYER_GW_PATH = "history/player_gw.parquet"


def _empty(reason: str) -> dict:
    return {"n": 0, "n_train": 0, "holdout_slots": 0,
            "cols_main": None, "cols_branch": None,
            "main": None, "branch": None,
            "verdict": "no reading", "reason": reason}


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


def _rmse(err: np.ndarray) -> float | None:
    return float(np.sqrt(np.mean(err ** 2))) if len(err) else None


def _side(pred: pd.DataFrame, rows: pd.DataFrame) -> dict:
    """RMSE and n per venue cut and bucket."""
    err = ((pred["e_goals"] + pred["e_assists"]).to_numpy()
           - (rows["goals"] + rows["assists"]).to_numpy(dtype="float64"))
    cats = categorize(rows["total_points"])
    is_home = rows["home"].astype(bool).to_numpy()
    out = {}
    for venue, vsel in (("all", np.ones(len(rows), dtype=bool)),
                        ("home", is_home), ("away", ~is_home)):
        out[venue] = {}
        for cat in RETURN_CATEGORIES:
            sel = vsel if cat == "all" else vsel & (cats == cat)
            out[venue][cat] = {"rmse": _rmse(err[sel]), "n": int(sel.sum())}
    return out


def _verdict(main: dict, branch: dict) -> tuple[str, str | None]:
    m, b = main["all"]["all"]["rmse"], branch["all"]["all"]["rmse"]
    if m is None or b is None:
        return "no reading", "no held-out appearance to score"
    failed = []
    if m - b < RMSE_GAIN:
        failed.append("overall_rmse")
    for cat in BUCKETS:
        mc, bc = main["all"][cat]["rmse"], branch["all"][cat]["rmse"]
        if mc is not None and bc is not None and bc - mc > BUCKET_SLACK:
            failed.append(f"rmse_{cat}")
    return ("pass" if not failed else "fail: " + ", ".join(failed)), None


def _rounded(side: dict) -> dict:
    """Six places for the printed line only; the verdict reads the raw
    floats, so a real but small move is never rounded into a tie."""
    return {venue: {cat: {"rmse": _r(v["rmse"]), "n": v["n"]}
                    for cat, v in cats.items()}
            for venue, cats in side.items()}


def home_away_reading(df: pd.DataFrame | None,
                      attack_cols: list[str] | None = None) -> dict:
    """The ``C3_HOME_AWAY`` payload over a player-gameweek feature frame."""
    if df is None or df.empty:
        return _empty("feature frame is empty")
    split = split_holdout(add_venue_splits(df))
    if split is None:
        return _empty(f"too few gameweek slots for the holdout "
                      f"(needs more than {CALIBRATION_MIN_SLOTS})")
    train, hold, slots = split
    cols = list(attack_cols) if attack_cols is not None else attacking_features()
    hold = hold[(hold["minutes"] > 0) & hold["goals"].notna()
                & hold["assists"].notna()
                & hold["total_points"].notna()].reset_index(drop=True)
    if hold.empty:
        return _empty("no held-out appearance with a result")

    main_model = AttackingModel(cols).fit(train)
    branch_model = AttackingModel(cols + SPLIT_COLUMNS).fit(train)
    main = _side(main_model.predict(hold), hold)
    branch = _side(branch_model.predict(hold), hold)
    verdict, reason = _verdict(main, branch)
    return {"n": int(len(hold)),
            "n_train": int((train["minutes"] > 0).sum()),
            "holdout_slots": slots,
            "cols_main": len(main_model.cols_),
            "cols_branch": len(branch_model.cols_),
            "main": _rounded(main), "branch": _rounded(branch),
            "verdict": verdict, "reason": reason}


def main() -> int:
    try:
        if not store.exists(PLAYER_GW_PATH):
            payload = _empty(f"no feature frame: "
                             f"{store.DATA_DIR / PLAYER_GW_PATH} is missing")
        else:
            df, _, _ = load_training_frame()
            payload = home_away_reading(df)
    except (OSError, ValueError, KeyError, TypeError, LightGBMError) as exc:
        # A corrupt parquet raises ArrowInvalid (a ValueError); a frame
        # missing a column raises KeyError, in the split build or the fit;
        # a degenerate fit raises LightGBMError.
        payload = _empty(f"feature frame unreadable: {type(exc).__name__}")
    print(f"C3_HOME_AWAY {json.dumps(payload, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
