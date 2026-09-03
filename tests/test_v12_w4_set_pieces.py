"""The set-piece override's one read hook, and the rail it must not break."""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.set_pieces import PenPriors, pen_table

COMP = pd.DataFrame({"code": [1, 2], "team_code": [3, 3],
                     "position": ["MID", "MID"], "p_play": [0.9, 0.9]})
PLAYERS = pd.DataFrame({"code": [1, 2], "name": ["A", "B"],
                        "penalties_order": [1, None]})
PRIORS = PenPriors(share_hist={}, league_pens_pg=0.13, team_games=100)

# Two clubs, so a file that speaks about one of them can be shown not to
# speak about the other: 1 and 2 are team_code 3, 3 and 4 are team_code 8,
# and FPL has the first man at each club down as the taker.
TWO_CLUBS = pd.DataFrame({"code": [1, 2, 3, 4], "team_code": [3, 3, 8, 8],
                          "position": ["MID"] * 4, "p_play": [0.9] * 4})
TWO_CLUBS_PLAYERS = pd.DataFrame(
    {"code": [1, 2, 3, 4], "name": ["A", "B", "C", "D"],
     "penalties_order": [1, None, 1, None]})


@pytest.fixture()
def clone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    return tmp_path


def test_no_override_file_is_byte_identical_to_before(clone):
    """The rail. Every machine is in this state until someone writes one."""
    table = pen_table(COMP, PLAYERS, PRIORS)
    assert table["share_now"].tolist() == [1.0, 0.0]


def test_an_override_moves_the_armband(clone):
    (clone / "data" / "set_pieces.toml").write_text(
        "[Arsenal]\npenalties = [2, 1]\n")
    table = pen_table(COMP, PLAYERS, PRIORS)
    assert table["share_now"].tolist() == [0.15, 1.0]


def test_a_partial_listing_demotes_the_taker_it_leaves_out(clone):
    """The one a user actually types: "the new man takes them now".

    A club's queue is exactly what the file lists for it, so player 1 — FPL's
    order 1, and this file's nobody — is not a taker. Before the 2026-09-03
    ruling the file only *added*, and this line read ``[1.0, 1.0]``: two men
    at one club each priced for every penalty it wins.
    """
    (clone / "data" / "set_pieces.toml").write_text(
        "[Arsenal]\npenalties = [2]\n")
    assert pen_table(COMP, PLAYERS, PRIORS)["share_now"].tolist() == [0.0, 1.0]


def test_the_club_it_does_not_speak_about_keeps_its_bootstrap_queue(clone):
    """The demotion is per club, not league-wide: naming Arsenal's taker says
    nothing about Chelsea's, who keeps the order FPL published."""
    (clone / "data" / "set_pieces.toml").write_text(
        "[Arsenal]\npenalties = [2]\n")
    table = pen_table(TWO_CLUBS, TWO_CLUBS_PLAYERS, PRIORS)
    assert table["share_now"].tolist() == [0.0, 1.0, 1.0, 0.0]


def test_two_team_codes_under_one_header_are_two_queues(clone):
    """The header is a comment; the codes are the key. A file that lists a
    Chelsea code under ``[Arsenal]`` — a transfer typed in the wrong table —
    still resolves each man's club from the frame, and demotes at both."""
    (clone / "data" / "set_pieces.toml").write_text(
        "[Arsenal]\npenalties = [2, 4]\n")
    table = pen_table(TWO_CLUBS, TWO_CLUBS_PLAYERS, PRIORS)
    assert table["share_now"].tolist() == [0.0, 1.0, 0.0, 0.15]


def test_an_override_naming_nobody_in_the_frame_changes_nothing(clone,
                                                                capsys):
    (clone / "data" / "set_pieces.toml").write_text(
        "[Arsenal]\npenalties = [999]\n")
    assert pen_table(COMP, PLAYERS, PRIORS)["share_now"].tolist() == [1.0, 0.0]
    # No code, no club, no demotion — and a printed line, because a silent
    # no-op is a correction the user thinks took.
    assert "999" in capsys.readouterr().out


def test_a_malformed_override_file_changes_nothing(clone):
    (clone / "data" / "set_pieces.toml").write_text("not toml [[[")
    assert pen_table(COMP, PLAYERS, PRIORS)["share_now"].tolist() == [1.0, 0.0]


def test_an_empty_list_does_not_remove_the_published_taker(clone):
    (clone / "data" / "set_pieces.toml").write_text(
        "[Arsenal]\npenalties = []\n")
    # An empty list names no code, so it identifies no club, so it demotes
    # nobody and the bootstrap stands. It records that the user looked and
    # found nobody; to demote a taker, list the club's replacement queue —
    # which is what the test above does with one name.
    assert pen_table(COMP, PLAYERS, PRIORS)["share_now"].tolist() == [1.0, 0.0]
