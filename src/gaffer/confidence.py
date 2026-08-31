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
"""

TIERS = ("early", "mixed", "backed")
"""Ascending. ``early`` is a refusal, not a low score."""


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

    ``reviewed`` counts gameweeks that carry a captaincy lane at all;
    ``graded`` counts the ones where it was comparable. The gap between them
    is the "the model's captain was not in your eleven" weeks, and it is
    reported rather than hidden — a season of ungraded lanes looks exactly
    like a season of agreement in any summary that collapses the two.
    """
    reviewed = graded = wins = losses = aligned = 0
    for row in ledger or []:
        lane = _lane(row, "captaincy")
        if lane is None:
            continue
        reviewed += 1
        delta = lane.get("delta_pts")
        if delta is None:
            continue
        graded += 1
        if lane.get("aligned"):
            aligned += 1
        elif float(delta) < 0:
            wins += 1
        elif float(delta) > 0:
            losses += 1

    if graded < MIN_GRADED:
        tier = "early"
        text = (f"Too early to grade — the model's captain has been "
                f"comparable to yours in {graded} of {reviewed} reviewed "
                f"gameweeks.")
    else:
        tier = "backed" if wins > losses else "mixed"
        text = (f"The model's captain outscored yours in {wins} of {graded} "
                f"comparable gameweeks ({aligned} you agreed on)")
        text += ("." if tier == "backed"
                 else " — it has not earned the armband yet.")
    return {"tier": tier, "reviewed": reviewed, "graded": graded,
            "wins": wins, "losses": losses, "aligned": aligned, "text": text}
