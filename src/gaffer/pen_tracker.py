"""The v6 penalty term, measured forward: takers predicted vs pens taken.

Read-only over what has already been banked — ``reports/components_gw{N}.parquet``
for what was served, ``data/live/player_gw.parquet`` for the week that happened.
Nothing here trains, fetches, or writes a model input, and nothing here touches
``set_pieces``: it imports the pure functions and constants and leaves the
module alone.

The v6 validation was deferred to season end. This turns that one May
comparison into a standing report that accrues weekly, which is the only
version of it anybody will actually read.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

from gaffer import artifacts
from gaffer.data import store
from gaffer.set_pieces import (GOAL_POINTS, LEAGUE_PENS_PG, PEN_CONVERSION,
                               pen_estimate, share_now)

PLAYER_GW_PATH = "live/player_gw.parquet"
EVENTS_PATH = "live/events.parquet"
UNDERSTAT_PATH = "history/understat_player.parquet"


def tracker_path() -> Path:
    """``reports/pen_tracker.json``, resolved through ``artifacts.REPORTS``.

    Read at call time rather than bound at import, so a test that redirects
    the reports directory redirects the component files and this output
    together.
    """
    return artifacts.REPORTS / "pen_tracker.json"


def finished_gws(events: pd.DataFrame) -> list[int]:
    """Gameweeks the league has actually played, in order.

    Only finished weeks: a gameweek in progress has half its penalties still
    to come, and a tracker that counted it would report a hit rate that moves
    on Sunday for reasons that are not evidence.
    """
    if events is None or "finished" not in events.columns:
        return []
    done = events[events["finished"].astype(bool)]
    return sorted(int(g) for g in done["gw"].unique())


def attach_npxg(rows: pd.DataFrame, season: str) -> pd.DataFrame | None:
    """``rows`` with Understat's ``us_npxg`` joined on (code, UK match date).

    The live parquet has no ``us_npxg`` — Understat is joined in the training
    frame, not the serving one — so the tracker does the join itself, on the
    same key ``models.train.attach_understat`` uses: Understat carries no
    gameweek number, and a player plus a date is unique even in a double
    gameweek.

    ``None`` — not a frame of NaN — when the parquet is missing or has nothing
    for this season, so the caller can tell "no coverage" from "no penalties"
    and name the instrument it fell back to.
    """
    if not store.exists(UNDERSTAT_PATH):
        return None
    us = store.load(UNDERSTAT_PATH)
    if us.empty or "us_npxg" not in us.columns:
        return None
    us = us[us["season"].astype(str) == str(season)]
    if us.empty:
        return None
    keyed = us[["code", "date", "us_npxg"]].copy()
    keyed["date"] = pd.to_datetime(keyed["date"], errors="coerce").dt.date
    keyed = keyed.drop_duplicates(subset=["code", "date"])
    out = rows.copy()
    out["_date"] = pd.to_datetime(out["kickoff_time"], errors="coerce",
                                  utc=True).dt.tz_convert(
                                      "Europe/London").dt.date
    out = out.merge(keyed.rename(columns={"date": "_date"}),
                    on=["code", "_date"], how="left", validate="many_to_one")
    return out.drop(columns=["_date"])


def realized_pens(rows: pd.DataFrame, season: str) -> tuple[pd.Series, str]:
    """Penalties taken per player-match, and the instrument that saw them.

    The xG-gap estimator when Understat covers the season, and otherwise the
    only penalties the FPL feed alone can see: the ones that were *missed*.
    That is a floor rather than a count — every converted spot kick is
    invisible to it — so the fallback is named ``pens_missed_only`` in the
    report and the two are never added together.

    ``rows`` is assumed to carry a fresh range index; the caller resets it.
    """
    joined = attach_npxg(rows, season)
    if joined is not None:
        events = pen_estimate(joined)
        if events is not None:
            return (pd.Series(events.to_numpy(), index=rows.index,
                              dtype="float64"), "xg_gap")
    if "pens_missed" not in rows.columns:
        return pd.Series(0.0, index=rows.index, dtype="float64"), \
            "pens_missed_only"
    missed = pd.to_numeric(rows["pens_missed"], errors="coerce").fillna(0.0)
    return missed.astype("float64"), "pens_missed_only"


def predicted_ep(gw: int) -> dict:
    """The pen term this gameweek's advise run actually served.

    Read off ``ep_pen_taker``, which ``run_advise`` already rescaled by the
    odds blend — so this is the increment that was *delivered*, not the one
    the model proposed. An absent component file is zeros: the tracker covers
    a whole season and the earliest weeks of one predate the artifact.
    """
    path = artifacts.components_path(gw)
    if not path.exists():
        return {"rows": 0, "ep_pen_taker": 0.0, "takers": 0}
    comp = pd.read_parquet(path)
    if "ep_pen_taker" not in comp.columns:
        return {"rows": int(len(comp)), "ep_pen_taker": 0.0, "takers": 0}
    ep = pd.to_numeric(comp["ep_pen_taker"], errors="coerce").fillna(0.0)
    return {"rows": int(len(comp)),
            "ep_pen_taker": round(float(ep.sum()), 3),
            "takers": int((ep.abs() > 0).sum())}
