"""``gaffer field-scrape``: what it fetches, what it refuses to fetch twice,
and the one thing it must never do — raise."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pandas as pd
import pytest

from gaffer.config import Config
from gaffer.data import store
from gaffer.data.field import (field_sample_path, load_field_eo,
                               load_field_sample, run_field_scrape, scrape_gw)
from gaffer.data.tier_eo import tier_cache_path, write_tier_cache

EVENTS = pd.DataFrame([
    {"gw": 1, "deadline_time": "2026-08-14T17:30:00Z", "is_current": False,
     "is_next": False, "finished": True, "data_checked": True},
    {"gw": 2, "deadline_time": "2026-08-21T17:30:00Z", "is_current": True,
     "is_next": False, "finished": True, "data_checked": False},
    {"gw": 3, "deadline_time": "2026-09-11T17:30:00Z", "is_current": False,
     "is_next": True, "finished": False, "data_checked": False},
])

PICKS = [[{"element": 7, "position": 1, "multiplier": 2},
          {"element": 8, "position": 2, "multiplier": 1}],
         [{"element": 7, "position": 1, "multiplier": 1},
          {"element": 9, "position": 2, "multiplier": 1}]]

CFG = Config(entry_id=1, league_id=5, current_season="2026-27")


@pytest.fixture()
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr("gaffer.data.field.RAW_FIELD",
                        tmp_path / "data/raw/field")
    monkeypatch.setattr("gaffer.data.field.RAW_TIER",
                        tmp_path / "data/raw/tier_eo")
    return tmp_path


@pytest.fixture()
def wired(here, monkeypatch):
    """Bootstrap, events and the shared fetch, all faked. Counts fetches."""
    calls = {"fetch": 0}

    def _fetch(client, gw, sample=300, seed=0):
        calls["fetch"] += 1
        calls["gw"] = int(gw)
        calls["sample"] = int(sample)
        return PICKS

    monkeypatch.setattr(
        "gaffer.api.client.FPLClient",
        lambda *a, **kw: SimpleNamespace(get_bootstrap=lambda: {}))
    monkeypatch.setattr("gaffer.data.bootstrap.build_events",
                        lambda raw: EVENTS)
    monkeypatch.setattr("gaffer.data.field.fetch_sample_picks", _fetch)
    return calls


def test_the_target_is_the_last_gameweek_whose_deadline_has_passed():
    assert scrape_gw(EVENTS, now="2026-08-25T12:30:00Z") == 2
    assert scrape_gw(EVENTS, now="2026-09-12T12:30:00Z") == 3


def test_before_any_deadline_there_is_nothing_to_scrape():
    assert scrape_gw(EVENTS, now="2026-08-01T12:30:00Z") is None


def test_an_events_frame_with_no_deadlines_is_none():
    assert scrape_gw(pd.DataFrame(columns=["gw", "deadline_time"]),
                     now="2026-09-12T12:30:00Z") is None


def test_a_scrape_banks_the_squads_and_the_eo_rows(here, wired):
    rows = run_field_scrape(CFG, gw=2)
    assert rows == 3          # elements 7, 8, 9
    assert load_field_sample("2026-27", 2) == PICKS
    log = load_field_eo()
    assert set(log["element"]) == {7, 8, 9}
    assert set(log["gw"]) == {2}


def test_the_scrape_populates_the_tier_cache_the_tracker_reads(here, wired):
    """One fetch serves both readers: after a scrape the live tracker finds
    the gameweek already cached and fires nothing."""
    run_field_scrape(CFG, gw=2)
    raw = json.loads(tier_cache_path(2, here / "data/raw/tier_eo").read_text())
    assert raw["7"]["eo"] == 150.0


def test_a_second_run_of_the_same_gameweek_fetches_nothing(here, wired,
                                                           capsys):
    run_field_scrape(CFG, gw=2)
    capsys.readouterr()
    assert run_field_scrape(CFG, gw=2) == 0
    assert wired["fetch"] == 1
    assert "already banked" in capsys.readouterr().out


def test_force_re_runs_a_banked_gameweek_and_replaces_the_bank(here, wired,
                                                               monkeypatch,
                                                               capsys):
    """The flag used to be half a flag: it re-fetched, paid the ~455
    requests, and then handed the fresh draw to a save that kept the old file
    — while printing a line about how many entries had been scraped."""
    run_field_scrape(CFG, gw=2)
    assert load_field_sample("2026-27", 2) == PICKS
    fresh = [[{"element": 21, "position": 1, "multiplier": 2}]]

    def _fresh(*a, **kw):
        wired["fetch"] += 1
        return fresh

    monkeypatch.setattr("gaffer.data.field.fetch_sample_picks", _fresh)
    capsys.readouterr()
    run_field_scrape(CFG, gw=2, force=True)
    assert wired["fetch"] == 2
    assert load_field_sample("2026-27", 2) == fresh
    assert "re-banked" in capsys.readouterr().out


def test_a_fresh_tier_cache_is_reused_rather_than_re_fetched(here, wired,
                                                             capsys):
    """D7. The live tracker paid for this gameweek's 455 requests minutes
    ago; the scrape logs its EO and fires nothing at the same endpoint in the
    same hour. No squads are banked, so the next run still has work to do."""
    write_tier_cache({7: {"eo": 12.0, "se": 1.0, "n": 300}}, 2,
                     here / "data/raw/tier_eo")
    rows = run_field_scrape(CFG, gw=2)
    assert wired["fetch"] == 0
    assert rows == 1
    assert load_field_sample("2026-27", 2) is None
    assert "reused" in capsys.readouterr().out


def test_a_stale_tier_cache_does_not_block_the_scrape(here, wired):
    path = tier_cache_path(2, here / "data/raw/tier_eo")
    write_tier_cache({7: {"eo": 12.0, "se": 1.0, "n": 300}}, 2,
                     here / "data/raw/tier_eo")
    old = time.time() - 7200
    import os
    os.utime(path, (old, old))
    assert run_field_scrape(CFG, gw=2) == 3
    assert wired["fetch"] == 1


def test_the_switch_off_fetches_nothing_at_all(here, wired, capsys):
    off = Config(entry_id=1, league_id=5, current_season="2026-27",
                 field_scrape=False)
    assert run_field_scrape(off, gw=2) is None
    assert wired["fetch"] == 0
    assert "field_scrape is off" in capsys.readouterr().out


def test_the_sample_size_comes_from_the_config(here, wired):
    run_field_scrape(Config(entry_id=1, league_id=5,
                            current_season="2026-27", field_sample=120), gw=2)
    assert wired["sample"] == 120


def test_a_gameweek_where_nobody_is_readable_writes_nothing(here, wired,
                                                            monkeypatch,
                                                            capsys):
    monkeypatch.setattr("gaffer.data.field.fetch_sample_picks",
                        lambda *a, **kw: [])
    assert run_field_scrape(CFG, gw=2) is None
    assert load_field_sample("2026-27", 2) is None
    assert "no sampled entry" in capsys.readouterr().out


def test_a_dead_api_prints_one_line_and_never_raises(here, monkeypatch,
                                                     capsys):
    def _boom(*a, **kw):
        raise RuntimeError("FPL is down")

    monkeypatch.setattr("gaffer.api.client.FPLClient", _boom)
    assert run_field_scrape(CFG) is None
    out = capsys.readouterr().out
    assert "field scrape not written" in out
    assert "FPL is down" in out


def test_no_gameweek_yet_is_a_printed_line_not_a_failure(here, wired, capsys):
    monkeypatch_now = "2026-08-01T12:30:00Z"
    assert run_field_scrape(CFG, now=monkeypatch_now) is None
    assert "no gameweek deadline" in capsys.readouterr().out


def test_an_already_banked_gameweek_costs_no_requests_at_all(here, wired,
                                                             monkeypatch,
                                                             capsys):
    """The Sunday run, every week the Saturday run worked. It used to build
    a client and fetch the bootstrap purely to learn a gameweek number that
    the events snapshot on disk already knows."""
    from gaffer.data import store

    run_field_scrape(CFG, gw=2)
    store.save(EVENTS, "live/events.parquet")

    def _no_network(*a, **kw):
        raise AssertionError("the banked path must not touch the API")

    monkeypatch.setattr("gaffer.api.client.FPLClient", _no_network)
    monkeypatch.setattr("gaffer.data.bootstrap.build_events", _no_network)
    capsys.readouterr()
    assert run_field_scrape(CFG, now="2026-08-25T12:30:00Z") == 0
    assert "already banked" in capsys.readouterr().out


def test_with_no_events_snapshot_the_bootstrap_is_still_the_fallback(here,
                                                                    wired):
    """No snapshot is not an error: the one request is paid, and the docstring
    says so."""
    assert run_field_scrape(CFG, now="2026-08-25T12:30:00Z") == 3
    assert wired["gw"] == 2


def test_an_absurd_field_sample_is_clamped_rather_than_honoured(here, wired):
    """``[league] field_sample = 100000`` is a typo, not an instruction: it
    would be a hundred thousand requests at a public API in one burst."""
    from gaffer.data.field import MAX_FIELD_SAMPLE

    run_field_scrape(Config(entry_id=1, league_id=5, current_season="2026-27",
                            field_sample=100_000), gw=2)
    assert wired["sample"] == MAX_FIELD_SAMPLE
