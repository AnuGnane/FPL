"""``reports/drafts.json``: named what-if constraint sets.

Not saved squads. A squad frozen on Tuesday is wrong by Friday and says
nothing about why it was ever chosen; the constraints that produced it are
still exactly as true, and re-solving them is what makes "compare my drafts"
a live question rather than a scrapbook.
"""

from __future__ import annotations

import json

import pytest

from gaffer.drafts import (MAX_DRAFTS, add_draft, delete_draft, drafts_path,
                           load_drafts)
from gaffer.errors import GafferError

CONSTRAINTS = {"lock": [11], "ban": [], "force_in": [22], "force_out": [33],
               "max_hits": 1, "chip": "none", "horizon": 3}


def test_an_absent_store_is_an_empty_list(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_drafts() == []


def test_a_corrupt_store_is_an_empty_list(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    drafts_path().write_text("[[[")
    assert load_drafts() == []
    assert "drafts" in capsys.readouterr().out


def test_a_draft_round_trips_with_its_constraints(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    add_draft("Salah route", CONSTRAINTS)
    rows = load_drafts()
    assert len(rows) == 1
    assert rows[0]["name"] == "Salah route"
    assert rows[0]["constraints"] == CONSTRAINTS
    assert rows[0]["created_at"].startswith("20")


def test_unknown_constraint_keys_are_dropped(tmp_path, monkeypatch):
    """The store is fed by an HTTP body; it keeps the seven keys the solver
    understands and nothing else."""
    monkeypatch.chdir(tmp_path)
    add_draft("odd", {**CONSTRAINTS, "wildcard_everything": True})
    assert set(load_drafts()[0]["constraints"]) == {
        "lock", "ban", "force_in", "force_out", "max_hits", "chip", "horizon"}


def test_missing_constraint_keys_get_their_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    add_draft("bare", {})
    assert load_drafts()[0]["constraints"] == {
        "lock": [], "ban": [], "force_in": [], "force_out": [], "max_hits": 0,
        "chip": "none", "horizon": None}


def test_a_duplicate_name_is_refused(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    add_draft("Salah route", CONSTRAINTS)
    with pytest.raises(GafferError) as exc:
        add_draft("Salah route", CONSTRAINTS)
    assert "Salah route" in str(exc.value)


@pytest.mark.parametrize("name", ["", "   ", "x" * 100])
def test_an_unusable_name_is_refused(tmp_path, monkeypatch, name):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(GafferError):
        add_draft(name, CONSTRAINTS)


def test_the_store_is_capped_at_twelve(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for i in range(MAX_DRAFTS):
        add_draft(f"draft {i}", CONSTRAINTS)
    with pytest.raises(GafferError):
        add_draft("one too many", CONSTRAINTS)
    assert MAX_DRAFTS == 12


def test_deleting_by_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    add_draft("a", CONSTRAINTS)
    add_draft("b", CONSTRAINTS)
    assert delete_draft("a") is True
    assert [r["name"] for r in load_drafts()] == ["b"]
    assert delete_draft("a") is False


def test_the_file_is_written_atomically(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    add_draft("a", CONSTRAINTS)
    assert not list((tmp_path / "reports").glob("*.tmp"))
    assert "drafts" in json.loads(drafts_path().read_text())


def test_order_is_creation_order(tmp_path, monkeypatch):
    """The list is read top-down and the newest draft is the one being
    worked on, so it goes last rather than jumping the queue."""
    monkeypatch.chdir(tmp_path)
    for name in ("first", "second", "third"):
        add_draft(name, CONSTRAINTS)
    assert [r["name"] for r in load_drafts()] == ["first", "second", "third"]
