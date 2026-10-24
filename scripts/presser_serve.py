"""The presser classifier's serving rule, the reading (holiday F-38).

GUIDE §12.4: "The presser classifier only logs. Serving stays off until the
grading report (12.2) has a few gameweeks in it", under ROADMAP candidate 7.
This reads whether those gameweeks say serving is worth an arm. Serving
itself is a model-cycle arm, the Mac's and Anu's; this turns nothing on.

``availability_eval.score_presser_grades`` pools every graded gameweek into
one payload; it carries ``graded_gws`` but no per-gameweek breakdown, so the
script calls it once per graded gameweek with the snapshot log cut to that
gameweek (the results and the events frame are passed whole, as
``evaluate_presser_grades`` passes them; the grader's own ``checked_gws``
intersection then keeps the one gameweek). Each call grades the last
pre-deadline verdict per player against whether he started, so one
``PRESSER_GW`` line per gameweek carries n verdict rows, the base absence
rate over them, and each class's precision of absence and recall over the
verdict rows. ``PRESSER_SERVE`` then reads the rule below.

The pre-registered rule, written here before the script has run on real
data. A gameweek **counts** when it carries at least ``MIN_ROWS`` (20)
verdict rows. Serving is worth a model-cycle arm iff there are at least
``MIN_WEEKS`` (3) counted gameweeks and, in **every** counted gameweek (one
out of order keeps serving off, however many others are in order):

- the precision of absence falls in the order the classes are named from
  most to least absent, ``ABSENCE_ORDER`` (``ruled_out``, ``assess``,
  ``knock``, ``rotation_risk``, ``confirmed_starter``; ``irrelevant`` says
  nothing about availability and is not ordered). "Falls" is non-increasing
  over the classes present that week: a tie does not break the order, a
  class with no rows that week is skipped, and so a week with one ordered
  class present passes this half trivially;

and, pooled over the counted gameweeks, the precision of the most confident
absence class (``ruled_out``) beats the base absence rate over all of those
gameweeks' verdict rows by at least ``PRECISION_LIFT`` (0.05). Fewer than
three counted gameweeks reads ``insufficient``.

Read-only. It imports the graders and edits none of them, and writes
nothing. A missing log, missing results or no configured season print the
line with ``n=0`` and a reason, never a traceback, because the night shift
transcribes the line whatever it says.

    uv run python scripts/presser_serve.py
"""

from __future__ import annotations

import itertools
import json

import pandas as pd

from gaffer.availability_eval import (
    checked_gws,
    load_events,
    score_presser_grades,
)
from gaffer.evaluation import news_actuals
from gaffer.snapshot import load_snapshot_log

MIN_ROWS = 20
MIN_WEEKS = 3
PRECISION_LIFT = 0.05
"""The pre-registered rule (holiday F-38's default)."""

ABSENCE_ORDER = ("ruled_out", "assess", "knock", "rotation_risk",
                 "confirmed_starter")
"""The classifier's vocabulary (``data/news/classifier.py``'s prompt) from
most to least absent, ``irrelevant`` left out."""

TOP_CLASS = ABSENCE_ORDER[0]


def _r(v: float | None) -> float | None:
    return None if v is None else round(float(v), 4)


def _empty(reason: str, season: str = "") -> dict:
    return {"n": 0, "season": season, "graded_gws": [], "counted_gws": [],
            "verdict": "no reading", "reason": reason}


def graded_weeks(log: pd.DataFrame | None, actuals: pd.DataFrame | None,
                 season: str) -> list[int]:
    """The season's gameweeks that carry a verdict and a result."""
    if log is None or log.empty \
            or not {"gw", "llm_verdict"} <= set(log.columns):
        return []
    frame = log[log["llm_verdict"].notna()]
    if "season" in frame.columns:
        frame = frame[frame["season"].astype(str) == str(season)]
    gws = pd.to_numeric(frame["gw"], errors="coerce").dropna()
    return sorted({int(g) for g in gws.unique()} & checked_gws(actuals))


def in_order(per_class: list[dict]) -> bool:
    """Whether precision is non-increasing along ``ABSENCE_ORDER`` over the
    classes present."""
    by = {c["verdict"]: c["precision"] for c in per_class}
    seen = [by[v] for v in ABSENCE_ORDER if v in by]
    return all(a >= b for a, b in itertools.pairwise(seen))


def week_reading(log: pd.DataFrame, actuals: pd.DataFrame,
                 events: pd.DataFrame, gw: int, season: str) -> dict:
    """One ``PRESSER_GW`` payload: the grader over the log cut to ``gw``."""
    cut = log[pd.to_numeric(log["gw"], errors="coerce") == gw]
    graded = score_presser_grades(cut, actuals, events, season=season)
    n = int(graded.get("rows") or 0)
    absent = int(graded.get("absent_rows") or 0)
    per_class = graded.get("per_class") or []
    return {
        "gw": int(gw), "n": n, "absent": absent,
        "base_absence": _r(absent / n) if n else None,
        "classes": {c["verdict"]: {"n": c["n"],
                                   "precision": _r(c["precision"]),
                                   "recall": _r(c["recall"])}
                    for c in per_class},
        "top_n": next((c["n"] for c in per_class
                       if c["verdict"] == TOP_CLASS), 0),
        "top_absent": next((c["not_started"]
                            for c in graded.get("confusion") or []
                            if c["verdict"] == TOP_CLASS), 0),
        "in_order": in_order(per_class) if n else None,
        "counts": n >= MIN_ROWS,
        "note": graded.get("note"),
    }


def serve_reading(weeks: list[dict], season: str) -> dict:
    """The ``PRESSER_SERVE`` payload over the per-gameweek readings."""
    counted = [w for w in weeks if w["counts"]]
    out = {"n": sum(w["n"] for w in weeks), "season": season,
           # The weeks the grader scored: one whose verdicts all came after
           # its deadline prints its line (and the grader's note) but is not
           # graded.
           "graded_gws": [w["gw"] for w in weeks if w["n"]],
           "counted_gws": [w["gw"] for w in counted],
           "out_of_order_gws": [w["gw"] for w in counted
                                if not w["in_order"]],
           "reason": None}
    if len(counted) < MIN_WEEKS:
        return {**out, "verdict": (
            f"insufficient: {len(counted)} graded gameweek(s) with "
            f"{MIN_ROWS}+ verdict rows, the rule needs {MIN_WEEKS}")}
    rows = sum(w["n"] for w in counted)
    absent = sum(w["absent"] for w in counted)
    top_n = sum(w["top_n"] for w in counted)
    top_absent = sum(w["top_absent"] for w in counted)
    base = absent / rows
    top = top_absent / top_n if top_n else None
    out.update(pooled_base_absence=_r(base), pooled_top_n=top_n,
               pooled_top_precision=_r(top))
    if out["out_of_order_gws"]:
        return {**out, "verdict": (
            "stays off: precision is out of class order in GW"
            + ", GW".join(str(g) for g in out["out_of_order_gws"]))}
    if top is None:
        return {**out, "verdict": f"stays off: no {TOP_CLASS} rows in the "
                                  "counted gameweeks"}
    lift = top - base
    if lift < PRECISION_LIFT:
        return {**out, "verdict": (
            f"stays off: {TOP_CLASS} precision beats the base rate by "
            f"{lift:+.4f}, under {PRECISION_LIFT}")}
    return {**out, "verdict": (
        f"worth an arm: in class order in every counted gameweek and "
        f"{TOP_CLASS} beats the base rate by {lift:+.4f}")}


def readings(log: pd.DataFrame | None, actuals: pd.DataFrame | None,
             events: pd.DataFrame | None,
             season: str) -> tuple[list[dict], dict]:
    """Every ``PRESSER_GW`` payload and the ``PRESSER_SERVE`` one."""
    if not season:
        return [], _empty("no configured season: the grader compares the "
                          "log's season column against it", season)
    if log is None or log.empty:
        return [], _empty("no snapshot log banked", season)
    if "llm_verdict" not in log.columns:
        return [], _empty("the snapshot log carries no llm_verdict column",
                          season)
    if actuals is None or actuals.empty:
        return [], _empty("no results: live/player_gw.parquet is missing or "
                          "empty", season)
    gws = graded_weeks(log, actuals, season)
    if not gws:
        return [], _empty(f"no gameweek of season {season} carries both a "
                          "verdict and a result yet", season)
    weeks = [week_reading(log, actuals, events, gw, season) for gw in gws]
    return weeks, serve_reading(weeks, season)


def _season() -> str:
    """The configured season, or ``""``, which :func:`readings` reports."""
    try:
        from gaffer.config import load_config

        return str(load_config().current_season or "")
    except Exception:  # noqa: BLE001 — a reading never blocks on config; an empty season prints its own reason
        return ""


def main() -> int:
    """Grade the presser verdicts and print a ``PRESSER_GW`` line per week
    and the ``PRESSER_SERVE`` verdict."""
    season = _season()
    try:
        weeks, serve = readings(load_snapshot_log(), news_actuals(),
                                load_events(), season)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        # A corrupt parquet raises ArrowInvalid (a ValueError); a log missing
        # a join column raises KeyError in the grader.
        weeks, serve = [], _empty(
            f"log or results unreadable: {type(exc).__name__}", season)
    for week in weeks:
        print(f"PRESSER_GW {json.dumps(week, sort_keys=True)}")
    print(f"PRESSER_SERVE {json.dumps(serve, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
