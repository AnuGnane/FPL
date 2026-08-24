"""Model-health tracking: compare stored predictions against realised points.

After a gameweek is finalised we join the predictions log written by
``run_advise`` with the actual player returns from the live store, and persist a
small health summary to ``reports/health.json`` for the next advice run to show.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

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
    advice_file = Path(f"reports/gw{finished_gw}-advice.json")
    captain = 0
    if advice_file.exists():
        captain = json.loads(advice_file.read_text())["captain"]["code"]
    health = compute_health(preds, actuals, captain_code=captain)
    Path("reports").mkdir(exist_ok=True)
    Path("reports/health.json").write_text(json.dumps(health, indent=1))
    return health


def latest_health() -> dict | None:
    p = Path("reports/health.json")
    return json.loads(p.read_text()) if p.exists() else None
