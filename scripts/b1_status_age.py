"""B1's second half: does the age of a status say anything the status does not?

ROADMAP candidate 6 (GUIDE §12.5 item 6). The 2026-09-01 research's B1 row
proposes a feature, "days since status last changed", once the flag-latency
report shows the log carries the signal. This is that reading, before the
feature (holiday F-21); the feature itself is a model-cycle arm, the Mac's.

The log is ``snapshot.load_snapshot_log()`` cut to one season (the configured
``current_season``, as ``availability_eval``'s graders take ``season=``, so
last season's gameweek n never meets this season's results), one row per
``(snap_date, code)`` with the last banked one kept. For every row the age is
the whole days since the player's ``(status, chance_of_playing)`` pair last
took its present value, read over the whole season's log up to that row's day
(a flag set in an earlier gameweek's window still counts). The change is
dated by the first snapshot that shows it, so with a missed day the age reads
short, never long. A pair that has not changed since the player's first row in
the log reads ``censored``, not zero: the log cannot say when it was set. That
covers the brief's case (an unchanged row from the log's first day) and also
a player who enters the log mid-season, whose first value was set at a time
the log did not see.

Each graded gameweek (pre-deadline rows by ``availability_eval.pre_deadline``
against ``deadlines(load_events())``, and the gameweek present in the results,
which is ``checked_gws``'s reading) contributes, per player, its last
pre-deadline row: its status and its age bucket (0-1, 2-3, 4-7, 8+ days, or
censored). The truth is ``evaluation.start_truth``, taken as the max per
``(gw, code)`` as ``availability_eval._outcomes`` does, so a double gameweek
is one row and "started" means started either. A row with no result is not
scored. Where ``news_shadow`` banked a row for the same ``(gw, code)`` in the
season (the last run kept), its ``p_play_flags`` is averaged beside the share,
with the count it is over.

The pass rule, written here before the script has run on real data: the
feature is worth an arm iff, within one status, the start share differs by at
least ``SHARE_GAP`` (0.10) between the youngest and the oldest uncensored age
buckets that each hold at least ``MIN_ROWS`` (30) rows. A status with fewer
than two such buckets is not read; no readable status reads ``insufficient``.

Read-only. It imports the readers and edits none of them, writes nothing and
adds no feature. A short or missing log, or no configured season (the join
is not read across seasons), prints the line with ``n=0`` and a reason,
never a traceback, because the night shift transcribes the line
whatever it says.

    uv run python scripts/b1_status_age.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from gaffer.availability_eval import deadlines, load_events, pre_deadline
from gaffer.evaluation import news_actuals, start_truth
from gaffer.news_shadow import load_shadow
from gaffer.snapshot import load_snapshot_log

AGE_BUCKETS = ((0, 1, "0-1"), (2, 3, "2-3"), (4, 7, "4-7"), (8, None, "8+"))
"""Whole days, both ends inclusive; ``None`` is open."""

CENSORED = "censored"

SHARE_GAP = 0.10
MIN_ROWS = 30
"""The pre-registered pass rule (holiday F-21's default)."""

_NO_VALUE = "\x00"
"""Stands in for a null ``status`` or ``chance_of_playing`` in the change
test, so "the log said nothing" is a value like any other and a move to or
from it is a change, as ``score_flag_latency`` treats a null status."""


def _empty(reason: str, season: str = "") -> dict:
    return {"n": 0, "season": season, "statuses": None,
            "verdict": "no reading", "reason": reason}


def _bucket(age: float | None) -> str:
    if age is None or pd.isna(age):
        return CENSORED
    for lo, hi, label in AGE_BUCKETS:
        if age >= lo and (hi is None or age <= hi):
            return label
    return CENSORED  # a negative age cannot arise from a sorted log


def _season_cut(frame: pd.DataFrame, season: str) -> pd.DataFrame:
    if season and "season" in frame.columns:
        return frame[frame["season"].astype(str) == str(season)]
    return frame


def with_ages(log: pd.DataFrame) -> pd.DataFrame:
    """``log`` (one season) with ``age_days`` on every row, NaN where censored.

    One row per ``(snap_date, code)``, the last banked kept; rows whose day
    will not parse are dropped, since they cannot be placed in the sequence.
    """
    frame = log.copy()
    # ``utc=True`` as ``pre_deadline`` parses the same column, so the two
    # readings of a day cannot disagree.
    frame["_day"] = pd.to_datetime(frame["snap_date"], errors="coerce",
                                   utc=True)
    frame["code"] = pd.to_numeric(frame["code"], errors="coerce")
    frame = frame[frame["_day"].notna() & frame["code"].notna()]
    # ``drop_duplicates`` and not ``groupby().last()``: ``last`` skips nulls
    # column by column, and would stitch a null ``chance_of_playing`` from one
    # banking onto the status of another.
    frame = (frame.sort_values(["code", "_day"], kind="stable")
             .drop_duplicates(["code", "_day"], keep="last")
             .reset_index(drop=True))
    chance = pd.to_numeric(frame["chance_of_playing"], errors="coerce")
    frame["_value"] = (
        frame["status"].astype("string").fillna(_NO_VALUE) + "|"
        + chance.map(lambda c: _NO_VALUE if pd.isna(c) else f"{c:g}"))
    first = ~frame.duplicated("code", keep="first")
    moved = first | (frame["_value"]
                     != frame.groupby("code")["_value"].shift())
    # The day the present value was first seen, and whether that was the
    # player's first row: both set at each move and carried forward through
    # the unchanged rows after it.
    frame["_since"] = frame["_day"].where(moved)
    frame["_from_first"] = first.astype("float64").where(moved)
    filled = frame.groupby("code")[["_since", "_from_first"]].ffill()
    frame["age_days"] = (frame["_day"] - filled["_since"]).dt.days.astype(
        "float64")
    frame.loc[filled["_from_first"] == 1.0, "age_days"] = np.nan
    return frame.drop(columns=["_value", "_since", "_from_first"])


def graded_rows(log: pd.DataFrame, actuals: pd.DataFrame,
                events: pd.DataFrame, shadow: pd.DataFrame | None,
                season: str = "") -> pd.DataFrame:
    """One row per graded ``(gw, code)``: status, bucket, started, flags."""
    aged = with_ages(_season_cut(log, season))
    window = pre_deadline(aged, deadlines(events))
    if window.empty:
        return pd.DataFrame()
    truth = actuals.assign(
        gw=pd.to_numeric(actuals["gw"], errors="coerce"),
        code=pd.to_numeric(actuals["code"], errors="coerce"))
    truth = truth[truth["gw"].notna() & truth["code"].notna()]
    truth = truth.assign(started=start_truth(truth)).groupby(
        ["gw", "code"], as_index=False).agg(started=("started", "max"))
    # A boolean, as ``_outcomes`` reads it: a results frame carrying a
    # double's starts summed to 2 must not lift a share above 1.
    truth["started"] = (truth["started"] > 0.0).astype("float64")
    last = (window.sort_values(["gw", "code", "_day"], kind="stable")
            .drop_duplicates(["gw", "code"], keep="last"))
    last["code"] = pd.to_numeric(last["code"], errors="coerce")
    rows = last.merge(truth, on=["gw", "code"], how="inner")
    rows["status"] = rows["status"].astype("string").fillna("")
    rows["age_bucket"] = rows["age_days"].map(_bucket)
    rows["p_play_flags"] = np.nan
    if shadow is not None and not shadow.empty \
            and {"gw", "code", "p_play_flags"} <= set(shadow.columns):
        sh = _season_cut(shadow, season)
        sh = sh.assign(gw=pd.to_numeric(sh["gw"], errors="coerce"),
                       code=pd.to_numeric(sh["code"], errors="coerce"))
        sh = sh[["gw", "code", "p_play_flags"]].drop_duplicates(
            ["gw", "code"], keep="last")
        rows = rows.drop(columns=["p_play_flags"]).merge(
            sh, on=["gw", "code"], how="left")
    return rows[["gw", "code", "snap_date", "status", "age_days",
                 "age_bucket", "started", "p_play_flags"]]


def _cell(part: pd.DataFrame) -> dict:
    flags = pd.to_numeric(part["p_play_flags"], errors="coerce").dropna()
    share = float(part["started"].mean())
    return {"n": len(part), "_share": share,
            "start_share": round(share, 4),
            "n_flags": len(flags),
            "mean_p_play_flags": (round(float(flags.mean()), 4)
                                  if len(flags) else None)}


def _status_verdict(cells: dict) -> dict | None:
    """The youngest and oldest qualifying uncensored buckets, or None."""
    ok = [label for _lo, _hi, label in AGE_BUCKETS
          if label in cells and cells[label]["n"] >= MIN_ROWS]
    if len(ok) < 2:
        return None
    young, old = ok[0], ok[-1]
    # Read on the printed figure: 0.6 - 0.5 is 0.0999... in floating point,
    # and a line printing ``gap: 0.1`` beside ``passes: false`` would
    # contradict the rule it states.
    gap = round(cells[young]["_share"] - cells[old]["_share"], 4)
    return {"young": young, "old": old, "gap": gap,
            "passes": abs(gap) >= SHARE_GAP}


def status_age_reading(log: pd.DataFrame | None, actuals: pd.DataFrame | None,
                       events: pd.DataFrame | None,
                       shadow: pd.DataFrame | None = None,
                       season: str = "") -> dict:
    """The ``B1_STATUS_AGE`` payload. Never raises for a missing input."""
    need = {"snap_date", "gw", "code", "status", "chance_of_playing"}
    if log is None or log.empty:
        return _empty("no availability snapshots banked", season)
    if not need <= set(log.columns):
        return _empty(f"log lacks {sorted(need - set(log.columns))}", season)
    if actuals is None or actuals.empty:
        return _empty("no results: live/player_gw.parquet is missing or empty",
                      season)
    if not {"gw", "code"} <= set(actuals.columns):
        return _empty("results lack gw or code", season)
    if not season:
        return _empty("no configured season: the log is not read across "
                      "seasons, whose gameweek n is a different fixture",
                      season)
    if not deadlines(events):
        return _empty("no gameweek has a readable deadline", season)
    if _season_cut(log, season).empty:
        return _empty(f"no snapshot banked for season {season}", season)
    rows = graded_rows(log, actuals, events, shadow, season)
    if rows.empty:
        return _empty("no pre-deadline snapshot meets a graded gameweek",
                      season)
    statuses = {}
    readable, passing = [], []
    labels = [label for _lo, _hi, label in AGE_BUCKETS] + [CENSORED]
    for status, part in rows.groupby("status", sort=True):
        cells = {label: _cell(part[part["age_bucket"] == label])
                 for label in labels if (part["age_bucket"] == label).any()}
        rule = _status_verdict(cells)
        for cell in cells.values():
            cell.pop("_share")
        name = status or "(none)"
        statuses[name] = {"n": len(part), "buckets": cells,
                          "rule": rule}
        if rule is not None:
            readable.append(name)
            if rule["passes"]:
                passing.append(f"{name} {rule['young']} vs {rule['old']} "
                               f"{rule['gap']:+.4f}")
    if passing:
        verdict = "worth an arm: " + ", ".join(passing)
    elif readable:
        verdict = (f"not worth an arm: no status's start share moves by "
                   f"{SHARE_GAP} with age ({', '.join(readable)} read)")
    else:
        verdict = (f"insufficient: no status has two uncensored age buckets "
                   f"of {MIN_ROWS} rows")
    return {"n": len(rows), "season": season,
            "gws": sorted(int(g) for g in rows["gw"].unique()),
            "statuses": statuses, "verdict": verdict, "reason": None}


def _season() -> str:
    """The configured season, or ``""``, which reads as no reading.

    ``availability_eval._season``'s direction, not ``c1_news_buckets``': the
    log and the season-less results join on ``(gw, code)``, where last
    season's gameweek n is a different fixture, so an uncut reading would be
    wrong rather than blurred.
    """
    try:
        from gaffer.config import load_config

        return str(load_config().current_season or "")
    except Exception:  # noqa: BLE001 — a missing config becomes the no-season line, never a traceback
        return ""


def main() -> int:
    """Read the snapshot log against the results and print the
    ``B1_STATUS_AGE`` verdict line."""
    season = _season()
    try:
        payload = status_age_reading(load_snapshot_log(), news_actuals(),
                                     load_events(), load_shadow(), season)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        # A corrupt parquet raises ArrowInvalid (a ValueError); a frame
        # missing a column the join needs raises KeyError.
        payload = _empty(f"log or results unreadable: {type(exc).__name__}",
                         season)
    print(f"B1_STATUS_AGE {json.dumps(payload, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
