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
    assert "0 of 0" in out["text"]


def test_one_reviewed_gameweek_is_still_too_early():
    """The live state as this cycle ships. G1 exercises exactly this."""
    out = captain_confidence([_gw(1, -2)])
    assert out["tier"] == "early"
    assert out["graded"] == 1 and out["reviewed"] == 1
    assert "1 of 1" in out["text"]
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
