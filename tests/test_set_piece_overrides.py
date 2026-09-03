"""The hand-edited set-piece override: what it can and cannot say."""

from __future__ import annotations

import pytest

from gaffer.data.set_piece_overrides import (SET_PIECE_KINDS,
                                             load_set_piece_overrides,
                                             override_path,
                                             penalty_order_overrides)


@pytest.fixture()
def clone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    return tmp_path


def _write(clone, text: str):
    override_path().write_text(text)


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


def test_the_path_follows_a_redirected_data_directory(tmp_path, monkeypatch):
    """The idiom every other reader in this package obeys: the file lives
    under ``store.DATA_DIR``, read at call time, so a test that moves the
    data directory moves this too without changing the process's cwd."""
    from gaffer.data import store

    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "elsewhere")
    (tmp_path / "elsewhere").mkdir()
    assert override_path() == tmp_path / "elsewhere" / "set_pieces.toml"
    override_path().write_text("[Arsenal]\npenalties = [123]\n")
    assert penalty_order_overrides() == {123: 1}


def test_a_quoted_club_header_parses(clone):
    """Two of the twenty clubs cannot be written as a bare TOML key at all —
    a space is not allowed in one, nor an apostrophe. Quoted, they are."""
    _write(clone, """
["Man City"]
penalties = [123]

["Nott'm Forest"]
corners = [456]
""")
    out = load_set_piece_overrides()
    assert out["Man City"]["penalties"] == {123: 1}
    assert out["Nott'm Forest"]["corners"] == {456: 1}


def test_an_unquoted_header_is_named_by_line_and_column(clone, capsys):
    """One bad header discards the *whole* file, so the printed line has to
    say where to look — otherwise a user whose Arsenal table is fine cannot
    tell that his Man City table three lines down killed both."""
    _write(clone, '[Arsenal]\npenalties = [1]\n\n[Man City]\ncorners = [2]\n')
    assert load_set_piece_overrides() == {}
    out = capsys.readouterr().out
    assert "line 4" in out
    assert "whole file" in out


def test_the_shipped_example_parses_and_documents_all_three_kinds():
    from gaffer.assets import load_set_pieces_example

    text = load_set_pieces_example()
    for kind in SET_PIECE_KINDS:
        assert kind in text


def test_the_shipped_example_parses_once_its_sample_is_uncommented(clone):
    """The template is a file a user uncomments. If the form it teaches does
    not parse, the first thing he does with it discards everything he typed
    — which is why every header it shows is quoted."""
    import re

    from gaffer.assets import load_set_pieces_example

    body = "\n".join(
        re.sub(r"^# ", "", line) for line in
        load_set_pieces_example().splitlines()
        if re.match(r"^# (\[|penalties|direct_free_kicks|corners)", line))
    assert "[" in body                      # the sample is still in there
    _write(clone, body)
    out = load_set_piece_overrides()
    assert out and all(club.strip() for club in out)
