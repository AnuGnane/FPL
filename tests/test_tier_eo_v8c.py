"""The v8c refactor's rails: one fetch path, and the old one unchanged.

``tier_eo_table`` is now a five-line consumer of ``fetch_sample_picks`` and
``eo_from_picks``. Every assertion here is about that being invisible: the
cache file, the numbers in it, the trickle, and the empty-cached behaviour the
live tracker depends on.
"""

from __future__ import annotations

import json

import pytest

from gaffer.data.tier_eo import (eo_from_picks, eo_se, fetch_sample_picks,
                                 read_tier_cache, tier_cache_path,
                                 tier_eo_table, write_tier_cache)

PICKS = {
    101: [{"element": 7, "multiplier": 2}, {"element": 8, "multiplier": 1},
          {"element": 9, "multiplier": 0}],
    102: [{"element": 7, "multiplier": 1}, {"element": 8, "multiplier": 1}],
}


class FakeClient:
    """Two entries at page 1, and picks for both. Counts every call."""

    def __init__(self, picks=None, fail=()):
        self.picks = PICKS if picks is None else picks
        self.fail = set(fail)
        self.pages, self.fetched = [], []

    def get_league_standings(self, league_id, page=1):
        self.pages.append(page)
        return {"standings": {"results": [
            {"entry": 100 + slot} for slot in range(50)]}}

    def get_entry_picks(self, entry_id, gw):
        self.fetched.append((entry_id, gw))
        if entry_id in self.fail:
            raise RuntimeError("private entry")
        return {"picks": self.picks.get(entry_id, [])}


def test_the_shared_fetch_returns_squads_without_their_entry_ids(monkeypatch):
    """The anonymisation boundary is here, at the fetch: nothing downstream
    ever sees which entry a squad came from, so nothing downstream can leak
    it."""
    monkeypatch.setattr("gaffer.data.tier_eo.sample_slots",
                        lambda n, seed, **kw: [(1, 1), (1, 2)])
    monkeypatch.setattr("gaffer.data.tier_eo.FETCH_PAUSE_S", 0.0)
    out = fetch_sample_picks(FakeClient(), 3, sample=2)
    assert out == [PICKS[101], PICKS[102]]


def test_a_private_entry_is_one_fewer_sample_not_a_failure(monkeypatch):
    monkeypatch.setattr("gaffer.data.tier_eo.sample_slots",
                        lambda n, seed, **kw: [(1, 1), (1, 2)])
    monkeypatch.setattr("gaffer.data.tier_eo.FETCH_PAUSE_S", 0.0)
    out = fetch_sample_picks(FakeClient(fail=(101,)), 3, sample=2)
    assert out == [PICKS[102]]


def test_each_page_is_fetched_once_however_many_slots_it_serves(monkeypatch):
    monkeypatch.setattr("gaffer.data.tier_eo.sample_slots",
                        lambda n, seed, **kw: [(1, 1), (1, 2), (1, 3)])
    monkeypatch.setattr("gaffer.data.tier_eo.FETCH_PAUSE_S", 0.0)
    client = FakeClient()
    fetch_sample_picks(client, 3, sample=3)
    assert client.pages == [1]


def test_the_trickle_sleeps_between_entries_and_not_before_the_first(
        monkeypatch):
    """The anti-429 pause is the reason 455 requests are polite rather than
    rude. It has to survive the refactor, and it has to not cost a sleep on a
    one-entry sample."""
    slept = []
    monkeypatch.setattr("gaffer.data.tier_eo.sample_slots",
                        lambda n, seed, **kw: [(1, 1), (1, 2)])
    monkeypatch.setattr("gaffer.data.tier_eo.time.sleep", slept.append)
    fetch_sample_picks(FakeClient(), 3, sample=2)
    assert len(slept) == 1


def test_the_eo_estimator_is_the_one_the_tracker_has_always_shown():
    out = eo_from_picks([PICKS[101], PICKS[102]])
    # element 7: multipliers 2 and 1 over two entries -> 150%.
    assert out[7]["eo"] == 150.0
    assert out[7]["n"] == 2
    assert out[7]["se"] == round(eo_se(3.0, 5.0, 2), 1)
    # element 9 is benched by the only entry that owns him: EO contributions
    # are zero, so he is not in the table at all.
    assert 9 not in out


def test_no_readable_entry_is_an_empty_table_not_a_division_by_zero():
    assert eo_from_picks([]) == {}


def test_the_cache_helpers_round_trip_through_the_documented_path(tmp_path):
    assert tier_cache_path(3, tmp_path) == tmp_path / "3.json"
    write_tier_cache({7: {"eo": 1.0, "se": 0.1, "n": 2}}, 3, tmp_path)
    assert read_tier_cache(3, tmp_path) == {7: {"eo": 1.0, "se": 0.1, "n": 2}}


def test_the_cached_json_still_has_string_keys_on_disk(tmp_path):
    """The on-disk shape is a compatibility surface: a cache written by a
    v8a build must still load in a v8c one and vice versa."""
    write_tier_cache({7: {"eo": 1.0, "se": 0.1, "n": 2}}, 3, tmp_path)
    raw = json.loads((tmp_path / "3.json").read_text())
    assert list(raw) == ["7"]


def test_reading_an_absent_cache_is_none(tmp_path):
    assert read_tier_cache(3, tmp_path) is None


def test_the_table_writes_the_cache_and_serves_it_next_time(tmp_path,
                                                            monkeypatch):
    monkeypatch.setattr("gaffer.data.tier_eo.sample_slots",
                        lambda n, seed, **kw: [(1, 1), (1, 2)])
    monkeypatch.setattr("gaffer.data.tier_eo.FETCH_PAUSE_S", 0.0)
    client = FakeClient()
    first = tier_eo_table(client, 3, sample=2, raw_dir=tmp_path)
    calls = len(client.fetched)
    second = tier_eo_table(client, 3, sample=2, raw_dir=tmp_path)
    assert first == second
    assert len(client.fetched) == calls        # the second call fetched nothing


def test_an_empty_gameweek_is_cached_like_any_other(tmp_path, monkeypatch):
    """v7a's deliberate choice, unchanged: a gameweek where nobody's picks
    are readable is a fact about that gameweek, and re-sampling 300 entries on
    every tracker poll to rediscover it is the expensive way to learn it."""
    monkeypatch.setattr("gaffer.data.tier_eo.sample_slots",
                        lambda n, seed, **kw: [(1, 1)])
    monkeypatch.setattr("gaffer.data.tier_eo.FETCH_PAUSE_S", 0.0)
    client = FakeClient(fail=(101,))
    assert tier_eo_table(client, 3, sample=1, raw_dir=tmp_path) == {}
    assert tier_cache_path(3, tmp_path).is_file()
    assert tier_eo_table(client, 3, sample=1, raw_dir=tmp_path) == {}
    assert len(client.fetched) == 1


def test_the_table_is_exactly_the_estimator_over_the_shared_fetch(
        tmp_path, monkeypatch):
    """The single-code-path claim, asserted rather than asserted-in-prose."""
    monkeypatch.setattr("gaffer.data.tier_eo.sample_slots",
                        lambda n, seed, **kw: [(1, 1), (1, 2)])
    monkeypatch.setattr("gaffer.data.tier_eo.FETCH_PAUSE_S", 0.0)
    client = FakeClient()
    assert tier_eo_table(client, 3, sample=2, raw_dir=tmp_path) \
        == eo_from_picks([PICKS[101], PICKS[102]])
