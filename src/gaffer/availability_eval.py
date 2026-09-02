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

from gaffer.config import load_config
from gaffer.evaluation import git_sha, news_actuals, run_at
from gaffer.snapshot import load_snapshot_log

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


LEAD_BUCKETS = ((0.0, 1.0, "<1d"), (1.0, 2.0, "1-2d"), (2.0, 3.0, "2-3d"),
                (3.0, 5.0, "3-5d"), (5.0, 7.0, "5-7d"),
                (7.0, float("inf"), "7d+"))
"""Half-open ``[lo, hi)`` bands, in the units a manager thinks in.

Under a day is "I found out on the way to the deadline"; over a week is "this
was never news". The boundaries are not fitted to anything and are not
supposed to be — they are a reading aid over a distribution the project has
never seen, and the raw ``changes`` rows are on the payload for anyone who
wants their own."""

WORST_LATE_FLAGS = 20
"""Spec §3.1's table size."""

UNAVAILABLE_FLAG_STATUS = ("i", "s", "u", "n")
"""Statuses that assert the player will not feature. ``d`` (doubtful) is
deliberately not one: it is the layer *hedging*, and grading a hedge as a
prediction of absence would score the honest answer as a miss."""


def _bucket(days: float) -> str:
    for lo, hi, label in LEAD_BUCKETS:
        if lo <= days < hi:
            return label
    return LEAD_BUCKETS[-1][2]


def _outcomes(actuals: pd.DataFrame) -> dict[tuple[int, int], bool]:
    """``{(gw, code): started}`` over the graded gameweeks.

    ``start_truth`` rather than a bare ``minutes > 0``: the question §3.1 asks
    is whether he *started*, and the ``starts`` column postdates part of the
    archive, so the shipped inference is the one that must be used here too.
    Summed per (gw, code) first, because a double gameweek is two rows and
    "did he start" over a double is "did he start either".
    """
    from gaffer.evaluation import start_truth

    if actuals is None or actuals.empty:
        return {}
    frame = actuals.copy()
    # The column is named without a leading underscore because
    # ``itertuples`` renames those to positional ``_1``-style attributes.
    frame["started_any"] = start_truth(frame)
    grouped = frame.groupby(["gw", "code"], as_index=False).agg(
        started_any=("started_any", "max"))
    return {(int(r.gw), int(r.code)): bool(r.started_any > 0.0)
            for r in grouped.itertuples()}


def score_flag_latency(log: pd.DataFrame, actuals: pd.DataFrame,
                       events: pd.DataFrame, *, season: str) -> dict:
    """Spec §3.1, over the banked snapshot log. Never raises.

    One row per (gw, code) whose ``status`` changed at least once inside the
    pre-deadline window of a graded gameweek. ``lead_days`` is measured from
    the **first** change, which is the first moment a manager could have
    acted; the final status is the last one recorded before the deadline.

    The payload carries its own gate. ``available`` is false until the log
    holds :data:`MIN_SNAP_DATES` distinct days **and** at least one covered
    gameweek is graded, and the note names both numbers — because "nothing to
    show" and "nothing happened" are different sentences and only one of them
    is true in August.
    """
    empty = _empty("flag_latency",
                   "No availability snapshots have been banked yet.",
                   snap_dates=0, min_snap_dates=MIN_SNAP_DATES,
                   covered_gws=[], checked_covered_gws=[], histogram=[],
                   late_flags=[], changes=[])
    if log is None or log.empty or "status" not in log.columns:
        return empty
    frame = log.copy()
    if "season" in frame.columns:
        frame = frame[frame["season"].astype(str) == str(season)]
    if frame.empty:
        return empty

    snap_dates = int(frame["snap_date"].astype(str).nunique())
    window = pre_deadline(frame, deadlines(events))
    covered = sorted({int(g) for g in window["gw"].unique()}) \
        if not window.empty else []
    graded = sorted(set(covered) & checked_gws(actuals))
    gate = dict(snap_dates=snap_dates, min_snap_dates=MIN_SNAP_DATES,
                covered_gws=covered, checked_covered_gws=graded)
    # The gate decides whether the report is *readable*, not whether it is
    # computed. The tables are built either way so a half-filled log can be
    # inspected while it fills; ``available`` is what a caller checks before
    # drawing a distribution over four days of evidence.
    open_gate = snap_dates >= MIN_SNAP_DATES and bool(graded)
    note = None if open_gate else (
        f"{snap_dates} of {MIN_SNAP_DATES} snapshot days banked, and "
        f"{len(graded)} covered gameweek(s) graded. The report fills as "
        f"`gaffer snapshot` runs and gameweeks are marked data_checked.")

    started = _outcomes(actuals)
    window = window[window["gw"].isin(graded)]
    window = window.sort_values(["gw", "code", "snap_date"])
    changes = []
    for (gw, code), part in window.groupby(["gw", "code"], sort=True):
        statuses = part["status"].astype("string").tolist()
        first = statuses[0]
        moved = [i for i, s in enumerate(statuses) if s != first]
        if not moved:
            continue
        outcome = started.get((int(gw), int(code)))
        if outcome is None:
            continue
        row = part.iloc[moved[0]]
        final = statuses[-1]
        changes.append({
            "gw": int(gw), "code": int(code),
            "first_change": str(row["snap_date"]),
            "lead_days": float(row["lead_days"]),
            "from_status": str(first), "final_status": str(final),
            "chance_of_playing": (
                None if pd.isna(part.iloc[-1].get("chance_of_playing"))
                else float(part.iloc[-1]["chance_of_playing"])),
            "started": bool(outcome),
        })

    histogram = []
    for _lo, _hi, label in LEAD_BUCKETS:
        rows = [c for c in changes if _bucket(c["lead_days"]) == label]
        if not rows:
            continue
        histogram.append({
            "bucket": label,
            "started": sum(1 for c in rows if c["started"]),
            "missed": sum(1 for c in rows if not c["started"]),
        })

    # The disagreement, both ways round. "The log said unavailable and he
    # started" is as much a late flag as its opposite: in each case the last
    # thing the manager was told before the deadline was wrong.
    late = [c for c in changes
            if (c["final_status"] in UNAVAILABLE_FLAG_STATUS) == c["started"]]
    late.sort(key=lambda c: (c["lead_days"], c["gw"], c["code"]))

    return {"run_at": run_at(), "git_sha": git_sha(), "kind": "flag_latency",
            "available": open_gate, "rows": len(changes), "note": note,
            "histogram": histogram,
            "late_flags": late[:WORST_LATE_FLAGS],
            "changes": changes, **gate}


def score_presser_grades(log: pd.DataFrame, actuals: pd.DataFrame,
                         events: pd.DataFrame, *, season: str) -> dict:
    """Spec §3.2, over the banked snapshot log. Never raises.

    **The population is ``llm_verdict.notna()``**, not ``source == "llm"``.
    The spec says both and they are different sets: measured on the live log,
    160 of 169 verdict rows carry ``source = premierinjuries`` and 9 carry
    ``llm``, because ``source`` names *which news source produced the row* and
    the classifier's verdict rides along on whatever row it was asked about.
    ``source`` travels into the payload as a breakdown instead.

    The event scored is **absence**. Every class claims it to some degree, so
    precision — absence given the verdict — is comparable across them, and the
    readout worth having is whether it falls in the order the classes are
    named in. Recall is over the verdict-carrying rows only and the payload
    says so: recall against every absent player in the gameweek would count
    everyone the classifier was never shown.

    The verdict graded is the **last one recorded before the deadline**, which
    is ``score_news_shadow``'s ``.last()`` rule for the same reason — it is the
    one that stood when the manager acted.
    """
    empty = _empty("presser_grades",
                   "No presser verdicts have been banked yet.",
                   verdicts_banked=0, confusion=[], per_class=[],
                   by_source=[], recall_population="verdict-carrying rows")
    if log is None or log.empty or "llm_verdict" not in log.columns:
        return empty
    frame = log.copy()
    if "season" in frame.columns:
        frame = frame[frame["season"].astype(str) == str(season)]
    frame = frame[frame["llm_verdict"].notna()]
    if frame.empty:
        return empty
    banked = int(len(frame))

    window = pre_deadline(frame, deadlines(events))
    if window.empty:
        return {**empty, "verdicts_banked": banked, "note": (
            f"{banked} verdict(s) banked, none of them recorded before a "
            f"deadline. The snapshot job began after GW2's deadline; the "
            f"first gradeable verdicts are the ones banked in a gameweek's "
            f"own week.")}
    graded = sorted({int(g) for g in window["gw"].unique()}
                    & checked_gws(actuals))
    if not graded:
        return {**empty, "verdicts_banked": banked, "note": (
            f"{banked} verdict(s) banked and {len(set(window['gw']))} "
            f"gameweek(s) covered before their deadline, none of them yet "
            f"marked data_checked. The grades land with the results.")}

    window = window[window["gw"].isin(graded)]
    last = (window.sort_values(["gw", "code", "snap_date"])
            .groupby(["gw", "code"], as_index=False).last())
    started = _outcomes(actuals)
    rows = []
    for r in last.itertuples():
        outcome = started.get((int(r.gw), int(r.code)))
        if outcome is None:
            continue
        rows.append({"verdict": str(r.llm_verdict),
                     "source": ("" if pd.isna(getattr(r, "source", None))
                                else str(r.source)),
                     "started": bool(outcome)})
    if not rows:
        return {**empty, "verdicts_banked": banked, "note": (
            "Every pre-deadline verdict belongs to a player with no result "
            "row in the graded gameweeks.")}

    absent_total = sum(1 for row in rows if not row["started"])
    confusion, per_class = [], []
    for verdict in sorted({row["verdict"] for row in rows}):
        part = [row for row in rows if row["verdict"] == verdict]
        missed = sum(1 for row in part if not row["started"])
        confusion.append({"verdict": verdict, "n": len(part),
                          "started": len(part) - missed,
                          "not_started": missed})
        per_class.append({
            "verdict": verdict, "n": len(part),
            # Six places, not three: the rounding is only there to keep
            # 0.30000000000000004 out of the artifact, and a third of a
            # small class is a repeating decimal that three places would
            # visibly move.
            "precision": round(missed / len(part), 6),
            # Zero rather than null when nobody was absent at all: the class
            # then found none of nothing, which is 0/0 only if you ask the
            # question the wrong way round. ``absent_total`` is on the payload
            # so a reader can see the denominator.
            "recall": (round(missed / absent_total, 6) if absent_total
                       else 0.0),
        })
    by_source = [{"source": s,
                  "rows": sum(1 for row in rows if row["source"] == s)}
                 for s in sorted({row["source"] for row in rows})]

    return {"run_at": run_at(), "git_sha": git_sha(),
            "kind": "presser_grades", "available": True, "rows": len(rows),
            "note": None, "verdicts_banked": banked,
            "graded_gws": graded, "absent_rows": absent_total,
            "confusion": confusion, "per_class": per_class,
            "by_source": by_source,
            "recall_population": "verdict-carrying rows"}


def load_events() -> pd.DataFrame:
    """The banked events snapshot, or an empty frame with the two columns.

    A module-level function rather than an inline ``store.load`` so a test can
    replace it, and so the two evaluators below cannot end up reading the
    deadline from two different places.
    """
    from gaffer.data import store

    if not store.exists("live/events.parquet"):
        return pd.DataFrame(columns=["gw", "deadline_time"])
    return store.load("live/events.parquet")


def _season() -> str:
    """``cfg.current_season``, or ``""``.

    Its own try, for ``news_shadow._current_season``'s reason: a report is
    better than no report, and a clone with no ``config.toml`` still has a log
    worth reading. An empty season matches the log's own empty-string season
    and therefore scores the pre-season rows and nothing else, which is the
    honest degradation rather than a silent whole-log score.
    """
    try:
        return str(load_config().current_season or "")
    except Exception as exc:  # noqa: BLE001 — a report never blocks on config
        print(f"availability report: no configured season ({exc})")
        return ""


def evaluate_flag_latency() -> dict:
    """:func:`score_flag_latency` over the banked log and the live results."""
    return score_flag_latency(load_snapshot_log(), news_actuals(),
                              load_events(), season=_season())


def evaluate_presser_grades() -> dict:
    """:func:`score_presser_grades` over the banked log and the results."""
    return score_presser_grades(load_snapshot_log(), news_actuals(),
                                load_events(), season=_season())
