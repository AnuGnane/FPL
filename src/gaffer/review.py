"""The decision loop: grading what I did against what the model said in time.

The journal already draws one line — the model's XI against mine, captain
doubled, no autosubs. This module asks the harder question the whole app
exists for: *which decision* cost me, in points and in title odds, and how
much has that decision type cost me all season.

Four things make it more than a bigger journal:

* **The counterfactual is deadline-guarded.** ``journal.latest_run_per_gw`` is
  imported verbatim (spec D3): among a gameweek's banked runs the newest one
  written *before* the deadline wins, and a gameweek where every run was late
  is graded with a flag rather than passed off as foresight.
* **Every squad is scored with real autosubs.** ``backtest.score_gw`` — the
  replay's scorer, with the vice fallback, the bench-boost arithmetic and the
  hit cost already in it. Imported, never modified; its simplified-autosub
  caveats (``backtest.py:36-38``) are exactly what the reconciliation gate
  below is built to catch.
* **Two currencies.** Points, and the change in P(win the mini-league) from
  v8c's Monte Carlo. A captaincy that cost two points and a place in the race
  is a different decision from one that cost two points and nothing.
* **Grades are banked, never re-derived.** ``ADVICE_HISTORY_KEEP`` is 20 and
  global, so GW1's advice is pruned within weeks (spec D2). The review runs
  once a gameweek's results are final and appends to
  ``reports/decision_ledger.json``; every reader afterwards reads the ledger.

Nothing here writes to ``advise``. The ledger is measurement.
"""

from __future__ import annotations

import pandas as pd

from gaffer.artifacts import load_components  # noqa: F401 — Task 5's import
from gaffer.backtest import score_gw
from gaffer.data import store
from gaffer.data.my_entry import (bank_my_entry, chip_for_gw, gw_history_row,
                                  load_my_gw, load_my_history,
                                  load_my_transfers, my_transfers_for_gw)
from gaffer.journal import _code_of_element, latest_run_per_gw

__all__ = ["ACTUAL_COLS", "actuals_for_gw", "code_of_element",
           "model_decisions", "my_decisions", "reviewable_gws", "score_gw"]

ACTUAL_COLS = ["code", "total_points", "minutes", "position"]
"""Exactly the columns :func:`gaffer.backtest.score_gw` reads, in its order."""

PLAYER_GW = "live/player_gw.parquet"

XI_SIZE = 11
"""Picks at a higher ``position`` than this are the bench, in that order."""


def code_of_element() -> dict[int, int]:
    """``element -> code`` off the live players table.

    A re-export of ``journal._code_of_element`` rather than a copy of it:
    ``journal.py`` is import-only this cycle (spec §5) and its row shape is
    pinned by existing tests, so the sharing goes this way round.
    """
    return _code_of_element()


def actuals_for_gw(gw: int) -> pd.DataFrame:
    """One row per code for ``gw``, shaped for :func:`score_gw`.

    Double gameweeks are aggregated here rather than left to the caller,
    which is the join ``backtest``'s docstring records having learned the
    hard way: ``score_gw`` builds a dict off this frame, so a second row for
    a code silently drops one of his two matches.

    Only the newest season is read. The live frame carries several, and GW2
    of 2022-23 is not GW2 of this one.

    An empty frame with the right columns for every failure — no file, no
    such gameweek, an unreadable parquet. ``run_review`` reads emptiness as
    "not reviewable" and says so.
    """
    empty = pd.DataFrame(columns=ACTUAL_COLS)
    if not store.exists(PLAYER_GW):
        return empty
    try:
        frame = store.load(PLAYER_GW)
    except Exception:  # noqa: BLE001 — an unreadable frame is a missing one
        return empty
    if frame.empty:
        return empty
    if "season_idx" in frame.columns:
        frame = frame[frame["season_idx"] == frame["season_idx"].max()]
    frame = frame[pd.to_numeric(frame["gw"], errors="coerce") == int(gw)]
    if frame.empty:
        return empty
    grouped = frame.groupby("code", as_index=False).agg(
        total_points=("total_points", "sum"), minutes=("minutes", "sum"),
        position=("position", "first"))
    grouped["code"] = grouped["code"].astype("int64")
    grouped["total_points"] = pd.to_numeric(
        grouped["total_points"], errors="coerce").fillna(0).astype("int64")
    grouped["minutes"] = pd.to_numeric(
        grouped["minutes"], errors="coerce").fillna(0).astype("int64")
    grouped["position"] = grouped["position"].astype(str)
    return grouped[ACTUAL_COLS]


def reviewable_gws() -> list[int]:
    """Every gameweek whose results are final, ascending.

    Presence in ``player_gw.parquet`` *is* the ``data_checked`` gate:
    ``refresh_live`` drops every gameweek FPL has not marked so, which is the
    same reasoning ``artifacts.ingested_through`` documents. Reviewing a week
    FPL is still adjusting would bank a grade against numbers that then move.
    """
    if not store.exists(PLAYER_GW):
        return []
    try:
        frame = store.load(PLAYER_GW)
    except Exception:  # noqa: BLE001
        return []
    if frame.empty:
        return []
    if "season_idx" in frame.columns:
        frame = frame[frame["season_idx"] == frame["season_idx"].max()]
    gws = pd.to_numeric(frame["gw"], errors="coerce").dropna()
    return sorted({int(g) for g in gws})


def _codes(entries) -> list[int]:
    return [int(e["code"]) for e in (entries or [])
            if isinstance(e, dict) and e.get("code") is not None]


def model_decisions(gw: int) -> dict | None:
    """What the model said before ``gw``'s deadline, or ``None``.

    ``None`` is not an edge case. ``ADVICE_HISTORY_KEEP`` is 20 runs across
    all gameweeks, so by October GW1's advice is gone and its ledger row is
    marked ``no_advice`` with every lane null — null, not zero, because "the
    model had no opinion" and "the model agreed with me" are different facts
    and only one of them is a grade (spec G2).
    """
    payload = latest_run_per_gw().get(int(gw))
    if payload is None:
        return None
    captain = (payload.get("captain") or {}).get("code")
    vice = (payload.get("vice") or {}).get("code")
    chip = next((str(row.get("chip")) for row in payload.get("chip_table") or []
                 if isinstance(row, dict) and row.get("play_now")), None)
    names = {int(p["code"]): str(p.get("name", p["code"]))
             for key in ("xi", "bench", "buys", "sells")
             for p in payload.get(key) or []
             if isinstance(p, dict) and p.get("code") is not None}
    positions = {int(p["code"]): str(p.get("position", ""))
                 for key in ("xi", "bench", "buys", "sells")
                 for p in payload.get(key) or []
                 if isinstance(p, dict) and p.get("code") is not None}
    return {
        "xi": _codes(payload.get("xi")),
        "bench": _codes(payload.get("bench")),
        "captain": None if captain is None else int(captain),
        "vice": None if vice is None else int(vice),
        "buys": _codes(payload.get("buys")),
        "sells": _codes(payload.get("sells")),
        "hits": int(payload.get("hits") or 0),
        "chip": chip,
        "names": names,
        "positions": positions,
        "post_deadline": bool(payload.get("post_deadline")),
    }


def my_decisions(gw: int, *, season: str, entry_id: int,
                 raw_dir=None) -> dict | None:
    """What I actually did in ``gw``, off the bank, or ``None``.

    Off the bank and never off the API: ``run_review`` banks first and grades
    second, so this function is a pure read and a gameweek nobody banked is a
    gameweek nobody grades (spec G2).

    ``xi`` is ``position`` 1-11 in that order and ``bench`` is 12-15 in that
    order, because bench order is one of the four graded lanes and a set
    would throw the lane away. The armband comes from ``is_captain`` rather
    than from the multiplier, which is 3 under a triple captain and 1 under a
    bench boost.
    """
    picks = load_my_gw(season, entry_id, gw, raw_dir)
    if picks is None:
        return None
    history = load_my_history(season, entry_id, raw_dir)
    row = gw_history_row(history, gw) or {}
    code_of = code_of_element()

    ordered, unresolved = [], 0
    for pick in picks:
        try:
            slot = int(pick["position"])
            element = int(pick["element"])
        except (KeyError, TypeError, ValueError):
            unresolved += 1
            continue
        code = code_of.get(element)
        if code is None:
            unresolved += 1
            continue
        ordered.append((slot, int(code), bool(pick.get("is_captain")),
                        bool(pick.get("is_vice_captain"))))
    ordered.sort(key=lambda r: r[0])

    notices = []
    if unresolved:
        notices.append(
            f"{unresolved} pick could not be resolved to a player and was "
            f"dropped from the grade" if unresolved == 1 else
            f"{unresolved} picks could not be resolved to players and were "
            f"dropped from the grade")
    cost = int(row.get("event_transfers_cost", 0) or 0)
    return {
        "xi": [code for slot, code, _, _ in ordered if slot <= XI_SIZE],
        "bench": [code for slot, code, _, _ in ordered if slot > XI_SIZE],
        "captain": next((c for _, c, cap, _ in ordered if cap), None),
        "vice": next((c for _, c, _, vc in ordered if vc), None),
        "chip": chip_for_gw(history, gw),
        "hits": cost // 4,
        "official_gross": (int(row["points"]) if row.get("points") is not None
                           else None),
        "official_cost": cost,
        "points_on_bench": (int(row["points_on_bench"])
                            if row.get("points_on_bench") is not None
                            else None),
        "transfers": my_transfers_for_gw(
            load_my_transfers(season, entry_id, raw_dir), gw),
        "notices": notices,
    }
