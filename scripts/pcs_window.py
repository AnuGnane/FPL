"""``p_cs`` on a two-gameweek window, the reading (holiday F-26).

GUIDE §12.4's v18c residual: the calibration block grades ``p_cs`` in its
cumulative row only, because one gameweek carries about twenty club-fixtures
against ``evaluation.MIN_CALIBRATION_SAMPLES``' thirty (``PER_GW_OMITTED``).
A per-two-gameweek window is named there as a model-cycle candidate; this
script is the reading that says whether such a window would ever clear the
floor this season.

It grades the banked ``p_cs`` at club-fixture grain the way
``evaluation.evaluate_calibration`` does, re-reading the files itself because
that block's readers (``_key``, ``_club_clean_sheets``, ``_first_kickoff_ns``)
are private and ``evaluation.py`` is not edited: the season's
``data/live/player_gw.parquet`` (cut to its newest ``season`` when the column
is there, so last season's GW n is never windowed beside this season's; the
block grades every row when called with ``season=None``) names the graded
gameweeks; each one's
``reports/components_gw{n}.parquet`` is refused when it was written after the
gameweek's **first** kickoff (``evaluation.POST_HOC_REASON``) or when no
kickoff is known, and joined to the graded rows on
``evaluation.FIXTURE_KEYS``; a club-fixture exists when one of its rows saw
``STARTER_MINUTES``, and its clean sheet is ``max(gc) == 0`` over all its
rows. A double gameweek's two fixtures are two club-fixtures.

The windows are consecutive gameweek pairs anchored at GW1 (1–2, 3–4, …),
from the first graded pair to the last. A window is **complete** when both
its gameweeks were graded (neither missing nor excluded). One
``PCS_WINDOW {…}`` per window gives the gameweeks, n club-fixtures, the mean
predicted, the observed share, Brier and log loss; then ``PCS_WINDOWS {…}``.

The rule, pre-registered before the script first ran (holiday F-26): a
per-window ``p_cs`` column is worth a card iff every complete window carries
at least ``MIN_CALIBRATION_SAMPLES`` club-fixtures, the floor
``PER_GW_OMITTED`` cites (``verdict: "card"``); otherwise ``"hold"``; with no
complete window, ``"insufficient"``. It writes nothing and adds no column to
the served block; a card would be a cycle item.

Missing components or results print the line with ``n=0`` and a reason,
never a traceback, because the night shift transcribes the lines.

    uv run python scripts/pcs_window.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from gaffer.evaluation import (
    FIXTURE_KEYS,
    MIN_CALIBRATION_SAMPLES,
    POST_HOC_REASON,
    STARTER_MINUTES,
    brier,
    log_loss,
)

DATA = Path("data")
REPORTS = Path("reports")
CLUB_KEYS = ["team_code", "opp_code", "kickoff_time"]


def _keyed(frame: pd.DataFrame) -> pd.DataFrame:
    """``FIXTURE_KEYS`` coerced as ``evaluation._key`` does, null keys dropped
    (pandas merges null keys as equal, so they would cross-join)."""
    out = frame.copy()
    for col in ("code", "opp_code"):
        out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
    out["kickoff_time"] = pd.to_datetime(out["kickoff_time"], format="mixed",
                                         errors="coerce", utc=True)
    return out.dropna(subset=list(FIXTURE_KEYS))


def _num(frame: pd.DataFrame, name: str) -> pd.Series:
    """``evaluation._column``: a missing head is all-NaN, which the grading
    drops, rather than a ``KeyError``."""
    if name not in frame.columns:
        return pd.Series(float("nan"), index=frame.index, dtype="float64")
    return pd.to_numeric(frame[name], errors="coerce")


def club_fixtures(joined: pd.DataFrame) -> pd.DataFrame:
    """One row per club-fixture: ``p_cs`` and ``clean_sheet``, as
    ``evaluation._club_clean_sheets`` reads them (an hour gates existence,
    every row speaks to the conceded count)."""
    work = pd.DataFrame({"team_code": joined["team_code"],
                         "opp_code": joined["opp_code"],
                         "kickoff_time": joined["kickoff_time"],
                         "minutes": _num(joined, "minutes"),
                         "gc": _num(joined, "gc"), "p_cs": _num(joined, "p_cs")})
    played = work[work["minutes"] >= STARTER_MINUTES]
    if played.empty:
        return pd.DataFrame({"p_cs": [], "clean_sheet": []}, dtype="float64")
    real = set(map(tuple, played[CLUB_KEYS].to_numpy()))
    work = work[[tuple(r) in real for r in work[CLUB_KEYS].to_numpy()]]
    by_club = work.groupby(CLUB_KEYS, as_index=False).agg(
        p_cs=("p_cs", "max"), conceded=("gc", "max"))
    by_club["clean_sheet"] = (by_club["conceded"] == 0).astype("float64")
    by_club.loc[by_club["conceded"].isna(), "clean_sheet"] = float("nan")
    return by_club[["p_cs", "clean_sheet"]]


def _first_kickoff_ns(fixtures: pd.DataFrame | None, gw: int) -> int | None:
    """``evaluation._first_kickoff_ns`` on a fixtures frame read once for the
    season rather than once a gameweek; ``None`` excludes, never passes."""
    if fixtures is None or not {"gw", "kickoff_time"} <= set(fixtures.columns):
        return None
    week = fixtures[pd.to_numeric(fixtures["gw"], errors="coerce") == gw]
    stamps = pd.to_datetime(week["kickoff_time"], errors="coerce",
                            utc=True).dropna()
    return int(stamps.min().value) if not stamps.empty else None


def grade_week(gw: int, truth: pd.DataFrame, fixtures: pd.DataFrame | None,
               reports: Path) -> tuple[np.ndarray, np.ndarray] | str:
    """``(p_cs, clean_sheet)`` for one gameweek's club-fixtures, or the reason
    it is not graded (``"missing"`` when no components were banked)."""
    path = reports / f"components_gw{gw}.parquet"
    if not path.exists():
        return "missing"
    first = _first_kickoff_ns(fixtures, gw)
    if first is None:
        return "kickoff unknown"
    if path.stat().st_mtime_ns > first:
        return POST_HOC_REASON
    try:
        comp = pd.read_parquet(path)
    except (OSError, ValueError) as exc:
        return f"unreadable ({exc.__class__.__name__})"
    if not set(FIXTURE_KEYS) <= set(comp.columns) & set(truth.columns):
        return "no per-fixture key"
    if "team_code" not in comp.columns:
        return "components carry no club"
    comp, truth = _keyed(comp), _keyed(truth)
    sides = [name for name, frame in (("components", comp),
                                      ("graded rows", truth))
             if frame.duplicated(subset=list(FIXTURE_KEYS)).any()]
    if sides:
        return f"duplicate rows per player-fixture ({', '.join(sides)})"
    joined = comp.merge(truth, on=list(FIXTURE_KEYS), how="inner",
                        suffixes=("", "_truth"))
    if joined.empty:
        return "banked components joined no graded rows"
    clubs = club_fixtures(joined)
    p, y = clubs["p_cs"].to_numpy(float), clubs["clean_sheet"].to_numpy(float)
    keep = np.isfinite(p) & np.isfinite(y)
    return p[keep], y[keep]


def _round(x: float) -> float | None:
    return round(x, 4) if math.isfinite(x) else None


def window_row(gws: tuple[int, int], graded: dict) -> dict:
    """One ``PCS_WINDOW`` row over the gameweeks of ``gws`` that graded."""
    parts = [graded[g] for g in gws if g in graded]
    p = np.concatenate([a for a, _ in parts]) if parts else np.array([])
    y = np.concatenate([b for _, b in parts]) if parts else np.array([])
    row = {"gws": list(gws), "graded": [g for g in gws if g in graded],
           "complete": all(g in graded for g in gws), "n": int(p.size),
           "mean_pred": _round(float(p.mean())) if p.size else None,
           "observed": _round(float(y.mean())) if y.size else None,
           "brier": _round(brier(p, y)) if p.size else None,
           "log_loss": _round(log_loss(p, y)) if p.size else None}
    if not p.size:
        row["reason"] = "no graded club-fixtures"
    return row


def read(data: Path = DATA, reports: Path = REPORTS) -> tuple[list[dict], dict]:
    """``(windows, summary)`` over the season's graded gameweeks."""
    base = {"floor": MIN_CALIBRATION_SAMPLES, "windows": 0, "complete": 0,
            "n": 0, "min_complete_n": None, "excluded": [], "missing": [],
            "verdict": "insufficient"}
    path = data / "live" / "player_gw.parquet"
    if not path.exists():
        return [], {**base, "reason": f"no {path}"}
    try:
        truth_all = pd.read_parquet(path)
    except (OSError, ValueError) as exc:
        return [], {**base, "reason": f"unreadable {path}: {exc.__class__.__name__}"}
    season = None
    if "season" in truth_all.columns and truth_all["season"].notna().any():
        season = str(max(truth_all["season"].dropna().astype(str)))
        truth_all = truth_all[truth_all["season"].astype(str) == season]
    if "gw" not in truth_all.columns:
        return [], {**base, "season": season, "reason": f"no gw column in {path}"}
    gw_col = pd.to_numeric(truth_all["gw"], errors="coerce")
    gws = sorted({int(g) for g in gw_col.dropna()})
    if not gws:
        return [], {**base, "season": season, "reason": "no graded gameweeks"}
    fx_path = data / "live" / "fixtures_all.parquet"
    try:
        fixtures = pd.read_parquet(fx_path) if fx_path.exists() else None
    except (OSError, ValueError):
        fixtures = None
    graded, excluded, missing = {}, [], []
    for gw in gws:
        out = grade_week(gw, truth_all[gw_col == gw], fixtures, reports)
        if out == "missing":
            missing.append(gw)
        elif isinstance(out, str):
            excluded.append({"gw": gw, "reason": out})
        else:
            graded[gw] = out
    starts = sorted({g - (g - 1) % 2 for g in gws})
    rows = [window_row((s, s + 1), graded) for s in starts]
    complete = [r for r in rows if r["complete"]]
    min_n = min((r["n"] for r in complete), default=None)
    verdict = ("insufficient" if not complete
               else "card" if min_n >= MIN_CALIBRATION_SAMPLES else "hold")
    summary = {**base, "season": season, "windows": len(rows),
               "complete": len(complete), "n": sum(r["n"] for r in rows),
               "min_complete_n": min_n, "excluded": excluded,
               "missing": missing, "verdict": verdict}
    if not graded:
        summary["reason"] = "no gameweek graded (components missing or excluded)"
    return rows, summary


def main(data: Path = DATA, reports: Path = REPORTS) -> None:
    rows, summary = read(data, reports)
    for row in rows:
        print(f"PCS_WINDOW {json.dumps(row)}")
    print(f"PCS_WINDOWS {json.dumps(summary)}")


if __name__ == "__main__":
    main()
