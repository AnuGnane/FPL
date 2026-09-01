"""Gate G1, §1: what did closing the last two club-leak consumers change?

Not a gate and no keep rule. Spec §1 continues v9c's D2, whose contract was
explicit: the as-of club ships whether or not eval moves, because a regression
would mean the old number was flattered by leakage. So this script reports and
does not decide — and, unlike ``scripts/v9c_club_eval.py``, it runs no
benchmark at all. Spec §1 asks for two numbers per consumer and nothing else,
which makes this minutes rather than the hour v9c's cost:

* ``V9D_CLUB_UNDERSTAT`` — over the whole training frame: how many rows have
  ``as_of_club != team_code`` at all (the population that *can* change), how
  many of those actually see a different own-side Understat value once the
  merge runs both ways, and the own-side **match rate** (non-NaN own-side
  rows) on each side. The match rate is the sanity check spec §1 names: the
  switched join may not resolve fewer rows than the unswitched one.
* ``V9D_CLUB_CONGESTION`` — the same shape for ``matches_last_14d``: the
  diverging population, the rows whose count actually moves, and the mean
  absolute change on those rows.
* ``V9D_CLUB_DONE`` — both blocks together, banked to
  ``reports/v9d_club_eval.json``.

Run it, watch it, read the lines::

    mkdir -p logs && caffeinate -i nohup .venv/bin/python scripts/v9d_club_eval.py \\
        > logs/v9d_club_eval.log 2>&1 &
    grep -e V9D_CLUB_UNDERSTAT -e V9D_CLUB_CONGESTION -e V9D_CLUB_DONE \\
        logs/v9d_club_eval.log

**The lever guard.** Both arms are produced by monkeypatching
``engineer.as_of_club`` to return the stamped ``team_code`` — the smallest
possible intervention, running the identical code path on both sides. Before
anything is reported, ``main`` asserts that the real ``as_of_club`` differs
from ``team_code`` on a non-zero number of rows. If the training frame carries
no ``club_code`` the two arms are the same arm and every number below is a
decorated zero, which reads exactly like a clean negative result. v9c learned
this twice (its run-2 zeros); the script exits rather than printing one.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from gaffer.features import engineer

_REAL = engineer.as_of_club


def _stamped(df: pd.DataFrame) -> pd.Series:
    """The pre-v9d answer: whatever the store stamped on the row today."""
    return df["team_code"]


def _frame() -> tuple[pd.DataFrame, pd.DataFrame | None, pd.DataFrame | None]:
    """The training frame plus the two side inputs the switches read."""
    from gaffer.data import store
    from gaffer.models.train import load_training_frame

    df, _tg, _ = load_training_frame()
    rolled = (engineer.add_understat_team_rolling(store.load("history/understat_team.parquet"))
              if store.exists("history/understat_team.parquet") else None)
    cups = (store.load("history/cups.parquet")
            if store.exists("history/cups.parquet") else None)
    return df, rolled, cups


def _own_cols(frame: pd.DataFrame) -> list[str]:
    return [c for c in frame.columns
            if c.startswith("team_") and c.endswith(tuple(
                f"_r{w}" for w in engineer.TEAM_US_WINDOWS))]


def _differs(left: pd.Series, right: pd.Series) -> pd.Series:
    """Elementwise inequality that counts NaN-vs-value as a difference and
    NaN-vs-NaN as a match. ``!=`` alone calls two NaNs different, which would
    report every unmatched row as a change."""
    both_nan = left.isna() & right.isna()
    return (~both_nan) & (left.ne(right) | (left.isna() ^ right.isna()))


def understat_block(df: pd.DataFrame, rolled: pd.DataFrame | None) -> dict:
    on = engineer.merge_understat_team(df, rolled)
    engineer.as_of_club = _stamped
    try:
        off = engineer.merge_understat_team(df, rolled)
    finally:
        engineer.as_of_club = _REAL
    cols = _own_cols(on)
    changed = pd.Series(False, index=on.index)
    for col in cols:
        changed |= _differs(on[col], off[col])
    return {
        "rows": int(len(df)),
        "own_columns": len(cols),
        "changed_rows": int(changed.sum()),
        "changed_share": round(float(changed.mean()), 6),
        "match_rate_on": round(float(on[cols[0]].notna().mean()), 6),
        "match_rate_off": round(float(off[cols[0]].notna().mean()), 6),
    }


def congestion_block(df: pd.DataFrame, cups: pd.DataFrame | None) -> dict:
    col = "matches_last_14d"
    on = engineer.add_congestion(df, cups)[col]
    engineer.as_of_club = _stamped
    try:
        off = engineer.add_congestion(df, cups)[col]
    finally:
        engineer.as_of_club = _REAL
    changed = _differs(on, off)
    delta = (on - off).abs()
    return {
        "rows": int(len(df)),
        "changed_rows": int(changed.sum()),
        "changed_share": round(float(changed.mean()), 6),
        "mean_abs_change_on_changed_rows": (
            round(float(delta[changed].mean()), 4) if changed.any() else 0.0),
        "mean_on": round(float(np.nanmean(on)), 4),
        "mean_off": round(float(np.nanmean(off)), 4),
    }


def main() -> None:
    df, rolled, cups = _frame()

    diverging = int((_REAL(df) != df["team_code"]).sum())
    if diverging == 0:
        raise SystemExit(
            "the lever is disconnected: as_of_club equals team_code on every "
            "row of the training frame, so both arms below would be the same "
            "arm and every number a decorated zero. Check that "
            "load_training_frame still derives club_code (v9c A7).")

    out = {
        "diverging_rows": diverging,
        "diverging_share": round(diverging / max(len(df), 1), 6),
        "understat": understat_block(df, rolled),
        "congestion": congestion_block(df, cups),
    }
    print("V9D_CLUB_UNDERSTAT", json.dumps(out["understat"]), flush=True)
    print("V9D_CLUB_CONGESTION", json.dumps(out["congestion"]), flush=True)
    print("V9D_CLUB_DONE", json.dumps(out), flush=True)

    if out["understat"]["match_rate_on"] < out["understat"]["match_rate_off"]:
        # Reported, not silenced: spec §1's sanity check is that the switched
        # join resolves no fewer rows than the unswitched one.
        print("V9D_CLUB_MATCH_RATE_REGRESSED", flush=True)

    Path("reports").mkdir(exist_ok=True)
    Path("reports/v9d_club_eval.json").write_text(
        json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
