"""The manual badge: where a set-piece override applied, and only there."""

from __future__ import annotations

import pytest

from gaffer.web.routers.players import set_piece_manual, set_piece_orders


@pytest.fixture()
def clone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    return tmp_path


def test_no_override_file_marks_nobody(clone):
    assert set_piece_manual() == {}


def test_every_named_code_is_marked_with_the_kinds_it_was_named_for(clone):
    (clone / "data" / "set_pieces.toml").write_text(
        "[Arsenal]\npenalties = [1, 2]\ncorners = [2]\n")
    assert set_piece_manual() == {1: ["penalties"],
                                  2: ["corners", "penalties"]}


def test_a_malformed_file_marks_nobody(clone):
    (clone / "data" / "set_pieces.toml").write_text("[[[")
    assert set_piece_manual() == {}


def test_the_kinds_are_sorted_so_the_badge_is_stable(clone):
    (clone / "data" / "set_pieces.toml").write_text(
        "[Arsenal]\ncorners = [1]\npenalties = [1]\ndirect_free_kicks = [1]\n")
    assert set_piece_manual()[1] == ["corners", "direct_free_kicks",
                                     "penalties"]


def test_an_empty_list_marks_nobody_because_it_names_nobody(clone):
    (clone / "data" / "set_pieces.toml").write_text(
        "[Arsenal]\npenalties = []\n")
    assert set_piece_manual() == {}


def test_the_orders_are_the_file_s_ranks_for_the_codes_it_names(clone):
    (clone / "data" / "set_pieces.toml").write_text(
        "[Arsenal]\npenalties = [1, 2]\n")
    orders = set_piece_orders({1: 300, 2: 300})
    assert orders["penalties"] == {1: 1, 2: 2}
    assert orders["corners"] == {} and orders["direct_free_kicks"] == {}


def test_an_unlisted_teammate_is_served_no_order_at_all(clone):
    """The club rule, at the serving seam: 3 plays for the club the file
    spoke about and the file left him out, so he is not a taker. 4 plays
    somewhere else and keeps whatever FPL said — this map says nothing
    about him, and the row falls back."""
    (clone / "data" / "set_pieces.toml").write_text(
        "[Arsenal]\npenalties = [1]\n")
    orders = set_piece_orders({1: 300, 3: 300, 4: 301})
    assert orders["penalties"] == {1: 1, 3: None}


def test_a_demoted_teammate_is_badged_because_his_blank_is_the_file_s(clone):
    (clone / "data" / "set_pieces.toml").write_text(
        "[Arsenal]\npenalties = [1]\n")
    assert set_piece_manual({1: 300, 3: 300}) == {1: ["penalties"],
                                                 3: ["penalties"]}


def test_without_a_club_map_only_the_named_codes_are_touched(clone):
    """A caller with no snapshot in hand can identify no club, so the file
    only adds — the pre-ruling behaviour, and the degradation rail's."""
    (clone / "data" / "set_pieces.toml").write_text(
        "[Arsenal]\npenalties = [1]\n")
    assert set_piece_orders()["penalties"] == {1: 1}


def test_the_row_schema_carries_the_kinds(clone):
    from gaffer.web.schemas import PlayerRow

    assert "set_piece_manual" in PlayerRow.model_fields
    assert PlayerRow.model_fields["set_piece_manual"].is_required() is False


def test_the_route_count_did_not_move(clone):
    """By absence, as the W4 rails are: the single absolute route pin lives in
    tests/test_v11_degradation.py, and the badge is an additive field on two
    existing payloads rather than a route of its own."""
    from gaffer.web.app import create_app

    paths = create_app().openapi()["paths"]
    assert not [p for p in paths if p.startswith("/api/setpieces")
                or p.startswith("/api/set-pieces")]
