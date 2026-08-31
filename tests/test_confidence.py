"""Confidence framing: prose the ledger entitles the tool to write.

The failure mode this guards is the one every consumer FPL tool has — a
percentage next to a recommendation, computed from nothing. So the tests are
mostly about refusal: with one reviewed gameweek the answer is "too early",
with four it quotes four, and there is no branch anywhere that produces a
number the ledger did not count.
"""

from __future__ import annotations

import pytest

from gaffer.confidence import MIN_GRADED, captain_confidence


def _gw(gw: int, delta: int | None, *, aligned: bool = False) -> dict:
    return {"gw": gw, "lanes": [
        {"lane": "transfers", "delta_pts": 3},
        {"lane": "captaincy", "delta_pts": delta, "aligned": aligned},
    ]}


def test_an_empty_ledger_is_too_early_and_says_zero():
    out = captain_confidence([])
    assert out["tier"] == "early"
    assert out["graded"] == 0 and out["reviewed"] == 0
    assert "0 gameweeks reviewed" in out["text"]


def test_one_reviewed_gameweek_is_still_too_early():
    """The live state as this cycle ships. G1 exercises exactly this."""
    out = captain_confidence([_gw(1, -2)])
    assert out["tier"] == "early"
    assert out["graded"] == 1 and out["reviewed"] == 1
    assert "1 gameweek reviewed" in out["text"]
    assert "too early" in out["text"].lower()


def test_an_ungraded_lane_counts_as_reviewed_but_not_as_graded():
    """"The model's captain was not in your eleven" is not evidence either
    way, and must not be scored as agreement."""
    ledger = [_gw(1, None), _gw(2, -3), _gw(3, 1), _gw(4, -1), _gw(5, -2)]
    out = captain_confidence(ledger)
    assert out["reviewed"] == 5 and out["graded"] == 4


def test_four_graded_weeks_reaches_a_verdict():
    ledger = [_gw(g, -2) for g in range(1, MIN_GRADED + 1)]
    out = captain_confidence(ledger)
    assert out["tier"] == "backed"
    assert out["wins"] == MIN_GRADED and out["losses"] == 0
    assert f"{MIN_GRADED} of {MIN_GRADED}" in out["text"]


def test_the_sign_convention_is_mine_minus_the_models():
    """``review._lane`` scores my choice minus the model's, so a negative
    delta is a week the model was right and a positive one is a week I was."""
    ledger = [_gw(1, -2), _gw(2, -1), _gw(3, 5), _gw(4, 4)]
    out = captain_confidence(ledger)
    assert out["wins"] == 2 and out["losses"] == 2
    assert out["tier"] == "mixed"
    assert "not earned the armband" in out["text"]


def test_an_aligned_week_is_neither_a_win_nor_a_loss():
    """I picked the model's own captain: there is nothing to compare."""
    ledger = [_gw(1, 0, aligned=True), _gw(2, 0, aligned=True),
              _gw(3, -3), _gw(4, -1)]
    out = captain_confidence(ledger)
    assert out["aligned"] == 2
    assert out["wins"] == 2 and out["losses"] == 0
    assert "2 you agreed on" in out["text"]


def test_an_aligned_week_is_not_in_the_graded_denominator():
    """B4. ``graded`` is ``wins + losses`` and nothing else.

    Four weeks of agreement used to clear MIN_GRADED, then divide zero wins by
    four "comparable" gameweeks and conclude the model *has not earned the
    armband* — a verdict against the tool built entirely out of weeks the user
    took its advice.
    """
    ledger = [_gw(g, 0, aligned=True) for g in range(1, 5)]
    out = captain_confidence(ledger)
    assert out["graded"] == 0
    assert out["reviewed"] == 4 and out["aligned"] == 4
    assert out["tier"] == "early"
    assert "not earned the armband" not in out["text"]
    assert "none gradeable yet" in out["text"]
    assert "4 gameweeks reviewed" in out["text"]


def test_the_early_sentence_quotes_reviewed_not_a_ratio():
    """The reviewer's repro at n=1: one lane, one number in the sentence."""
    out = captain_confidence([_gw(1, -2)])
    assert out["reviewed"] == 1 and out["graded"] == 1
    assert "1 gameweek reviewed" in out["text"]
    assert " of " not in out["text"]


def test_four_graded_weeks_survive_extra_aligned_ones():
    """Aligned weeks are quoted, never counted: four real comparisons still
    reach a verdict with a dozen agreements sitting beside them."""
    ledger = ([_gw(g, -2) for g in range(1, 5)]
              + [_gw(g, 0, aligned=True) for g in range(5, 17)])
    out = captain_confidence(ledger)
    assert out["tier"] == "backed" and out["graded"] == 4
    assert "4 of 4" in out["text"] and "12 you agreed on" in out["text"]


def test_a_lane_that_says_nothing_survived_is_not_reviewed():
    """A pruned gameweek carries a captaincy lane whose note says the advice
    is gone. Counting it as reviewed inflates the denominator of the refusal
    sentence with weeks nobody ever looked at."""
    ledger = [{"gw": 1, "lanes": [{
        "lane": "captaincy", "delta_pts": None, "aligned": False,
        "note": "no banked advice survives for this gameweek"}]},
        _gw(2, -1)]
    out = captain_confidence(ledger)
    assert out["reviewed"] == 1 and out["graded"] == 1


def test_a_ledger_row_with_no_captaincy_lane_is_skipped_not_crashed():
    out = captain_confidence([{"gw": 1, "lanes": []}, {"gw": 2}])
    assert out["reviewed"] == 0 and out["tier"] == "early"


def test_junk_in_the_ledger_never_raises():
    """The ledger is a file on disk that a laptop may have died mid-write to,
    and a captain card is not worth a 500."""
    out = captain_confidence(["nonsense", {"lanes": "no"}, None])
    assert out["tier"] == "early" and out["reviewed"] == 0


def test_the_text_never_contains_a_percentage():
    """D3's whole point: tiers quote counts, not manufactured confidence."""
    for ledger in ([], [_gw(1, -1)], [_gw(g, -1) for g in range(1, 9)]):
        assert "%" not in captain_confidence(ledger)["text"]
