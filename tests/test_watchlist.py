"""The starred-player store: a bookmark, and nothing more than a bookmark.

``overrides.py``'s shape with the two numbers removed, which removes most of
its tests with them — there is no range to clip, no coherence to warn about
and no model that has to obey anything. What is left is the part that still
matters on a store the availability pass and a launchd job both read: an
absent file is an empty list, a corrupt one is an empty list, a write is
atomic, and a cap exists.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from gaffer import artifacts
from gaffer.errors import GafferError
from gaffer.watchlist import (MAX_WATCHED, NOTE_MAX, load_watchlist,
                              save_watchlist, unwatch, watch, watch_targets,
                              watched_codes)


@pytest.fixture(autouse=True)
def _tmp_reports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()


def test_an_absent_store_is_an_empty_watchlist():
    assert load_watchlist() == {}
    assert watched_codes() == []


def test_a_star_round_trips_with_its_note():
    watch(11, note="rotation risk, watch the presser")
    rows = load_watchlist()
    assert list(rows) == [11]
    assert rows[11]["note"] == "rotation risk, watch the presser"
    assert rows[11]["set_at"]


def test_a_second_star_on_the_same_player_replaces_the_note():
    watch(11, note="first")
    watch(11, note="second")
    assert load_watchlist()[11]["note"] == "second"
    assert len(load_watchlist()) == 1


def test_a_star_needs_no_note_at_all():
    """A bookmark with nothing written on it is still a bookmark — the whole
    difference between this store and the override store."""
    watch(11)
    assert load_watchlist()[11]["note"] == ""


def test_codes_come_back_sorted_and_as_integers():
    """JSON object keys are strings by definition; this is where they stop
    being strings, so a caller looking one up with an int cannot miss."""
    for code in (33, 11, 22):
        watch(code)
    assert watched_codes() == [11, 22, 33]


def test_unwatching_removes_one_and_reports_whether_it_did():
    watch(11)
    assert unwatch(11) is True
    assert unwatch(11) is False
    assert load_watchlist() == {}


def test_an_unknown_code_is_refused_when_a_universe_is_given():
    with pytest.raises(GafferError, match="not in the current player list"):
        watch(999, known_codes=[11, 22])


def test_the_universe_check_is_skipped_when_there_is_no_universe():
    watch(999)
    assert watched_codes() == [999]


def test_a_long_note_is_refused_rather_than_truncated():
    """A silently halved note is a sentence the user did not write."""
    with pytest.raises(GafferError, match="longer than"):
        watch(11, note="x" * (NOTE_MAX + 1))


def test_the_cap_refuses_the_hundred_and_first_but_not_a_re_star():
    for code in range(1, MAX_WATCHED + 1):
        watch(code)
    with pytest.raises(GafferError, match="is the cap"):
        watch(MAX_WATCHED + 1)
    watch(1, note="re-starring an existing one is always allowed")
    assert len(load_watchlist()) == MAX_WATCHED


def test_a_corrupt_store_reads_as_an_empty_one(capsys):
    (artifacts.REPORTS / "watchlist.json").write_text("{not json")
    assert load_watchlist() == {}
    assert "watchlist store unreadable" in capsys.readouterr().out


@pytest.mark.parametrize("payload", ['[]', '{"watchlist": []}',
                                     '{"watchlist": {"11": "nonsense"}}',
                                     '{}'])
def test_a_store_whose_shape_has_drifted_reads_as_empty_or_skips_the_row(
        payload):
    (artifacts.REPORTS / "watchlist.json").write_text(payload)
    assert load_watchlist() in ({}, {})


def test_the_write_is_atomic_and_leaves_no_temp_behind():
    watch(11)
    assert not (artifacts.REPORTS / "watchlist.json.tmp").exists()
    assert json.loads(
        (artifacts.REPORTS / "watchlist.json").read_text())["watchlist"]


def test_saving_an_empty_store_is_a_file_not_a_deletion():
    """``unwatch`` of the last star must leave a readable empty store rather
    than an absent one that a half-written file is indistinguishable from."""
    watch(11)
    unwatch(11)
    assert (artifacts.REPORTS / "watchlist.json").exists()
    assert load_watchlist() == {}


def test_saving_creates_the_reports_directory_on_a_fresh_clone(tmp_path):
    (tmp_path / "reports").rmdir()
    save_watchlist({11: {"note": "", "set_at": ""}})
    assert load_watchlist()[11]["note"] == ""


def test_the_watch_target_of_a_bare_clone_is_the_stars_alone():
    """No solve state, no advice payload — and a star is still a star."""
    watch(11)
    assert watch_targets() == {11: "watchlist"}


def test_the_watch_target_is_empty_when_nothing_is_watched_at_all():
    assert watch_targets() == {}


def test_a_second_writers_temp_file_survives_this_writers_unlink(monkeypatch):
    """Two saves racing must not share one temp name.

    The old fixed ``watchlist.json.tmp`` gave both writers the same sibling:
    whichever renamed first then unlinked the other's half-written file in its
    ``finally``, and the loser's ``os.replace`` raised ``FileNotFoundError``.
    Here writer B — another process, another pid — starts its temp file while
    A is renaming, and must still find it afterwards.

    v12 W1 §2.11: the rename moved into ``gaffer.io``, so the spy follows it.
    The claim is unchanged.
    """
    from gaffer import io as gio

    path = artifacts.REPORTS / "watchlist.json"
    real_replace = os.replace
    renamed, other = [], {}

    def spy(src, dst):
        renamed.append(Path(src).name)
        if len(renamed) == 1:
            b_tmp = Path(dst).with_name(f"{Path(dst).name}.999999.tmp")
            b_tmp.write_text(json.dumps(
                {"watchlist": {"7": {"note": "b", "set_at": ""}}}))
            other["tmp"] = b_tmp
        real_replace(src, dst)

    monkeypatch.setattr(gio.os, "replace", spy)
    save_watchlist({11: {"note": "a", "set_at": ""}})

    assert renamed == [f"watchlist.json.{os.getpid()}.tmp"]
    assert other["tmp"].exists(), "A's finally unlinked B's temp file"
    real_replace(other["tmp"], path)
    assert list(load_watchlist()) == [7]
