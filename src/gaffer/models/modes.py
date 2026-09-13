"""The three modes a player's gameweek can be in, and the label for one.

The vocabulary the minutes model and its DNP calibrator both speak. It sat
in ``gaffer.models.minutes`` until v18d §2, where it was the whole reason
``dnp_calibrate`` reached back into ``minutes`` from inside a function body:
``minutes`` imports the fitter at module scope, so the reverse edge could
never be a top-level import. A leaf module owns the vocabulary instead and
both sides import it the ordinary way.
"""

from __future__ import annotations

import pandas as pd

DNP, SUB, START = 0, 1, 2
MODE_COLS = ["p_dnp", "p_sub", "p_start"]
SIXTY_MINUTES = 60


def mode_labels(df: pd.DataFrame) -> pd.Series:
    """{0 DNP, 1 sub, 2 start} from ``starts`` and ``minutes``.

    ``starts`` is the FPL feed's own flag and is present from 2022-23, which
    is every season in ``train_seasons``. Where it is missing the label falls
    back to the 60-minute threshold, which is what the old model used for
    everything and is wrong only for the cameo-heavy tail — better than
    dropping a season.
    """
    mins = pd.to_numeric(df["minutes"], errors="coerce").fillna(0.0)
    starts = (pd.to_numeric(df["starts"], errors="coerce")
              if "starts" in df.columns
              else pd.Series(float("nan"), index=df.index))
    starts = starts.fillna((mins >= SIXTY_MINUTES).astype("float64"))
    label = pd.Series(DNP, index=df.index, dtype="int64")
    label[mins > 0] = SUB
    # ``>= 1`` rather than ``== 1``: the column is a count, and a double
    # gameweek's aggregated row carries a 2.
    label[(mins > 0) & (starts >= 1)] = START
    return label
