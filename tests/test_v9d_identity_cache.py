"""``with_identity`` reads the same three parquets on every advice request.

Three small files, re-read and re-projected into dicts on every page load, on
a machine that refreshes them at most a few times a day. The memo is keyed on
the file's own identity — path, mtime and size — so a refreshed parquet misses
naturally and there is no TTL to be wrong about.

Two things this file pins that are easy to get wrong later:

* **The key resolves the path on every call.** ``store.DATA_DIR`` is a
  module-level ``Path("data")`` and this suite changes the process CWD
  constantly. A cache keyed on the relative string alone would hand one
  test's ``teams.parquet`` to the next test's tmpdir — and, worse, one user's
  data directory to another's.
* **``_difficulty_by_team`` is not cached** (plan A7). It calls
  ``meta.ticker``, which composes odds, Elo and fixtures; there is no single
  file to stat, and a key that pretended otherwise would serve a stale tint
  after an odds refresh. So its reads are excluded from the counts below.

  Plan A7 expected to exclude them *by path* — count only the three identity
  paths and let the ticker's own reads through. The tree is harsher than that:
  ``meta.ticker`` reads ``live/teams.parquet`` and
  ``live/fixtures_all.parquet``, the very paths being counted, so a
  path filter cannot tell whose read it is looking at. The exclusion is
  therefore made at the seam — ``_difficulty_by_team`` is stubbed — which is
  the assertion plan A7 actually wanted and one a later reader cannot loosen
  into a false pass.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.data import store
from gaffer.web import identity


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    identity.clear_cache()
    (tmp_path / "data" / "live").mkdir(parents=True)
    store.save(pd.DataFrame({"code": [3], "short_name": ["ARS"],
                             "team_id": [1]}), "live/teams.parquet")
    store.save(pd.DataFrame({"code": [7], "team_code": [3]}),
               "live/players.parquet")
    store.save(pd.DataFrame({"gw": [9], "finished": [False], "home_id": [1],
                             "away_id": [1],
                             "kickoff_time": ["2026-01-01T12:00:00Z"]}),
               "live/fixtures_all.parquet")
    # The uncached ticker reads two of the three counted paths itself; see
    # this module's docstring. Stubbed so every read below is identity's own.
    monkeypatch.setattr(identity, "_difficulty_by_team", lambda gws: {})
    reads: list[str] = []
    real = store.load
    monkeypatch.setattr(store, "load",
                        lambda rel: (reads.append(rel), real(rel))[1])
    yield tmp_path, reads
    identity.clear_cache()


IDENTITY_PATHS = {"live/teams.parquet", "live/players.parquet",
                  "live/fixtures_all.parquet"}


def _payload() -> dict:
    return {"xi": [{"code": 7, "name": "Someone", "ep": 5.0}]}


def test_a_second_call_reads_none_of_the_three_identity_files(wired):
    """The whole point. The ticker's own reads are allowed and are not
    counted — see this module's docstring and plan A7."""
    _tmp, reads = wired
    identity.with_identity(_payload(), 9)
    reads.clear()
    identity.with_identity(_payload(), 9)
    assert not (set(reads) & IDENTITY_PATHS)


def test_the_second_call_returns_the_same_answer(wired):
    """A cache that changes an answer is a bug with better latency."""
    first = identity.with_identity(_payload(), 9)
    second = identity.with_identity(_payload(), 9)
    assert first == second


def test_a_refreshed_parquet_is_re_read(wired):
    """No TTL: a new mtime is the invalidation. This is the assertion that
    fails if someone caches on the relative path alone."""
    tmp, reads = wired
    identity.with_identity(_payload(), 9)
    reads.clear()
    store.save(pd.DataFrame({"code": [3], "short_name": ["ARSENAL"],
                             "team_id": [1]}), "live/teams.parquet")
    out = identity.with_identity(_payload(), 9)
    assert "live/teams.parquet" in reads
    assert out["xi"][0]["team_short"] == "ARSENAL"


def test_a_missing_file_is_read_uncached_and_still_never_raises(wired):
    """A ``stat`` failure means "read it uncached", not "fail". The module's
    standing contract is that nothing here raises, and a cache is not a
    reason to start."""
    tmp, _reads = wired
    (tmp / "data" / "live" / "players.parquet").unlink()
    out = identity.with_identity(_payload(), 9)
    assert out["xi"][0]["team_code"] is None


def test_a_different_gameweek_is_not_served_the_first_ones_fixtures(wired):
    """The fixture map is per gameweek, so the gameweek is part of its key.
    Serving GW9's opener for GW10 would be a silently wrong chip."""
    identity.with_identity(_payload(), 9)
    out = identity.with_identity(_payload(), 10)
    assert out["xi"][0]["next_fixture"] is None


def test_alternating_gameweeks_do_not_evict_each_other(wired):
    """Two gameweeks in flight is ordinary traffic — a live matchday page
    beside a planning one — and with one shared fixture slot each request
    would evict the other's map and re-read the parquet, which is the cost
    the memo exists to remove."""
    _tmp, reads = wired
    identity.with_identity(_payload(), 9)
    identity.with_identity(_payload(), 10)
    reads.clear()
    identity.with_identity(_payload(), 9)
    identity.with_identity(_payload(), 10)
    assert not (set(reads) & IDENTITY_PATHS)


def test_the_cache_stays_bounded(wired):
    """Per-gameweek slots are unbounded input. A memo that grows with the
    traffic is a leak with better latency."""
    for gw in range(1, 40):
        identity.with_identity(_payload(), gw)
    assert len(identity._CACHE) <= identity._CACHE_MAX


def test_the_caller_cannot_mutate_the_cached_maps(wired):
    """``with_identity`` copies the fixture dict before adding difficulty
    (``identity.py:187``). If that copy is ever dropped, the second request
    inherits the first's difficulty — this is the rail that says so."""
    identity.with_identity(_payload(), 9)
    out = identity.with_identity(_payload(), 9)
    entry = out["xi"][0]
    if entry["next_fixture"] is not None:
        entry["next_fixture"]["opponent_short"] = "MUTATED"
    again = identity.with_identity(_payload(), 9)
    if again["xi"][0]["next_fixture"] is not None:
        assert again["xi"][0]["next_fixture"]["opponent_short"] != "MUTATED"


def test_clear_cache_is_available_to_tests_and_empties_it(wired):
    _tmp, reads = wired
    identity.with_identity(_payload(), 9)
    identity.clear_cache()
    reads.clear()
    identity.with_identity(_payload(), 9)
    assert set(reads) & IDENTITY_PATHS
