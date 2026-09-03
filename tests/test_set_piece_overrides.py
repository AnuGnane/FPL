"""The hand-edited set-piece override: what it can and cannot say."""

from __future__ import annotations

import pytest

from gaffer.data.set_piece_overrides import (OVERRIDE_PATH, SET_PIECE_KINDS,
                                             load_set_piece_overrides,
                                             penalty_order_overrides)


@pytest.fixture()
def clone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    return tmp_path


def _write(clone, text: str):
    (clone / OVERRIDE_PATH).write_text(text)


def test_the_three_kinds_are_named_and_stable():
    assert SET_PIECE_KINDS == ("penalties", "direct_free_kicks", "corners")


def test_no_file_is_an_empty_override_not_a_crash(clone):
    assert load_set_piece_overrides() == {}
    assert penalty_order_overrides() == {}


def test_ordered_takers_become_one_based_orders(clone):
    _write(clone, """
[Arsenal]
penalties = [123, 456]
corners = [456]
""")
    out = load_set_piece_overrides()
    assert out["Arsenal"]["penalties"] == {123: 1, 456: 2}
    assert out["Arsenal"]["corners"] == {456: 1}
    assert out["Arsenal"]["direct_free_kicks"] == {}


def test_penalty_order_overrides_flattens_across_clubs(clone):
    _write(clone, """
[Arsenal]
penalties = [123, 456]

[Chelsea]
penalties = [789]
""")
    assert penalty_order_overrides() == {123: 1, 456: 2, 789: 1}


def test_a_malformed_file_is_an_empty_override_and_a_printed_line(clone,
                                                                  capsys):
    _write(clone, "this is not toml [[[")
    assert load_set_piece_overrides() == {}
    assert "set pieces:" in capsys.readouterr().out


def test_an_unknown_kind_is_ignored_rather_than_carried(clone):
    _write(clone, """
[Arsenal]
penalties = [1]
throw_ins = [2]
""")
    out = load_set_piece_overrides()
    assert set(out["Arsenal"]) == set(SET_PIECE_KINDS)


def test_a_non_integer_code_is_dropped_not_coerced(clone, capsys):
    _write(clone, """
[Arsenal]
penalties = [123, "Saka", 456]
""")
    assert load_set_piece_overrides()["Arsenal"]["penalties"] == {123: 1,
                                                                 456: 2}
    assert "not a player code" in capsys.readouterr().out


def test_a_duplicate_code_keeps_its_first_position(clone):
    _write(clone, """
[Arsenal]
penalties = [123, 456, 123]
""")
    assert load_set_piece_overrides()["Arsenal"]["penalties"] == {123: 1,
                                                                 456: 2}


def test_a_club_with_an_empty_list_says_nobody_takes_them(clone):
    """An empty list is a statement, not an absence: it is how a user says
    "the published taker has left and nobody has replaced him yet"."""
    _write(clone, """
[Arsenal]
penalties = []
""")
    out = load_set_piece_overrides()
    assert out["Arsenal"]["penalties"] == {}
    assert "Arsenal" in out


def test_the_shipped_example_parses_and_documents_all_three_kinds():
    from gaffer.assets import load_set_pieces_example

    text = load_set_pieces_example()
    for kind in SET_PIECE_KINDS:
        assert kind in text
