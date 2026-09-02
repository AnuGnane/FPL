"""What the classifier would have done, banked whether or not it did it.

The N2 pattern, applied to F5: the verdicts are logged from the first run,
the serving flag stays off, and a season of "would have" against "did happen"
is what decides whether the flag ever gets flipped. Deleting the log to save
the flip a week of history is how a cycle ends with an unmeasurable feature.

Never raises: instrumentation does not block advice.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from gaffer.data import store
from gaffer.io import atomic_save

PRESSER_PATH = "live/presser_log.parquet"

PRESSER_COLS = ["season", "gw", "code", "verdict", "confidence",
                "p_play_before", "p_play_would", "run_at"]

PRESSER_DAMP = 0.8
"""What a ``rotation_risk`` verdict would multiply the first gameweek by.

Deliberately blunter than the line-up damp: a quote hinting at rotation is
weaker evidence than a published team sheet omitting him, and a number this
side of the ceiling cannot be the thing that benches a captain even if the
flag is flipped.
"""


def would_factor(verdict) -> float:
    """The factor serving *would* apply for a verdict (spec §5).

    Only ``rotation_risk`` moves a number. ``ruled_out``, ``knock`` and
    ``assess`` are claims the structured feed already carries — premierinjuries
    prints the status and the date, and damping again would count one injury
    twice. ``confirmed_starter`` is informational: the codebase's standing
    rule is that news lowers a number and never raises one.
    """
    return PRESSER_DAMP if str(verdict) == "rotation_risk" else 1.0


def presser_rows(frame: pd.DataFrame, season: str, gw: int,
                 run_at: str | None = None) -> pd.DataFrame:
    """One row per classified player, with before and would side by side."""
    if "llm_verdict" not in frame.columns:
        return pd.DataFrame(columns=PRESSER_COLS)
    part = frame[frame["llm_verdict"].notna()].copy()
    if part.empty:
        return pd.DataFrame(columns=PRESSER_COLS)
    part = part.drop_duplicates(subset=["code"])
    before = pd.to_numeric(part["p_play"], errors="coerce")
    factor = part["llm_verdict"].map(would_factor).astype("float64")
    out = pd.DataFrame({
        "season": str(season or ""),
        "gw": int(gw),
        "code": pd.to_numeric(part["code"], errors="coerce").astype("int64"),
        "verdict": part["llm_verdict"].astype("string"),
        "confidence": pd.to_numeric(part.get("llm_confidence"),
                                    errors="coerce"),
        "p_play_before": before,
        "p_play_would": before * factor,
        "run_at": str(run_at or datetime.now(timezone.utc).isoformat())})
    return out[PRESSER_COLS].reset_index(drop=True)


def append_presser(rows: pd.DataFrame) -> int:
    """Append ``rows``, atomically, deduplicated on the run's own key.

    Append-by-rewrite through :func:`gaffer.io.atomic_save`, the same trade
    :func:`gaffer.snapshot.append_snapshot` makes: a job killed mid-parquet
    must not cost a season of history to save one afternoon. Two writes of one
    run bank once, so a hand re-run is free.

    v12 W1 §2.11: the temp name carries this process's pid now, where it used
    to be a single shared ``.tmp``. The scheduled snapshot job and a hand-run
    ``gaffer snapshot`` are exactly the two writers that shared it.
    """
    if rows is None or rows.empty:
        return 0
    existing = (store.load(PRESSER_PATH) if store.exists(PRESSER_PATH)
                else pd.DataFrame(columns=PRESSER_COLS))
    for col in PRESSER_COLS:
        if col not in existing.columns:
            existing[col] = None
    frames = [f[PRESSER_COLS] for f in (existing, rows) if not f.empty]
    merged = pd.concat(frames, ignore_index=True).drop_duplicates(
        subset=["season", "gw", "code", "run_at"], keep="last")
    atomic_save(merged, PRESSER_PATH)
    return int(len(rows))


def load_presser_log() -> pd.DataFrame:
    """Every banked verdict, or an empty frame with the right columns."""
    if not store.exists(PRESSER_PATH):
        return pd.DataFrame(columns=PRESSER_COLS)
    return store.load(PRESSER_PATH)


def write_presser(frame: pd.DataFrame, season: str, gw: int) -> int:
    """Bank one run's verdicts. Rows written, or ``0`` on any failure."""
    try:
        return append_presser(presser_rows(frame, season, gw))
    except Exception as exc:  # noqa: BLE001 — instrumentation never blocks
        print(f"news: presser log not written ({exc})")
        return 0
