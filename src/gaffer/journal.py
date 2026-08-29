"""The decision journal: the model's plan against the one you actually played.

A computed join with no manual entry anywhere (spec §6.4):

- Source A is ``reports/advice_history/`` — the newest banked run of a
  gameweek is what the model said before that deadline.
- Source B is the FPL entry API's picks for that gameweek.
- Both sides are scored on the realized points already in
  ``data/live/player_gw.parquet``, captain doubled, no autosubs — the same
  measure ``meta.py::_actual_points`` uses for the history page.

Everything degrades to an empty journal: no history, no results, a gameweek the
API will not answer, all produce rows the UI shows an empty state for.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from gaffer.artifacts import advice_history_files

JOURNAL_PATH = Path("reports/journal.json")

CACHE_MAX_AGE_S = 6 * 3600
"""Post-gameweek data changes at most weekly; six hours is generous."""


def xi_points(codes: list[int], captain: int | None,
              points: dict[int, int]) -> int:
    """XI points as picked, captain doubled, missing players worth zero."""
    total = sum(int(points.get(int(c), 0)) for c in codes)
    if captain is not None:
        total += int(points.get(int(captain), 0))
    return int(total)


def latest_run_per_gw() -> dict[int, dict]:
    """``{gw: advice payload}`` for the newest banked run of each gameweek."""
    out: dict[int, dict] = {}
    for path in advice_history_files():          # oldest first
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        gw = payload.get("gw")
        if gw is None:
            continue
        out[int(gw)] = payload                   # later files win
    return out


def _points_by_gw() -> dict[int, dict[int, int]]:
    from gaffer.data import store

    if not store.exists("live/player_gw.parquet"):
        return {}
    frame = store.load("live/player_gw.parquet")
    out: dict[int, dict[int, int]] = {}
    for gw, rows in frame.groupby("gw"):
        out[int(gw)] = {int(c): int(p)
                        for c, p in zip(rows["code"], rows["total_points"])}
    return out


def _code_of_element() -> dict[int, int]:
    from gaffer.data import store

    if not store.exists("live/players.parquet"):
        return {}
    frame = store.load("live/players.parquet")
    return {int(e): int(c) for e, c in zip(frame["element"], frame["code"])}


def _names(entries) -> list[str]:
    return [str(e.get("name", e.get("code", ""))) for e in entries or []
            if isinstance(e, dict)]


def build_journal(client, entry_id: int) -> dict:
    """Score every gameweek that has both a banked run and a finished result."""
    runs = latest_run_per_gw()
    points_by_gw = _points_by_gw()
    code_of = _code_of_element()

    rows: list[dict] = []
    for gw in sorted(runs):
        points = points_by_gw.get(gw)
        if not points:
            continue                             # gameweek not finished yet
        try:
            picks = client.get_entry_picks(entry_id, gw).get("picks") or []
        except Exception as exc:                 # noqa: BLE001 — network/schema
            # One unanswerable gameweek must not cost the user the rest of the
            # journal; it simply has no "what you did" side to compare against.
            print(f"journal: no picks for GW{gw} ({exc})")
            continue

        payload = runs[gw]
        model_xi = [int(p["code"]) for p in payload.get("xi") or []
                    if isinstance(p, dict) and "code" in p]
        model_captain = (payload.get("captain") or {}).get("code")
        model_pts = xi_points(
            model_xi, None if model_captain is None else int(model_captain),
            points)

        started = [p for p in picks if int(p.get("position", 99)) <= 11]
        actual_xi = [code_of.get(int(p["element"]))
                     for p in started if "element" in p]
        actual_xi = [c for c in actual_xi if c is not None]
        captain_pick = next((p for p in started if p.get("is_captain")), None)
        actual_captain = (code_of.get(int(captain_pick["element"]))
                          if captain_pick else None)
        actual_pts = xi_points(actual_xi, actual_captain, points)

        name_of = {int(p["code"]): str(p.get("name", p["code"]))
                   for key in ("xi", "buys", "sells")
                   for p in payload.get(key) or []
                   if isinstance(p, dict) and "code" in p}
        rows.append({
            "gw": gw,
            "model_pts": model_pts,
            "actual_pts": actual_pts,
            "delta": model_pts - actual_pts,
            "model_captain": (name_of.get(int(model_captain))
                              if model_captain is not None else None),
            "actual_captain": (name_of.get(int(actual_captain))
                               if actual_captain is not None else None),
            "model_buys": _names(payload.get("buys")),
            "model_sells": _names(payload.get("sells")),
        })

    cumulative: list[dict] = []
    model_total = actual_total = 0
    for row in rows:
        model_total += row["model_pts"]
        actual_total += row["actual_pts"]
        cumulative.append({"gw": row["gw"], "model": model_total,
                           "actual": actual_total,
                           "delta": model_total - actual_total})

    return {"rows": rows, "cumulative": cumulative,
            "built_at": datetime.now(timezone.utc).isoformat()}


def _stale(path: Path) -> bool:
    try:
        age = (datetime.now(timezone.utc)
               - datetime.fromtimestamp(path.stat().st_mtime,
                                        tz=timezone.utc)).total_seconds()
    except OSError:
        return True
    return age > CACHE_MAX_AGE_S


def load_journal(client, entry_id: int) -> dict:
    """The cached journal, rebuilt when the cache is missing or stale."""
    if JOURNAL_PATH.exists() and not _stale(JOURNAL_PATH):
        try:
            return json.loads(JOURNAL_PATH.read_text())
        except (OSError, ValueError):
            pass                                 # rebuild rather than fail
    out = build_journal(client, entry_id)
    if out["rows"]:
        # An empty journal is not worth a cache file: the next gameweek is the
        # thing that will make it non-empty, and a stale empty file would just
        # have to be invalidated.
        try:
            JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
            JOURNAL_PATH.write_text(json.dumps(out, indent=1))
        except OSError as exc:
            print(f"journal cache not written: {exc}")
    return out
