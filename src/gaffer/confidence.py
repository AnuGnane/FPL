"""Confidence framing, derived from the banked record and nothing else.

Every consumer FPL tool prints a confidence number, and none of them can say
where it came from. This module exists so that this one can: the only inputs
are counts out of ``reports/decision_ledger.json``, the only outputs are
sentences containing those counts, and there is no branch anywhere that
manufactures a percentage.

The tiering is deliberately coarse. Three graded gameweeks cannot separate a
real captaincy edge from a coin, so below :data:`MIN_GRADED` the answer is not
a weaker claim, it is a refusal to make one — "too early to grade", with the
count that makes the refusal checkable. Above it the sentence still quotes
counts rather than a rate, because "outscored yours in 5 of 7" is a fact and
"71% confident" is a decoration.

Read-only, never raises, and never a reason for a 500: the ledger is a file a
laptop can die mid-write to, and a captain card is not worth an error page.
"""

from __future__ import annotations

MIN_GRADED = 4
"""Gradeable gameweeks below which the tool declines to have an opinion.

Four rather than three because three weeks of a binary comparison is one draw
short of being able to say anything at all, and one short of the point where
the honest sentence stops being "come back later".

Gates on ``wins + losses`` — see :func:`captain_confidence`. It used to gate
on "lanes carrying a delta", which counted weeks of *agreement*, and four
agreements were enough to trip the verdict branch and print "it has not
earned the armband yet" off a record of zero disagreements.
"""

TIERS = ("early", "mixed", "backed")
"""Ascending. ``early`` is a refusal, not a low score."""

NOTHING_SURVIVED = "no banked advice survives"
"""The prefix ``review.grade_gw`` writes on every lane of a pruned gameweek.

Such a lane is not a review of anything — the advice it would have graded has
been deleted (spec D2) — so it does not count towards ``reviewed`` either.
Left in, a season of pruned weeks reads as a season the tool was watched
through and never once managed to have an opinion in.
"""


def _lane(row, name: str) -> dict | None:
    """One named lane out of one ledger row, or ``None``.

    Defensive at every level because the caller is the web layer and the
    argument came off disk: a row that is not a dict, a ``lanes`` that is not
    a list, a lane that is not a dict.
    """
    if not isinstance(row, dict):
        return None
    lanes = row.get("lanes")
    if not isinstance(lanes, list):
        return None
    for lane in lanes:
        if isinstance(lane, dict) and lane.get("lane") == name:
            return lane
    return None


def captain_confidence(ledger) -> dict:
    """What the ledger entitles the captain card to say.

    ``delta_pts`` on a captaincy lane is *my* points minus the *model's*
    (``review._lane``), so a negative delta is a week the model's armband beat
    mine and a positive one is a week mine beat the model's. An ``aligned``
    week is neither: I picked the model's own captain, so there is nothing to
    compare and counting it as agreement-therefore-success would be scoring
    the tool against itself.

    ``graded`` is ``wins + losses``, exactly. An aligned week is **not** in it
    and is **not** in the denominator of anything: it is quoted on its own,
    beside the record rather than inside it. The first cut counted aligned
    weeks as graded, which made four weeks of taking the tool's advice enough
    to clear :data:`MIN_GRADED` and then print "0 of 4 — it has not earned the
    armband yet". A verdict against the model assembled out of weeks nobody
    disagreed with it is not a weak claim, it is a false one.

    ``reviewed`` counts gameweeks that carry a captaincy lane worth the name.
    A lane whose note says the advice was pruned (:data:`NOTHING_SURVIVED`) is
    not one: nothing was reviewed there. The gap between ``reviewed`` and
    ``graded + aligned`` is the "the model's captain was not in your eleven"
    weeks, reported rather than hidden.
    """
    reviewed = wins = losses = aligned = 0
    for row in ledger or []:
        lane = _lane(row, "captaincy")
        if lane is None:
            continue
        note = lane.get("note")
        if isinstance(note, str) and NOTHING_SURVIVED in note:
            continue
        reviewed += 1
        delta = lane.get("delta_pts")
        if lane.get("aligned"):
            aligned += 1
        elif delta is None:
            continue
        elif float(delta) < 0:
            wins += 1
        elif float(delta) > 0:
            losses += 1
    graded = wins + losses

    agreed = f" ({aligned} you agreed on)" if aligned else ""
    if graded < MIN_GRADED:
        tier = "early"
        weeks = f"{reviewed} gameweek{'' if reviewed == 1 else 's'} reviewed"
        tail = ("none gradeable yet" if graded == 0
                else f"{graded} gradeable so far")
        text = f"Too early to grade — {weeks}, {tail}{agreed}."
    else:
        tier = "backed" if wins > losses else "mixed"
        text = (f"The model's captain outscored yours in {wins} of {graded} "
                f"comparable gameweeks{agreed}")
        text += ("." if tier == "backed"
                 else " — it has not earned the armband yet.")
    return {"tier": tier, "reviewed": reviewed, "graded": graded,
            "wins": wins, "losses": losses, "aligned": aligned, "text": text}
