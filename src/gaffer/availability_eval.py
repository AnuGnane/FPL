"""Grading the availability layer's *inputs*: flags, and the verdicts on them.

``gaffer.news_shadow`` grades what the news layer did to a probability. This
module grades the layer's raw material, out of the log ``gaffer snapshot`` has
been banking every day since v7c and nothing has ever read:

* **flag latency** (spec §3.1) — how much warning a status change gave before
  the deadline, and whether the player then started;
* **presser verdicts** (spec §3.2) — the classifier's four classes against
  what happened.

Both stand on the same three facts and the middle one is the one the spec
missed. The log stamps every snapshot with ``next_unfinished_gw`` — the first
gameweek not yet *finished* (``snapshot.py:45-57``) — so a snapshot taken
while a gameweek is being played carries that gameweek's number with its
deadline already behind it. A lead time computed over those rows is negative.
Every row therefore passes :func:`pre_deadline` first, and a gameweek whose
deadline is unreadable contributes nothing rather than a guess.

Nothing here raises for a caller that is a report: a missing log, a missing
results file and an events frame with no deadlines each produce a well-formed
payload with ``available: false`` and a sentence saying what is missing.
"""

from __future__ import annotations

import pandas as pd

from gaffer.evaluation import git_sha, news_actuals, run_at

MIN_SNAP_DATES = 14
"""Spec §3.1's first gate. Fourteen days is two full news cycles, which is the
shortest stretch over which "how much warning" is a distribution rather than
an anecdote."""


def deadlines(events: pd.DataFrame | None) -> dict[int, pd.Timestamp]:
    """``{gw: deadline}`` in UTC, for the gameweeks that have a readable one.

    A gameweek whose deadline will not parse is **absent**, not defaulted. The
    only use of this map is to decide whether a snapshot came in time, and a
    guessed deadline answers that question by inventing the answer.
    """
    if events is None or not isinstance(events, pd.DataFrame) \
            or events.empty or "deadline_time" not in events.columns:
        return {}
    gws = pd.to_numeric(events["gw"], errors="coerce")
    when = pd.to_datetime(events["deadline_time"], errors="coerce", utc=True)
    return {int(g): w for g, w in zip(gws, when)
            if pd.notna(g) and pd.notna(w)}


def pre_deadline(log: pd.DataFrame,
                 by_gw: dict[int, pd.Timestamp]) -> pd.DataFrame:
    """``log`` cut to snapshots taken at or before their gameweek's deadline,
    with ``lead_days`` attached.

    ``snap_date`` is a date string with no clock in it (``snapshot.py:36-42``),
    so the snapshot is taken at 00:00 UTC of that day. The deadline keeps its
    own time — 17:30 on most Fridays — because dropping it would make a
    Thursday flag and a Friday one the same number.
    """
    if log is None or log.empty:
        return log if log is not None else pd.DataFrame()
    out = log.copy()
    out["gw"] = pd.to_numeric(out["gw"], errors="coerce")
    out["_deadline"] = out["gw"].map(by_gw)
    out["_taken"] = pd.to_datetime(out["snap_date"], errors="coerce", utc=True)
    out = out[out["_deadline"].notna() & out["_taken"].notna()]
    out = out[out["_taken"] <= out["_deadline"]]
    if out.empty:
        return out.drop(columns=["_deadline", "_taken"])
    out["lead_days"] = ((out["_deadline"] - out["_taken"])
                        .dt.total_seconds() / 86400.0).round(2)
    out["gw"] = out["gw"].astype("int64")
    return out.drop(columns=["_deadline", "_taken"])


def checked_gws(actuals: pd.DataFrame | None) -> set[int]:
    """The gameweeks FPL has marked ``data_checked``, read the way the rest of
    the tree reads it: presence in the results frame (``review.py:140``).

    Not the events frame's flag. ``refresh_live`` drops every gameweek that
    flag is false for, so the results file *is* the flag, and reading the flag
    separately would let the two disagree about a gameweek mid-refresh.
    """
    if actuals is None or not isinstance(actuals, pd.DataFrame) \
            or actuals.empty or "gw" not in actuals.columns:
        return set()
    gws = pd.to_numeric(actuals["gw"], errors="coerce").dropna()
    return {int(g) for g in gws.unique()}


def _empty(kind: str, note: str, **extra) -> dict:
    """A well-formed payload with nothing in it and a sentence saying why.

    Spec §1: a view whose data does not exist yet says what it is waiting for.
    The sentence is built here rather than in the UI so the CLI, the API and
    the page all say the same thing.
    """
    return {"run_at": run_at(), "git_sha": git_sha(), "kind": kind,
            "available": False, "rows": 0, "note": note, **extra}
