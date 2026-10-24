"""B8's precondition: is Understat still feeding the banked xG?

ROADMAP candidate 8 ("B8 FotMob xG fallback — only if Understat goes down";
GUIDE §12.5 item 8), the one candidate with no reading in §12.5's table
(holiday F-80). The fallback is only worth a spec once Understat has stopped,
so this reads whether it has.

The frames are ``history/understat_team.parquet`` and
``history/understat_player.parquet`` (``data/understat.py``'s
``UNDERSTAT_TEAM_PATH`` and ``UNDERSTAT_PLAYER_PATH``), read through
``store``. Neither carries a gameweek: ``TEAM_COLS`` has ``season`` and
``date``, ``PLAYER_COLS`` has ``match_id`` and ``date`` and no ``season``
(``data/understat.py:34-38``). So team rows are cut to the configured
``current_season``, player rows to the season's date span (the first
deadline to ``SPAN_TAIL_DAYS`` after the last), and each row's ``date`` is
mapped to the gameweek whose deadline is the latest on or before it, by the
deadlines ``availability_eval.deadlines(load_events())`` gives, as
``scripts/b1_status_age.py`` reads them.

The line carries, per frame, the gameweeks with rows and the newest row's
date; and the gap: the gameweeks of ``live/player_gw.parquet`` that have
results but no Understat rows in either frame, each with its age, the whole
days from the gameweek's end (the next gameweek's deadline, or
``SPAN_TAIL_DAYS`` after the last deadline) to the reading's day.

The rule, written here before the script has run on real data (a ruling,
Anu's): the fallback earns a spec iff a gameweek whose results are banked has
carried no Understat rows for ``GAP_DAYS`` (7) days or more; otherwise
"Understat is up". Measuring from the gameweek's end, not its deadline, keeps
a gameweek whose matches are still being played from reading as a gap.

No network call: the script reads the banked parquet only, so it says what
the last refresh saw, not what Understat serves today. A refresh that stopped
running reads the same as Understat going down, and the newest row's date is
there to tell the two apart by eye. Read-only: it writes nothing. A missing
parquet, no events or no config prints the line with a reason, never a
traceback, because the night shift transcribes the line whatever it says.

    uv run python scripts/b8_understat_cover.py
"""

from __future__ import annotations

import json

import pandas as pd

from gaffer.availability_eval import deadlines, load_events
from gaffer.data import store
from gaffer.data.understat import UNDERSTAT_PLAYER_PATH, UNDERSTAT_TEAM_PATH
from gaffer.evaluation import news_actuals

GAP_DAYS = 7
"""The pre-registered rule (holiday F-80's default)."""

SPAN_TAIL_DAYS = 7
"""Days after the last deadline the season's matches can still fall in."""


def _load(rel: str) -> pd.DataFrame | None:
    return store.load(rel) if store.exists(rel) else None


def _dates(frame: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(frame["date"], errors="coerce", utc=True,
                          format="mixed")


def to_gw(dates: pd.Series, by_gw: dict[int, pd.Timestamp]) -> pd.Series:
    """Each date's gameweek: the latest deadline day on or before it, else NaN.

    Understat banks a bare day (``data/understat.py``'s ``.date()``), which
    parses to midnight, so a deadline is compared by its day: a Friday opener
    on deadline day is that gameweek's, not the one before.
    """
    gws = sorted(by_gw)
    marks = pd.Series([by_gw[g].normalize() for g in gws])
    pos = marks.searchsorted(dates, side="right") - 1
    return pd.Series([gws[p] if p >= 0 else float("nan") for p in pos],
                     index=dates.index, dtype="float")


def _gw_end(gw: int, by_gw: dict[int, pd.Timestamp]) -> pd.Timestamp:
    later = [g for g in by_gw if g > gw]
    if later:
        return by_gw[min(later)]
    return by_gw[gw] + pd.Timedelta(days=SPAN_TAIL_DAYS)


def _frame_cover(frame: pd.DataFrame | None, by_gw: dict,
                 season: str, cut_season: bool) -> dict:
    if frame is None or frame.empty or "date" not in frame.columns:
        return {"rows": 0, "gws": [], "newest": None}
    if cut_season:
        if "season" not in frame.columns:
            return {"rows": 0, "gws": [], "newest": None}
        frame = frame[frame["season"].astype(str) == season]
    dates = _dates(frame).dropna()
    start = min(by_gw.values()).normalize()
    stop = max(by_gw.values()) + pd.Timedelta(days=SPAN_TAIL_DAYS)
    dates = dates[(dates >= start) & (dates <= stop)]
    gws = to_gw(dates, by_gw).dropna()
    return {"rows": len(dates),
            "gws": sorted({int(g) for g in gws}),
            "newest": (dates.max().date().isoformat()
                       if len(dates) else None)}


def _empty(reason: str, season: str) -> dict:
    return {"season": season, "team": None, "player": None, "gaps": [],
            "verdict": None, "reason": reason}


def understat_reading(team: pd.DataFrame | None, player: pd.DataFrame | None,
                      events: pd.DataFrame | None,
                      actuals: pd.DataFrame | None, season: str,
                      today: pd.Timestamp) -> dict:
    """The ``B8_UNDERSTAT`` payload for the banked frames on ``today``."""
    if not season:
        return _empty("no configured season: team rows are cut by it", season)
    by_gw = deadlines(events)
    if not by_gw:
        return _empty("no gameweek has a readable deadline", season)
    team_cover = _frame_cover(team, by_gw, season, cut_season=True)
    player_cover = _frame_cover(player, by_gw, season, cut_season=False)
    if actuals is None or actuals.empty or "gw" not in actuals.columns:
        result_gws: list[int] = []
    else:
        result_gws = sorted({int(g) for g in actuals["gw"].dropna()})
    seen = set(team_cover["gws"]) | set(player_cover["gws"])
    day = pd.Timestamp(today).tz_localize(None).normalize()
    gaps = []
    for gw in result_gws:
        if gw in seen or gw not in by_gw:
            continue
        end = _gw_end(gw, by_gw).tz_localize(None).normalize()
        gaps.append({"gw": gw, "days": int((day - end).days)})
    stale = [g for g in gaps if g["days"] >= GAP_DAYS]
    if team is None and player is None:
        verdict = None
    elif stale:
        verdict = ("the fallback earns a spec: no Understat rows for "
                   + ", ".join(f"GW{g['gw']} ({g['days']}d)" for g in stale))
    else:
        verdict = "Understat is up"
    reason = None
    if team is None and player is None:
        reason = "no Understat parquet banked"
    elif not result_gws:
        reason = "no results: live/player_gw.parquet is missing or empty"
    return {"season": season, "team": team_cover, "player": player_cover,
            "results_gws": result_gws, "gaps": gaps, "verdict": verdict,
            "reason": reason}


def _season() -> str:
    """The configured season, or ``""``, which reads as no reading."""
    try:
        from gaffer.config import load_config

        return str(load_config().current_season or "")
    except Exception:  # noqa: BLE001 — a missing config becomes the no-season line, never a traceback
        return ""


def main() -> int:
    """Read the banked Understat files and print the ``B8_UNDERSTAT`` verdict
    line."""
    season = _season()
    try:
        payload = understat_reading(
            _load(UNDERSTAT_TEAM_PATH), _load(UNDERSTAT_PLAYER_PATH),
            load_events(), news_actuals(), season,
            pd.Timestamp.now(tz="UTC"))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        # A corrupt parquet raises ArrowInvalid (a ValueError).
        payload = _empty(f"a parquet is unreadable: {type(exc).__name__}",
                         season)
    print(f"B8_UNDERSTAT {json.dumps(payload, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
