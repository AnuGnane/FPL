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
