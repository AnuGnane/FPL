"""Re-derive BPS and bonus under the 2026/27 rules.

Stored history was scored under the old rules, so the bonus model's target
and its BPS features silently mean two different things either side of the
2026/27 boundary. These are pure functions over a player-match frame — no
I/O, no config reads — so the caller decides which season counts as
"current" and callers in training and serving can share one adjusted
history (no train/serve skew).

The 2026/27 change (premierleague.com/en/news/4679946) has two halves and we
can only reproduce one. Clearances/blocks/interceptions now earn 1 BPS per
*three* actions instead of per two, which the stored ``cbi`` count lets us
correct exactly. The -1 BPS for being tackled was removed, and no public
source carries a times-tackled column — so old-season BPS here slightly
*underestimates* new-rules BPS for players who are dispossessed often. That
is a known, deliberate approximation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def adjust_bps(df: pd.DataFrame, current_idx: int) -> pd.Series:
    """Per-row BPS restated under the 2026/27 CBI rule.

    ``bps + floor(cbi/3) - floor(cbi/2)`` — a non-positive delta — for rows
    older than ``current_idx``. Rows at or after ``current_idx`` were already
    scored under the new rules and come back untouched. A missing ``cbi``
    (every season before 2025/26) means there is nothing to correct, so the
    delta is zero rather than NaN; a missing ``bps`` stays missing.
    """
    bps = pd.to_numeric(df["bps"], errors="coerce")
    if "cbi" in df.columns:
        cbi = pd.to_numeric(df["cbi"], errors="coerce").fillna(0.0)
    else:
        cbi = pd.Series(0.0, index=df.index, dtype="float64")
    delta = np.floor(cbi / 3.0) - np.floor(cbi / 2.0)
    old = pd.to_numeric(df["season_idx"], errors="coerce") < current_idx
    return bps + delta.where(old, 0.0)


def fixture_pair(df: pd.DataFrame) -> pd.Series:
    """The unordered ``{team_code, opp_code}`` pair as a stable string.

    Both sides of one match have to land in the same bonus ranking, and they
    carry the pair the other way round, so the key sorts the two codes before
    joining them.
    """
    a = pd.to_numeric(df["team_code"], errors="coerce")
    b = pd.to_numeric(df["opp_code"], errors="coerce")
    lo = np.minimum(a, b)
    hi = np.maximum(a, b)
    return (pd.Series(lo, index=df.index).astype("string") + "-"
            + pd.Series(hi, index=df.index).astype("string"))


def award_bonus(values: list[float]) -> list[int]:
    """FPL bonus for one fixture's BPS values, published tie rules included.

    Ranked descending on distinct values:

    * tie for 1st among two -> ``3, 3`` then the next player takes 1 (the 2
      is skipped, because it would have gone to the second of the two);
    * tie for 1st among three or more -> every tied player takes 3 and
      nothing else is awarded;
    * tie for 2nd -> every tied player takes 2 and no 1 is awarded;
    * tie for 3rd -> every tied player takes 1.

    A fixture with no ties awards exactly 6 points; a tied one awards more,
    which is the real game's behaviour, not a bug.
    """
    out = [0] * len(values)
    distinct = sorted(set(values), reverse=True)
    groups = [[i for i, v in enumerate(values) if v == d] for d in distinct]
    if not groups:
        return out
    for i in groups[0]:
        out[i] = 3
    if len(groups[0]) >= 3:
        return out
    if len(groups[0]) == 2:
        if len(groups) > 1:
            for i in groups[1]:
                out[i] = 1
        return out
    if len(groups) > 1:
        for i in groups[1]:
            out[i] = 2
        if len(groups[1]) >= 2:
            return out
        if len(groups) > 2:
            for i in groups[2]:
                out[i] = 1
    return out


def rederive_bonus(df: pd.DataFrame,
                   bps: pd.Series | None = None) -> pd.Series:
    """Bonus points re-awarded per fixture from (adjusted) BPS.

    Fixtures are ``(season_idx, gw, kickoff_time, fixture_pair)``: the
    kickoff is what separates a double gameweek's two matches, which share
    every other part of the key. ``bps`` defaults to the frame's own column
    so the function is usable on unadjusted history too.

    Only appearances are ranked. A player on zero minutes carries a zero BPS
    that would otherwise tie with every other absentee and, in a fixture
    where nobody scored, could be handed bonus the real game never awarded.
    """
    values = (pd.to_numeric(df["bps"], errors="coerce") if bps is None
              else pd.to_numeric(bps, errors="coerce"))
    if "minutes" in df.columns:
        minutes = pd.to_numeric(df["minutes"], errors="coerce").fillna(0.0)
    else:
        minutes = pd.Series(1.0, index=df.index, dtype="float64")
    out = pd.Series(0.0, index=df.index, dtype="float64")
    out[values.isna()] = float("nan")

    eligible = values.notna() & (minutes > 0)
    if not eligible.any():
        return out
    key = pd.Series(
        list(zip(df["season_idx"], df["gw"],
                 df["kickoff_time"].astype("string"), fixture_pair(df))),
        index=df.index)
    for _, idx in values[eligible].groupby(key[eligible]).groups.items():
        awards = award_bonus([float(v) for v in values.loc[idx]])
        out.loc[idx] = [float(a) for a in awards]
    return out
