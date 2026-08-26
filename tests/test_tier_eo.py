"""Sampled top-10k effective ownership. No network: every call goes through
httpx.MockTransport wired into the real client."""

import json

import httpx
import pytest

from gaffer.api.client import FPLClient
from gaffer.data.tier_eo import (MAX_PAGE, PAGE_SIZE, eo_se,
                                 fetch_tier_entries, sample_slots,
                                 tier_eo_table)


def test_sample_slots_are_distinct_page_slot_pairs():
    slots = sample_slots(300, seed=1)
    assert len(slots) == 300
    assert len(set(slots)) == 300
    assert all(1 <= page <= MAX_PAGE and 0 <= slot < PAGE_SIZE
               for page, slot in slots)


def test_sample_slots_are_deterministic_for_a_seed():
    assert sample_slots(50, seed=7) == sample_slots(50, seed=7)
    assert sample_slots(50, seed=7) != sample_slots(50, seed=8)


def test_sample_slots_are_sorted_so_pages_are_fetched_once():
    slots = sample_slots(40, seed=3)
    assert slots == sorted(slots)


def _tier_transport(calls: list):
    """League 314 standings plus per-entry picks; 50 entries a page."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "leagues-classic" in path:
            page = int(request.url.params.get("page_standings", 1))
            calls.append(("page", page))
            return httpx.Response(200, json={"standings": {
                "has_next": True,
                "results": [{"entry": page * 1000 + slot}
                            for slot in range(PAGE_SIZE)]}})
        parts = path.rstrip("/").split("/")
        entry = int(parts[-4])
        calls.append(("picks", entry))
        # Everyone owns 1; every other entry captains him; nobody owns 2.
        return httpx.Response(200, json={"picks": [
            {"element": 1, "multiplier": 2 if entry % 2 == 0 else 1},
            {"element": 3, "multiplier": 0}]})

    return httpx.MockTransport(handler)


def test_fetch_tier_entries_reuses_a_page_across_its_slots(tmp_path):
    calls: list = []
    client = FPLClient(raw_dir=tmp_path / "raw",
                       transport=_tier_transport(calls))
    entries = fetch_tier_entries(client, [(1, 0), (1, 5), (2, 3)])
    assert entries == [1000, 1005, 2003]
    assert [c for c in calls if c[0] == "page"] == [("page", 1), ("page", 2)]


def test_tier_eo_table_counts_captaincy_and_reports_a_standard_error(tmp_path):
    calls: list = []
    client = FPLClient(raw_dir=tmp_path / "raw",
                       transport=_tier_transport(calls))
    out = tier_eo_table(client, gw=3, sample=4, seed=11,
                        raw_dir=tmp_path / "tier")
    assert out[1]["n"] == 4
    # Two of the four captain him, two own him: EO = (2*2 + 1*2) / 4 = 150%.
    assert out[1]["eo"] == 150.0
    # The SE is of the EO estimate itself: contributions [2, 2, 1, 1], sample
    # stdev 0.5774, over sqrt(4) = 0.2887 -> 28.9 percentage points. The old
    # binomial-ownership bar read 0.0 here, which claimed a captaincy split
    # down the middle was measured without error.
    assert out[1]["se"] == 28.9
    assert 3 not in out                      # benched by everyone


def test_tier_eo_table_caches_per_gameweek(tmp_path):
    calls: list = []
    cache = tmp_path / "tier"
    client = FPLClient(raw_dir=tmp_path / "raw",
                       transport=_tier_transport(calls))
    first = tier_eo_table(client, gw=3, sample=4, seed=11, raw_dir=cache)
    picks_calls = len([c for c in calls if c[0] == "picks"])
    assert json.loads((cache / "3.json").read_text())
    second = tier_eo_table(client, gw=3, sample=4, seed=11, raw_dir=cache)
    assert len([c for c in calls if c[0] == "picks"]) == picks_calls
    assert second == first


def test_tier_eo_table_of_a_sample_nobody_answered_is_empty(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if "leagues-classic" in request.url.path:
            return httpx.Response(200, json={"standings": {
                "has_next": True,
                "results": [{"entry": 1} for _ in range(PAGE_SIZE)]}})
        return httpx.Response(404, json={"detail": "Not found."})

    client = FPLClient(raw_dir=tmp_path / "raw", retries=1,
                       transport=httpx.MockTransport(handler))
    assert tier_eo_table(client, gw=3, sample=2, seed=1,
                         raw_dir=tmp_path / "tier") == {}


def test_an_empty_tier_sample_is_cached_like_any_other(tmp_path):
    """The live tracker polls; re-sampling hundreds of entries every poll to
    rediscover that none of them are readable is the expensive way to learn
    it. The empty result is a fact about the gameweek."""
    calls: list = []
    cache = tmp_path / "tier"

    def handler(request: httpx.Request) -> httpx.Response:
        if "leagues-classic" in request.url.path:
            return httpx.Response(200, json={"standings": {
                "has_next": True,
                "results": [{"entry": 1} for _ in range(PAGE_SIZE)]}})
        calls.append(request.url.path)
        return httpx.Response(404, json={"detail": "Not found."})

    client = FPLClient(raw_dir=tmp_path / "raw", retries=1,
                       transport=httpx.MockTransport(handler))
    assert tier_eo_table(client, gw=3, sample=2, seed=1, raw_dir=cache) == {}
    assert (cache / "3.json").read_text() == "{}"
    after = len(calls)
    assert tier_eo_table(client, gw=3, sample=2, seed=1, raw_dir=cache) == {}
    assert len(calls) == after                # served from disk


def test_eo_se_is_the_standard_error_of_the_mean_contribution():
    # Contributions [2, 2, 1, 1]: total 6, sum of squares 10, n 4.
    assert eo_se(6.0, 10.0, 4) == pytest.approx(28.8675, abs=1e-3)
    # Everyone contributes the same: no spread, no error bar.
    assert eo_se(4.0, 4.0, 4) == 0.0
    # A single sample has no sample stdev at all.
    assert eo_se(1.0, 1.0, 1) == 0.0
    assert eo_se(0.0, 0.0, 0) == 0.0
