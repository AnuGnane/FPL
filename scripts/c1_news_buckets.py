"""C1's buckets half: does the news layer earn its place on zeros and blanks?

ROADMAP candidate 1 (GUIDE §12.5 item 1). The 2026-09-01 research's C1 row:
the news layer has never been ablated against "flag only", and the buckets
where it should show are the zeros and the blanks (holiday F-19). The replay
half and any retirement are the Mac's and Anu's; this is the reading.

The rows are gate N2's: ``news_shadow.load_shadow()`` cut to one season (the
configured ``current_season``, as ``evaluate_news_shadow`` cuts it, because
``live/player_gw.parquet`` is this season's results and carries no season
column), one row per ``(season, gw, code)`` with the last banked run kept, as
``score_news_shadow`` keeps it, joined inner to the results summed per
``(gw, code)``, so a double gameweek is one row and a shadow row with no
result yet is not scored. Each row is bucketed by its realised
``total_points`` with ``evaluation.categorize``, and ``all`` pools them.

For each of ``evaluation.RETURN_CATEGORIES`` the line carries n, the Brier of
``p_play_news`` and of ``p_play_flags`` on "played at all" (minutes above
``SHADOW_PLAYED_MINUTES``), the minutes MAE of ``e_min_news`` and
``e_min_flags``, and the same over the bucket's disagreeing rows, those where
``|p_play_news - p_play_flags| > DISAGREE``. On the agreeing rows the two
Briers are equal to within the threshold, so the disagreeing rows are where
the layer's worth is read.

The pass rule, written here before the script has run on real data: the news
layer keeps its place iff, on the disagreeing rows of the zeros bucket and of
the blanks bucket, its Brier beats the flags side's by at least
``BRIER_GAIN`` (0.002) in each, with at least ``MIN_DISAGREE`` (30)
disagreeing rows in each. Fewer rows in either reads ``insufficient``.

Read-only. It imports the readers and edits none of them, writes nothing and
turns nothing off. A missing log or missing results print the line with
``n=0`` and a reason, never a traceback, because the night shift transcribes
the line whatever it says.

    uv run python scripts/c1_news_buckets.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from gaffer.evaluation import (
    RETURN_CATEGORIES,
    SHADOW_PLAYED_MINUTES,
    categorize,
    news_actuals,
)
from gaffer.news_shadow import load_shadow

DISAGREE = 0.05
BRIER_GAIN = 0.002
MIN_DISAGREE = 30
"""The pre-registered pass rule (holiday F-19's default)."""

RULE_BUCKETS = ("zeros", "blanks")
"""The two buckets the rule reads, the research's C1 targets."""


def _empty(reason: str, season: str = "") -> dict:
    return {"n": 0, "season": season, "buckets": None,
            "verdict": "no reading", "reason": reason}


def _r(v: float) -> float | None:
    return None if not np.isfinite(v) else round(float(v), 4)


def _sides(rows: pd.DataFrame) -> dict:
    """n, both Briers and both minutes MAEs over ``rows``."""
    n = int(len(rows))
    if n == 0:
        return {"n": 0, "brier_news": None, "brier_flags": None,
                "mae_news": None, "mae_flags": None}
    played = (rows["minutes"] > SHADOW_PLAYED_MINUTES).astype("float64")
    out: dict = {"n": n}
    for side in ("news", "flags"):
        out[f"brier_{side}"] = _r(((rows[f"p_play_{side}"] - played) ** 2)
                                  .mean())
        out[f"mae_{side}"] = _r((rows[f"e_min_{side}"] - rows["minutes"])
                                .abs().mean())
    return out


def joined_rows(shadow: pd.DataFrame | None, actuals: pd.DataFrame | None,
                season: str = "") -> pd.DataFrame:
    """The scored rows: the season's log, one row per key, joined to results.

    A log banked before the season column existed keeps its two-part key and
    is not cut, as ``score_news_shadow`` and ``evaluate_news_shadow`` treat it.
    """
    if shadow is None or shadow.empty or actuals is None or actuals.empty:
        return pd.DataFrame()
    if season and "season" in shadow.columns:
        shadow = shadow[shadow["season"].astype(str) == str(season)]
    if shadow.empty:
        return pd.DataFrame()
    key = (["season", "gw", "code"] if "season" in shadow.columns
           else ["gw", "code"])
    cols = key + ["p_play_news", "p_play_flags", "e_min_news", "e_min_flags"]
    last = shadow[cols].groupby(key, as_index=False).last()
    last["gw"] = pd.to_numeric(last["gw"], errors="coerce")
    last["code"] = pd.to_numeric(last["code"], errors="coerce")
    truth = actuals.assign(
        gw=pd.to_numeric(actuals["gw"], errors="coerce"),
        code=pd.to_numeric(actuals["code"], errors="coerce"),
        minutes=pd.to_numeric(actuals["minutes"], errors="coerce").fillna(0),
        total_points=pd.to_numeric(actuals["total_points"],
                                   errors="coerce").fillna(0),
    ).groupby(["gw", "code"], as_index=False).agg(
        minutes=("minutes", "sum"), total_points=("total_points", "sum"))
    return last.merge(truth, on=["gw", "code"], how="inner")


def _verdict(buckets: dict) -> str:
    gains = []
    for name in RULE_BUCKETS:
        dis = buckets[name]["disagree"]
        if dis["n"] < MIN_DISAGREE:
            return (f"insufficient: {name} has {dis['n']} disagreeing rows, "
                    f"the rule needs {MIN_DISAGREE}")
        gains.append((name, dis["brier_flags"] - dis["brier_news"]))
    short = [f"{name} {gain:+.4f}" for name, gain in gains
             if gain < BRIER_GAIN]
    if short:
        return ("retire candidate: the news layer's Brier gain is under "
                f"{BRIER_GAIN} on " + ", ".join(short))
    return "keeps its place: " + ", ".join(
        f"{name} {gain:+.4f}" for name, gain in gains)


def buckets_reading(shadow: pd.DataFrame | None,
                    actuals: pd.DataFrame | None, season: str = "") -> dict:
    """The ``C1_BUCKETS`` payload for a shadow log and a results frame."""
    if shadow is None or shadow.empty:
        return _empty("no news shadow log banked", season)
    if actuals is None or actuals.empty:
        return _empty("no results: live/player_gw.parquet is missing or empty",
                      season)
    missing = {"gw", "code", "minutes", "total_points"} - set(actuals.columns)
    if missing:
        return _empty(f"results lack {sorted(missing)}", season)
    rows = joined_rows(shadow, actuals, season)
    if rows.empty:
        return _empty(f"no shadow row for season {season or '(any)'} "
                      "has a result yet", season)
    cats = categorize(rows["total_points"])
    dis = (rows["p_play_news"] - rows["p_play_flags"]).abs() > DISAGREE
    buckets = {}
    for name in RETURN_CATEGORIES:
        sel = (np.ones(len(rows), dtype=bool) if name == "all"
               else cats == name)
        buckets[name] = {**_sides(rows[sel]),
                         "disagree": _sides(rows[sel & dis.to_numpy()])}
    return {"n": int(len(rows)), "season": season, "buckets": buckets,
            "verdict": _verdict(buckets), "reason": None}


def _season() -> str:
    """The configured season, or ``""`` (no cut) when no config loads."""
    try:
        from gaffer.config import load_config

        return str(load_config().current_season or "")
    except Exception:  # noqa: BLE001 — a reading over every season beats none; evaluate_news_shadow falls back the same way
        return ""


def main() -> int:
    season = _season()
    try:
        payload = buckets_reading(load_shadow(), news_actuals(), season)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        # A corrupt parquet raises ArrowInvalid (a ValueError); a log missing
        # a prediction column raises KeyError in the join.
        payload = _empty(f"log or results unreadable: {type(exc).__name__}",
                         season)
    print(f"C1_BUCKETS {json.dumps(payload, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
