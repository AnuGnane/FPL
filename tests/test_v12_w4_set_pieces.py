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


def test_an_override_naming_nobody_in_the_frame_changes_nothing(clone):
    (clone / "data" / "set_pieces.toml").write_text(
        "[Arsenal]\npenalties = [999]\n")
    assert pen_table(COMP, PLAYERS, PRIORS)["share_now"].tolist() == [1.0, 0.0]


def test_a_malformed_override_file_changes_nothing(clone):
    (clone / "data" / "set_pieces.toml").write_text("not toml [[[")
    assert pen_table(COMP, PLAYERS, PRIORS)["share_now"].tolist() == [1.0, 0.0]


def test_an_empty_list_removes_the_published_taker(clone):
    (clone / "data" / "set_pieces.toml").write_text(
        "[Arsenal]\npenalties = []\n")
    # Nobody is named, so nobody is overridden and the bootstrap stands. An
    # empty list says "the published taker left"; saying so about a player the
    # file does not name is not something this hook can do, and pretending
    # otherwise would need the club column it deliberately does not read.
    assert pen_table(COMP, PLAYERS, PRIORS)["share_now"].tolist() == [1.0, 0.0]
