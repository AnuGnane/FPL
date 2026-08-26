"""Gate N2's instrumentation: what the news layer changed, banked weekly.

The news half of v5 cannot be backtested — there is no archive of what the
injury press said on a Friday in 2023 — so its verdict has to accrue forward.
Every advise run with news active writes one row per pool player per gameweek:
the news prediction, the flags-only prediction, and nothing else.
``gaffer evaluate --news-shadow`` scores them once the gameweek is played.

The flags-only side costs one extra ``apply_availability`` call on the same
model output. The model runs once (spec §9).

Nothing here may raise. An advise run that fails because its instrumentation
failed is worse than an unmeasured one.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from gaffer.data import store

SHADOW_PATH = "live/news_shadow.parquet"

SHADOW_COLS = ["gw", "code", "p_play_news", "p_play_flags", "e_min_news",
               "e_min_flags", "run_at"]

REQUIRED_INPUT = ("code", "gw", "p_play", "p_play_flags", "e_min",
                  "e_min_flags")


def shadow_rows(comp: pd.DataFrame, gw: int,
                run_at: str | None = None) -> pd.DataFrame:
    """The component frame -> one shadow row per player, for ``gw`` only.

    Only the first gameweek of the horizon: the scorer joins these against
    actual minutes, and a GW+1 row would be scored against the wrong week.
    Double gameweeks are averaged rather than duplicated — two fixtures are
    one "did he play at all" outcome.
    """
    rows = comp[comp["gw"] == int(gw)]
    grouped = rows.groupby("code", as_index=False).agg(
        p_play_news=("p_play", "mean"),
        p_play_flags=("p_play_flags", "mean"),
        e_min_news=("e_min", "mean"),
        e_min_flags=("e_min_flags", "mean"))
    grouped.insert(0, "gw", int(gw))
    grouped["run_at"] = run_at or datetime.now(timezone.utc).isoformat(
        timespec="seconds")
    return grouped[SHADOW_COLS]


def write_shadow(comp, gw: int):
    """Append this run's shadow rows to ``data/live/news_shadow.parquet``.

    Returns the path written, or ``None`` when there is nothing to bank: a
    frame without the flags columns (news disabled, or an older component
    file), or a run where every row is tied because no source had anything to
    say. Never raises — the caller is one line inside ``run_advise`` and an
    advise run must not die of its own instrumentation.
    """
    try:
        if comp is None or not set(REQUIRED_INPUT) <= set(comp.columns):
            return None
        rows = shadow_rows(comp, gw)
        if rows.empty:
            return None
        tied = ((rows["p_play_news"] - rows["p_play_flags"]).abs() < 1e-12) \
            & ((rows["e_min_news"] - rows["e_min_flags"]).abs() < 1e-9)
        if bool(tied.all()):
            return None
        existing = (store.load(SHADOW_PATH) if store.exists(SHADOW_PATH)
                    else pd.DataFrame(columns=SHADOW_COLS))
        merged = pd.concat([existing, rows], ignore_index=True)
        return store.save(merged[SHADOW_COLS], SHADOW_PATH)
    except Exception as exc:  # noqa: BLE001 — instrumentation never blocks
        print(f"news shadow log not written: {exc}")
        return None


def load_shadow() -> pd.DataFrame:
    """Every banked shadow row, or an empty frame with the right columns."""
    if not store.exists(SHADOW_PATH):
        return pd.DataFrame(columns=SHADOW_COLS)
    return store.load(SHADOW_PATH)
