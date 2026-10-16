"""C1's replay half, step zero: which seasons and gameweeks the two logs cover.

ROADMAP candidate 1 (GUIDE §12.5 item 1) and v20 spec §4 ("buckets plus a
K ≥ 5 replay … the same two-half shape; it would be v20e"). The replay
applies no availability layer in either mode (``backtest.run_backtest``'s
docstring: "the replay applies no availability filtering in either mode"), so
an ablation of the news layer in the replay needs the layer's inputs banked
for the season it replays. Before that half can be designed the Mac needs to
know what the logs hold (holiday F-79).

Two logs are read: the news shadow log (``news_shadow.load_shadow()``,
``live/news_shadow.parquet``) and the availability snapshot log
(``snapshot.load_snapshot_log()``, as ``scripts/b1_status_age.py`` reads it).
For each, per season present: the row count, the gameweek span, and the share
of the gameweeks ``START_GW`` (``run_backtest``'s default, 5) to ``LAST_GW``
(38) that carry at least one row, with the missing ones named; rows with no
gameweek or no season label are counted apart (``unlabelled``).

The rule, written here before the script has run on real data: the replay
half is runnable iff one season the replay can take as ``run_backtest``'s
``season`` (one of the configured ``train_seasons``, the list
``run_backtest`` indexes) carries shadow rows for every gameweek from
``START_GW`` to ``LAST_GW``. Otherwise it reads "the replay half waits on a
season of the shadow log", naming the first season that could qualify: the
earliest shadow season with no gap so far from ``START_GW`` (one that is
complete but not yet replayable, or the current season in progress; a past
season whose log stopped short of ``LAST_GW`` is passed over), else the season
after the newest in the log, else, with no shadow log at all, the configured
``current_season``. The shadow log is this season's, v5 on, so the current
season is the first that can qualify, and only once the replay can read its
results. The verdict is an arm, the Mac's; the snapshot log is reported
beside it and decides nothing.

Read-only. It imports the readers and edits none of them, writes nothing, fits
no model and runs no replay. A missing log, or no config, prints the line with
a reason, never a traceback, because the night shift transcribes the line
whatever it says.

    uv run python scripts/c1_replay_cover.py
"""

from __future__ import annotations

import json

import pandas as pd

from gaffer.news_shadow import load_shadow
from gaffer.snapshot import load_snapshot_log

START_GW = 5
"""``run_backtest``'s default ``start_gw``, the first gameweek it replays."""

LAST_GW = 38
"""``run_backtest`` replays to GW38."""


def _window() -> list[int]:
    return list(range(START_GW, LAST_GW + 1))


def season_cover(log: pd.DataFrame | None) -> dict:
    """Per season in ``log``: rows, gameweek span and the window's coverage."""
    if log is None or log.empty or not {"season", "gw"} <= set(log.columns):
        return {}
    frame = log[["season", "gw"]].dropna(subset=["gw"])
    labels = frame["season"].fillna("").astype(str).str.strip()
    frame = frame[~labels.isin(["", "nan", "None"])]
    window = _window()
    out = {}
    for season, part in frame.groupby(frame["season"].astype(str), sort=True):
        gws = {int(g) for g in part["gw"]}
        missing = [gw for gw in window if gw not in gws]
        covered = len(window) - len(missing)
        out[season] = {
            "rows": int(len(part)),
            "gw_min": min(gws),
            "gw_max": max(gws),
            "covered": covered,
            "of": len(window),
            "share": round(covered / len(window), 4),
            "missing": missing,
        }
    return out


def _next_season(season: str) -> str:
    """``"2026-27"`` → ``"2027-28"``; ``""`` when the label does not parse."""
    try:
        first = int(season.split("-")[0])
    except ValueError:
        return ""
    return f"{first + 1}-{(first + 2) % 100:02d}"


def _no_gap_so_far(cell: dict) -> bool:
    """True when every window gameweek up to the season's newest is present."""
    reached = [gw for gw in cell["missing"] if gw <= cell["gw_max"]]
    return not reached and cell["gw_max"] >= START_GW


def unlabelled(log: pd.DataFrame | None) -> int:
    """Rows ``season_cover`` cannot place: no gameweek, or no season label.

    Shadow rows banked before the ``season`` column existed read back with
    ``""`` (``news_shadow``'s reindex), so they are counted here rather than
    read as a season of their own.
    """
    if log is None or log.empty or not {"season", "gw"} <= set(log.columns):
        return 0
    labels = log["season"].fillna("").astype(str).str.strip()
    return int((log["gw"].isna() | labels.isin(["", "nan", "None"])).sum())


def first_candidate(shadow: dict, current_season: str) -> str:
    """The first season that could qualify, by the docstring's rule.

    A season other than the current one whose log stopped short of
    ``LAST_GW`` can never be completed, so it is passed over.
    """
    for season, cell in shadow.items():
        stalled = season != current_season and cell["gw_max"] < LAST_GW
        if _no_gap_so_far(cell) and not stalled:
            return season
    if shadow:
        return _next_season(max(shadow))
    return current_season


def cover_reading(shadow_log: pd.DataFrame | None,
                  snapshot_log: pd.DataFrame | None,
                  replayable: list[str], current_season: str = "") -> dict:
    """The ``C1_COVER`` payload for the two logs and the replayable seasons."""
    shadow = season_cover(shadow_log)
    snapshot = season_cover(snapshot_log)
    base = {"start_gw": START_GW, "last_gw": LAST_GW,
            "current_season": current_season,
            "replayable": sorted(replayable),
            "shadow": shadow, "snapshot": snapshot,
            "unlabelled": {"shadow": unlabelled(shadow_log),
                           "snapshot": unlabelled(snapshot_log)}}
    qualifying = sorted(season for season, cell in shadow.items()
                        if not cell["missing"] and season in replayable)
    candidate = first_candidate(shadow, current_season)
    if qualifying:
        verdict = ("runnable: the shadow log covers GW"
                   f"{START_GW}-{LAST_GW} of {', '.join(qualifying)}")
    else:
        verdict = ("the replay half waits on a season of the shadow log: "
                   f"{candidate or 'the current season'} is the first that "
                   "could qualify")
    if not shadow and not snapshot:
        reason = "no news shadow log and no availability snapshots banked"
    elif not shadow:
        reason = "no news shadow log banked"
    else:
        reason = None
    return {**base, "qualifying": qualifying, "first_candidate": candidate,
            "verdict": verdict, "reason": reason}


def _config() -> tuple[list[str], str]:
    """The configured ``train_seasons`` and ``current_season``, or empties."""
    try:
        from gaffer.config import load_config

        cfg = load_config()
        return ([str(s) for s in (cfg.train_seasons or [])],
                str(cfg.current_season or ""))
    except Exception:  # noqa: BLE001 — a missing config reads as no replayable season, which the verdict then names, never a traceback
        return [], ""


def _read(loader) -> tuple[pd.DataFrame | None, str | None]:
    try:
        return loader(), None
    except (OSError, ValueError, KeyError, TypeError) as exc:
        # A corrupt parquet raises ArrowInvalid (a ValueError).
        return None, type(exc).__name__


def main() -> int:
    replayable, current = _config()
    shadow, shadow_err = _read(load_shadow)
    snapshot, snapshot_err = _read(load_snapshot_log)
    payload = cover_reading(shadow, snapshot, replayable, current)
    errors = [f"{name} unreadable: {err}" for name, err in
              (("shadow log", shadow_err), ("snapshot log", snapshot_err))
              if err]
    if errors:
        payload["reason"] = "; ".join(errors)
    print(f"C1_COVER {json.dumps(payload, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
