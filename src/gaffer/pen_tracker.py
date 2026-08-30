"""The v6 penalty term, measured forward: takers predicted vs pens taken.

Read-only over what has already been banked — ``reports/components_gw{N}.parquet``
for what was served, ``data/live/player_gw.parquet`` for the week that happened.
Nothing here trains, fetches, or writes a model input, and nothing here touches
``set_pieces``: it imports the pure functions and constants and leaves the
module alone.

The v6 validation was deferred to season end. This turns that one May
comparison into a standing report that accrues weekly, which is the only
version of it anybody will actually read.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

from gaffer import artifacts
from gaffer.data import store
from gaffer.set_pieces import (GOAL_POINTS, LEAGUE_PENS_PG, PEN_CONVERSION,
                               pen_estimate, share_now)

PLAYER_GW_PATH = "live/player_gw.parquet"
EVENTS_PATH = "live/events.parquet"
UNDERSTAT_PATH = "history/understat_player.parquet"


def tracker_path() -> Path:
    """``reports/pen_tracker.json``, resolved through ``artifacts.REPORTS``.

    Read at call time rather than bound at import, so a test that redirects
    the reports directory redirects the component files and this output
    together.
    """
    return artifacts.REPORTS / "pen_tracker.json"


def finished_gws(events: pd.DataFrame) -> list[int]:
    """Gameweeks the league has actually played, in order.

    Only finished weeks: a gameweek in progress has half its penalties still
    to come, and a tracker that counted it would report a hit rate that moves
    on Sunday for reasons that are not evidence.
    """
    if events is None or "finished" not in events.columns:
        return []
    done = events[events["finished"].astype(bool)]
    return sorted(int(g) for g in done["gw"].unique())


def attach_npxg(rows: pd.DataFrame, season: str) -> pd.DataFrame | None:
    """``rows`` with Understat's ``us_npxg`` joined on (code, UK match date).

    The live parquet has no ``us_npxg`` — Understat is joined in the training
    frame, not the serving one — so the tracker does the join itself, on the
    same key ``models.train.attach_understat`` uses: Understat carries no
    gameweek number, and a player plus a date is unique even in a double
    gameweek.

    ``None`` — not a frame of NaN — when the parquet is missing or has nothing
    for this season, so the caller can tell "no coverage" from "no penalties"
    and name the instrument it fell back to. A season being present is not the
    same as this *week* being present, though: a frame does come back all-NaN
    when the backfill has not reached these fixtures, and
    :func:`realized_pens` is what checks that.
    """
    if not store.exists(UNDERSTAT_PATH):
        return None
    us = store.load(UNDERSTAT_PATH)
    if us.empty or "us_npxg" not in us.columns:
        return None
    us = us[us["season"].astype(str) == str(season)]
    if us.empty:
        return None
    keyed = us[["code", "date", "us_npxg"]].copy()
    keyed["date"] = pd.to_datetime(keyed["date"], errors="coerce").dt.date
    keyed = keyed.drop_duplicates(subset=["code", "date"])
    out = rows.copy()
    out["_date"] = pd.to_datetime(out["kickoff_time"], errors="coerce",
                                  utc=True).dt.tz_convert(
                                      "Europe/London").dt.date
    out = out.merge(keyed.rename(columns={"date": "_date"}),
                    on=["code", "_date"], how="left", validate="many_to_one")
    return out.drop(columns=["_date"])


def realized_pens(rows: pd.DataFrame,
                  season: str) -> tuple[pd.Series, str, int]:
    """Penalties per player-match, the instrument, and the rows it covered.

    The xG-gap estimator when Understat covers *this week*, and otherwise the
    only penalties the FPL feed alone can see: the ones that were *missed*.
    That is a floor rather than a count — every converted spot kick is
    invisible to it — so the fallback is named ``pens_missed_only`` in the
    report and the two are never added together.

    Coverage is checked per week, not per season: :func:`attach_npxg` answers
    "is this season in the parquet", and a mid-season backfill lag leaves the
    latest week joined to nothing but NaN. Calling that an xg gap would report
    every taker as having taken no penalty, which reads as evidence against the
    taker model rather than as the missing data it is. So a week with no joined
    ``us_npxg`` at all falls back and says so.

    ``covered_rows`` is how many rows the join actually landed on — zero on
    both fallback paths, and the number a reader needs to tell a quiet week
    from an unseen one.

    ``rows`` is assumed to carry a fresh range index; the caller resets it.
    """
    joined = attach_npxg(rows, season)
    if joined is not None:
        covered = int(joined["us_npxg"].notna().sum())
        if covered:
            events = pen_estimate(joined)
            if events is not None:
                return (pd.Series(events.to_numpy(), index=rows.index,
                                  dtype="float64"), "xg_gap", covered)
    if "pens_missed" not in rows.columns:
        return pd.Series(0.0, index=rows.index, dtype="float64"), \
            "pens_missed_only", 0
    missed = pd.to_numeric(rows["pens_missed"], errors="coerce").fillna(0.0)
    return missed.astype("float64"), "pens_missed_only", 0


def predicted_ep(gw: int) -> dict:
    """The pen term this gameweek's advise run actually served.

    Read off ``ep_pen_taker``, which ``run_advise`` already rescaled by the
    odds blend — so this is the increment that was *delivered*, not the one
    the model proposed. An absent component file is zeros: the tracker covers
    a whole season and the earliest weeks of one predate the artifact.
    """
    path = artifacts.components_path(gw)
    if not path.exists():
        return {"rows": 0, "ep_pen_taker": 0.0, "takers": 0}
    comp = pd.read_parquet(path)
    if "ep_pen_taker" not in comp.columns:
        return {"rows": int(len(comp)), "ep_pen_taker": 0.0, "takers": 0}
    ep = pd.to_numeric(comp["ep_pen_taker"], errors="coerce").fillna(0.0)
    return {"rows": int(len(comp)),
            "ep_pen_taker": round(float(ep.sum()), 3),
            "takers": int((ep.abs() > 0).sum())}


def gw_block(week: pd.DataFrame, gw: int, season: str) -> dict:
    """One finished gameweek: what was predicted against what happened.

    ``team_games`` counts distinct (opponent, kickoff) pairs rather than clubs,
    so a double gameweek contributes two team-games and the observed
    pens-per-game stays comparable with the served :data:`LEAGUE_PENS_PG`.

    The key is ``opp_code``, not ``team_code``: the live rows carry the
    player's *current* club (``data/live.py`` stamps ``player_meta`` over the
    whole season), so after a January transfer his August row claims a fixture
    his new club never played and the team-game count drifts up all season.
    ``opp_code`` is the opponent of the match that was actually played.

    A week with no penalties reports ``None`` for the hit rate, not zero: zero
    over zero would read as the taker model having been wrong every time.
    """
    week = week.reset_index(drop=True)
    events, instrument, covered = realized_pens(week, season)
    order = (week["penalties_order"] if "penalties_order" in week.columns
             else pd.Series(pd.NA, index=week.index))
    share = share_now(order)
    positions = (week["position"].astype(str) if "position" in week.columns
                 else pd.Series("MID", index=week.index))
    goal_points = positions.map(GOAL_POINTS).astype("float64").fillna(0.0)
    taken = float(events.sum())
    by_first = float(events[share >= 1.0].sum())
    team_games = 0
    if {"opp_code", "kickoff_time"} <= set(week.columns):
        team_games = int(len(week[["opp_code", "kickoff_time"]]
                             .drop_duplicates()))
    pred = predicted_ep(gw)
    return {
        "gw": int(gw),
        "instrument": instrument,
        "rows": int(len(week)),
        "covered_rows": covered,
        "team_games": team_games,
        "component_rows": pred["rows"],
        "predicted_ep_pen_taker": pred["ep_pen_taker"],
        "predicted_takers": pred["takers"],
        "pens_taken": round(taken, 3),
        "pens_by_first_choice": round(by_first, 3),
        "taker_hit_rate": round(by_first / taken, 3) if taken else None,
        "pens_per_team_game": (round(taken / team_games, 4) if team_games
                               else None),
        "realized_pen_points": round(
            float((events * PEN_CONVERSION * goal_points).sum()), 3),
    }


def safe_gw_block(week: pd.DataFrame, gw: int, season: str) -> dict:
    """:func:`gw_block`, or ``{"gw": N, "error": ...}`` if that week is broken.

    Per gameweek rather than per report: one truncated week's rows or one
    half-written component file is that week's problem, and degrading the whole
    season to a note would throw away every week that read fine.
    """
    try:
        return gw_block(week, gw, season)
    except Exception as exc:  # noqa: BLE001 — one bad week, not a bad season
        return {"gw": int(gw), "error": str(exc)}


def season_totals(blocks: list[dict]) -> dict:
    """The season line: the cumulative comparison the v6 validation wanted.

    ``instruments`` is a list because a season can straddle an Understat
    backfill, and totals mixing a counted week with a missed-only week are not
    one measurement.
    """
    taken = sum(b["pens_taken"] for b in blocks)
    first = sum(b["pens_by_first_choice"] for b in blocks)
    games = sum(b["team_games"] for b in blocks)
    return {
        "gws": len(blocks),
        "instruments": sorted({b["instrument"] for b in blocks}),
        "team_games": games,
        "predicted_ep_pen_taker": round(
            sum(b["predicted_ep_pen_taker"] for b in blocks), 3),
        "pens_taken": round(taken, 3),
        "pens_by_first_choice": round(first, 3),
        "taker_hit_rate": round(first / taken, 3) if taken else None,
        "pens_per_team_game": round(taken / games, 4) if games else None,
        "league_pens_pg_served": LEAGUE_PENS_PG,
        "realized_pen_points": round(
            sum(b["realized_pen_points"] for b in blocks), 3),
    }


def _current_season() -> str:
    """``cfg.current_season``, or ``""`` when there is no readable config."""
    try:
        from gaffer.config import load_config

        return str(load_config().current_season or "")
    except Exception:  # noqa: BLE001 — a report never blocks on config
        return ""


def track_pens(season: str | None = None) -> dict:
    """The season so far, gameweek by gameweek. Never raises.

    Every failure — no live season, a truncated parquet, an Understat file
    that will not read — comes back as an empty report carrying a note. A
    standing report that dies on one bad file is a report nobody runs.
    """
    report: dict = {"season": "", "gws": [], "season_totals": {}, "notes": []}
    try:
        report["season"] = str(
            season if season is not None else _current_season())
        if not store.exists(PLAYER_GW_PATH) or not store.exists(EVENTS_PATH):
            report["notes"].append(
                "no live season on disk — run `gaffer refresh` first")
            return report
        rows = store.load(PLAYER_GW_PATH)
        have = {int(g) for g in rows["gw"].unique()}
        done = [g for g in finished_gws(store.load(EVENTS_PATH)) if g in have]
        if not done:
            report["notes"].append("no finished gameweek in the live season yet")
            return report
        report["gws"] = [
            safe_gw_block(rows[rows["gw"] == g], g, report["season"])
            for g in done]
        good = [b for b in report["gws"] if "error" not in b]
        broken = [b for b in report["gws"] if "error" in b]
        report["season_totals"] = season_totals(good)
        if broken:
            report["notes"].append(
                "skipped " + ", ".join(f"gw{b['gw']}" for b in broken)
                + " — the week would not read; the season line covers the rest")
        if any(b["instrument"] == "pens_missed_only" for b in good):
            report["notes"].append(
                "penalties counted from pens_missed only — Understat npxg is "
                "not on disk for this season, so converted spot kicks are "
                "invisible and every count here is a floor")
        return report
    except Exception as exc:  # noqa: BLE001 — a standing report never blocks
        report["notes"].append(f"pen tracker degraded: {exc}")
        return report


def save_tracker(report: dict) -> Path:
    """``reports/pen_tracker.json``, through a temp file and ``os.replace``.

    The same atomic write as :func:`gaffer.evaluation.save_evaluation`, and for
    the same reason: a reader either sees the whole previous report or the
    whole new one, never the half-written middle.
    """
    text = json.dumps(report, indent=1, allow_nan=False)
    artifacts.REPORTS.mkdir(exist_ok=True)
    path = tracker_path()
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def format_tracker(report: dict) -> str:
    """The printed table: one line per gameweek, then the season line."""
    lines = [f"Penalty tracker — season {report.get('season') or 'unknown'}",
             f"{'GW':>3}  {'pred EP':>8}  {'pens':>5}  {'1st':>5}  "
             f"{'hit':>5}  {'per game':>9}  instrument"]
    for b in report.get("gws", []):
        if "error" in b:
            lines.append(f"{b['gw']:>3}  unreadable: {b['error']}")
            continue
        hit = ("    —" if b["taker_hit_rate"] is None
               else f"{b['taker_hit_rate']:>5.2f}")
        per = ("        —" if b["pens_per_team_game"] is None
               else f"{b['pens_per_team_game']:>9.3f}")
        lines.append(
            f"{b['gw']:>3}  {b['predicted_ep_pen_taker']:>8.2f}  "
            f"{b['pens_taken']:>5.1f}  {b['pens_by_first_choice']:>5.1f}  "
            f"{hit}  {per}  {b['instrument']}")
    totals = report.get("season_totals") or {}
    if totals:
        lines.append(
            f"season: predicted EP {totals['predicted_ep_pen_taker']:.2f} vs "
            f"realized pen points {totals['realized_pen_points']:.2f} over "
            f"{totals['gws']} gw — {totals['pens_taken']:.1f} pens in "
            f"{totals['team_games']} team-games against a served "
            f"{totals['league_pens_pg_served']}/game")
    for note in report.get("notes", []):
        lines.append(f"note: {note}")
    return "\n".join(lines)
