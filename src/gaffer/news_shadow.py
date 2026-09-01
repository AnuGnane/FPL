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

from gaffer.config import load_config
from gaffer.data import store

SHADOW_PATH = "live/news_shadow.parquet"

SHADOW_COLS = ["season", "gw", "code", "p_play_news", "p_play_flags",
               "e_min_news", "e_min_flags", "p_play_presser", "run_at"]
"""v10 §F2b adds ``p_play_presser`` beside the other prediction columns and
before ``run_at``, which stays last: the stamp is metadata and every reader of
this parquet — the scorer, the digest, a human with ``parquet-tools`` —
expects it there."""

REQUIRED_INPUT = ("code", "gw", "p_play", "p_play_flags", "e_min",
                  "e_min_flags")


def shadow_rows(comp: pd.DataFrame, gw: int,
                run_at: str | None = None,
                season: str = "") -> pd.DataFrame:
    """The component frame -> one shadow row per player, for ``gw`` only.

    Only the first gameweek of the horizon: the scorer joins these against
    actual minutes, and a GW+1 row would be scored against the wrong week.
    A double gameweek collapses to one row, but not by one rule: ``p_play`` is
    the *mean* of the fixtures because "did he turn out at all" is a single
    outcome, while ``e_min`` is their *sum*, because the scorer's MAE is
    against the gameweek's total minutes and a doubled-up player really is
    expected to play both matches.
    """
    rows = comp[comp["gw"] == int(gw)]
    grouped = rows.groupby("code", as_index=False).agg(
        p_play_news=("p_play", "mean"),
        p_play_flags=("p_play_flags", "mean"),
        e_min_news=("e_min", "sum"),
        e_min_flags=("e_min_flags", "sum"))
    grouped.insert(0, "gw", int(gw))
    # The log outlives a season rollover and gameweek 5 comes round again;
    # without this the scorer's key collides across years.
    grouped.insert(0, "season", str(season or ""))
    # v10 §F2b (specs/2026-09-01-gaffer-v10-minutes-design.md): what the
    # presser classifier *would* have done, beside what the news layer did.
    # Joined from the presser log rather than carried on ``comp``, because
    # ``apply_availability`` drops ``llm_verdict`` before ``predict_components``
    # ever sees it and ``advise.py`` — which names the carried columns — is
    # protected. The log is already on disk by this point: ``write_presser``
    # runs inside ``apply_availability``, one line before ``write_shadow``
    # is called (advise.py:585-586).
    grouped["p_play_presser"] = grouped["p_play_news"] * _presser_factors(
        grouped["code"], season, gw)
    grouped["run_at"] = run_at or datetime.now(timezone.utc).isoformat(
        timespec="seconds")
    return grouped[SHADOW_COLS]


def _presser_factors(codes: pd.Series, season: str, gw: int) -> pd.Series:
    """``would_factor`` per code for this ``(season, gw)``, ``1.0`` elsewhere.

    ``1.0`` and never null: a player the classifier never saw has no opinion
    recorded against him, and "no opinion" is arithmetically "no change". A
    null would lose him from the scorer's join instead, which is the one
    outcome that would make the third side unreadable.

    Its own ``try``, returning all-``1.0`` on anything at all. The presser log
    is instrumentation and ``would_factor`` never raises, but a corrupt
    parquet still can — and instrumentation does not block *other*
    instrumentation.
    """
    ones = pd.Series(1.0, index=codes.index, dtype="float64")
    try:
        from gaffer.data.news.presser_log import load_presser_log, would_factor

        log = load_presser_log()
        if log is None or log.empty:
            return ones
        part = log[(log["season"].astype(str) == str(season or ""))
                   & (pd.to_numeric(log["gw"], errors="coerce") == int(gw))]
        if part.empty:
            return ones
        factor = (part.assign(
            _code=pd.to_numeric(part["code"], errors="coerce"),
            _f=part["verdict"].map(would_factor).astype("float64"))
            .dropna(subset=["_code"])
            .drop_duplicates(subset=["_code"], keep="last")
            .set_index("_code")["_f"])
        return (pd.to_numeric(codes, errors="coerce").map(factor)
                .astype("float64").fillna(1.0))
    except Exception as exc:  # noqa: BLE001 — instrumentation never blocks
        print(f"news shadow: presser factors not joined ({exc})")
        return ones


def _current_season() -> str:
    """``cfg.current_season``, or ``""`` when there is no readable config.

    Read here rather than passed in, so the one line in ``run_advise`` stays
    one line. Its own try, because the shadow log is instrumentation: a
    machine with no config.toml must still bank the week.
    """
    try:
        return str(load_config().current_season or "")
    except Exception:  # noqa: BLE001 — instrumentation never blocks
        return ""


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
        rows = shadow_rows(comp, gw, season=_current_season())
        if rows.empty:
            return None
        tied = ((rows["p_play_news"] - rows["p_play_flags"]).abs() < 1e-12) \
            & ((rows["e_min_news"] - rows["e_min_flags"]).abs() < 1e-9)
        if bool(tied.all()):
            return None
        existing = (store.load(SHADOW_PATH) if store.exists(SHADOW_PATH)
                    else pd.DataFrame(columns=SHADOW_COLS))
        # A parquet banked before a column existed reads back: the reindex
        # that v8-era code did for ``season`` alone generalises to the whole
        # of SHADOW_COLS, so v10's p_play_presser needs no second special
        # case and neither will the next one.
        for col in SHADOW_COLS:
            if col not in existing.columns:
                existing = existing.assign(
                    **{col: "" if col == "season" else float("nan")})
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
