"""Model-health tracking: compare stored predictions against realised points.

After a gameweek is finalised we join the predictions log written by
``run_advise`` with the actual player returns from the live store, and persist a
small health summary to ``reports/health.json`` for the next advice run to show.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from gaffer.artifacts import load_advice
from gaffer.data import store


def compute_health(preds: pd.DataFrame, actuals: pd.DataFrame,
                   captain_code: int, advice_pts: float | None = None,
                   actual_pts: float | None = None) -> dict:
    """Join predictions with actuals and summarise prediction error."""
    j = preds.merge(actuals, on=["code", "gw"], how="inner")
    starters = j[j["minutes"] >= 60]
    mae = (starters["ep"] - starters["total_points"]).abs().mean()
    return {
        "gw": int(j["gw"].iloc[0]) if len(j) else None,
        "mae_starters": round(float(mae), 2) if pd.notna(mae) else None,
        "captain_actual": int(j.loc[j["code"] == captain_code,
                                    "total_points"].iloc[0])
                          if (j["code"] == captain_code).any() else None,
        "advice_pts": advice_pts,
        "actual_pts": actual_pts,
    }


def update_health(finished_gw: int) -> dict | None:
    """After a GW is finalized: join the stored predictions log with actuals
    from data/live/player_gw.parquet; persist to reports/health.json."""
    pred_rel = f"live/predictions/gw{finished_gw}.parquet"
    if not store.exists(pred_rel) or not store.exists("live/player_gw.parquet"):
        return None
    preds = store.load(pred_rel)
    live = store.load("live/player_gw.parquet")
    actuals = live[live["gw"] == finished_gw][
        ["code", "gw", "total_points", "minutes"]]
    if actuals.empty:
        # GW not finalised yet (refresh_live only stores data_checked GWs).
        return None
    # v17f §1 part 4: the advice file is read through ``artifacts``, which is
    # the one place its name is spelled. A run with no advice on disk — or one
    # whose payload names no captain, or is not an object at all — still
    # writes a health summary; the captain's actual score is simply the one
    # line it cannot fill. ``GafferError`` is a ``ValueError``, so the three
    # named cover the missing file, a payload that is not a mapping and a
    # code that is not a number.
    try:
        captain = int((load_advice(finished_gw).get("captain") or {})
                      .get("code", 0))
    except (AttributeError, TypeError, ValueError):
        captain = 0
    health = compute_health(preds, actuals, captain_code=captain)
    Path("reports").mkdir(exist_ok=True)
    Path("reports/health.json").write_text(json.dumps(health, indent=1))
    return health


def latest_health() -> dict | None:
    p = Path("reports/health.json")
    return json.loads(p.read_text()) if p.exists() else None
