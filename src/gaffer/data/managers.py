"""EPL head-coach spells, and the rotation key derived from them.

No head-coach data exists anywhere else in the repo, so v8a ships one: a
committed reference asset (``data/manager_tenures.toml``) in the spirit of
``injury_return_curves.json``. It is *optional at runtime* by design — a clone
without it, or one whose copy is corrupt, gets club-season windows instead of
manager spells and every F1 feature still computes. That degradation is a
rail, not an accident: see ``tests/test_v8a_degradation.py``.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pandas as pd

from gaffer.data import store

MANAGER_TENURES_PATH = "manager_tenures.toml"
"""Relative to ``store.DATA_DIR``. Read at call time, not bound at import, so
a test that redirects the data directory redirects this too."""

TENURE_COLS = ["team_code", "club", "manager", "start_date", "end_date"]


def load_manager_tenures(path: Path | str | None = None
                         ) -> pd.DataFrame | None:
    """The tenure asset as a frame, or ``None`` when there isn't one.

    ``None`` rather than an empty frame, so a caller cannot mistake "no asset"
    for "no club ever changed manager" — the two are opposite instructions to
    :func:`spell_keys`. Every failure lands on ``None``: absent file, invalid
    TOML, no ``[[spell]]`` tables, no parseable ``team_code``.
    """
    dest = (Path(path) if path is not None
            else store.DATA_DIR / MANAGER_TENURES_PATH)
    if not dest.is_file():
        return None
    try:
        raw = tomllib.loads(dest.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — a broken asset degrades, never raises
        return None
    rows = raw.get("spell") or []
    if not rows:
        return None
    out = pd.DataFrame(rows)
    for col in TENURE_COLS:
        if col not in out.columns:
            out[col] = None
    out["team_code"] = pd.to_numeric(out["team_code"], errors="coerce")
    out = out[out["team_code"].notna()].copy()
    if out.empty:
        return None
    out["team_code"] = out["team_code"].astype("int64")
    out["start_date"] = pd.to_datetime(out["start_date"], errors="coerce",
                                       utc=True)
    # An open spell is written as an empty string rather than omitted, so the
    # asset reads as a table; both spellings have to arrive as NaT.
    end = out["end_date"].astype("object").where(
        out["end_date"].astype("object").ne(""), None)
    out["end_date"] = pd.to_datetime(end, errors="coerce", utc=True)
    out = out.dropna(subset=["start_date"])
    if out.empty:
        return None
    return (out[TENURE_COLS].sort_values(["team_code", "start_date"])
            .reset_index(drop=True))


def spell_keys(team_code, kickoff, season_idx,
               tenures: pd.DataFrame | None) -> pd.Series:
    """One string per row naming the manager spell that row's match sits in.

    The key is opaque on purpose — nothing reads it except a ``groupby``. What
    matters is that it changes exactly when the manager does, and that it
    degrades to ``c{club}s{season}`` for any row the asset cannot place: no
    asset at all, a club it does not carry, a date outside every spell, or a
    missing kickoff. A season-scoped club window is the honest fallback,
    because a season boundary is where most managerial change lands anyway.

    Half-open intervals: a spell covers ``start <= t < end``, so a successor
    whose ``start_date`` equals his predecessor's ``end_date`` claims the
    handover date and no match is ever counted twice.
    """
    club = pd.to_numeric(team_code, errors="coerce")
    season = pd.to_numeric(season_idx, errors="coerce")
    fallback = pd.Series(
        [f"c{int(c)}s{int(s)}" if pd.notna(c) and pd.notna(s) else ""
         for c, s in zip(club, season)], index=club.index, dtype="object")
    if tenures is None or tenures.empty:
        return fallback
    when = pd.to_datetime(kickoff, errors="coerce", utc=True)
    by_club: dict[int, list] = {}
    for r in tenures.itertuples():
        by_club.setdefault(int(r.team_code), []).append(
            (r.start_date, r.end_date,
             f"c{int(r.team_code)}m{r.manager}@{r.start_date.date()}"))
    out = []
    for c, t, back in zip(club, when, fallback):
        key = None
        if pd.notna(c) and pd.notna(t):
            for start, end, name in by_club.get(int(c), ()):
                if t >= start and (pd.isna(end) or t < end):
                    key = name
                    break
        out.append(key if key is not None else back)
    return pd.Series(out, index=club.index, dtype="object")
