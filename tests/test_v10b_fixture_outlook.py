"""Doubles and blanks, counted over the season's own fixture list.

There is no fixture-count helper anywhere in this tree and there never has
been: the matrix router appends one cell per fixture (``routers/fixtures.py:
134-146``) and the ticker prices one row per fixture (``meta.py:240-245``), so
a team playing twice in a gameweek silently becomes two cells and two rows and
nothing anywhere counts it. That is what this module is for.

Two definitions carry the weight, and both are about what *absence* means
(plan A8):

* a gameweek not present in the frame is **not** a league-wide blank. It is a
  gameweek nobody has published. Only gameweeks with rows are considered.
* the season's team set is the union of every team appearing anywhere in the
  frame, never a hardcoded twenty — a pre-season file and a February file have
  different unions and a constant would be right in one of them.
"""

from __future__ import annotations

import pandas as pd

from gaffer.data.fixtures import fixtures_per_team_per_gw, season_outlook


def _fixtures() -> pd.DataFrame:
    """Four teams. GW1 is normal, GW2 doubles team 1 and blanks team 4."""
    return pd.DataFrame([
        {"gw": 1, "home_id": 1, "away_id": 2},
        {"gw": 1, "home_id": 3, "away_id": 4},
        {"gw": 2, "home_id": 1, "away_id": 3},
        {"gw": 2, "home_id": 2, "away_id": 1},
    ])


def test_a_normal_gameweek_gives_every_team_one_fixture():
    counts = fixtures_per_team_per_gw(_fixtures())
    assert counts[1] == {1: 1, 2: 1, 3: 1, 4: 1}


def test_a_double_is_counted_twice_not_flattened():
    assert fixtures_per_team_per_gw(_fixtures())[2][1] == 2


def test_a_team_with_no_fixture_that_week_is_zero_not_missing():
    """The blank, in the counts. A missing key would make every consumer write
    ``.get(team, ?)`` and pick its own answer for what the ``?`` is."""
    assert fixtures_per_team_per_gw(_fixtures())[2][4] == 0


def test_codes_are_used_when_a_map_is_supplied():
    """``fixtures_all`` speaks team *ids*; everything else in the UI speaks
    codes, and the join is the caller's (``routers/fixtures.py:97-99``)."""
    counts = fixtures_per_team_per_gw(_fixtures(), {1: 14, 2: 43, 3: 3, 4: 8})
    assert counts[2][14] == 2 and counts[2][8] == 0


def test_an_id_the_map_does_not_know_is_dropped_rather_than_passed_through():
    """Half-mapped output — some codes, some raw ids in the same dict — is the
    quiet way a team gets counted twice under two names."""
    counts = fixtures_per_team_per_gw(_fixtures(), {1: 14, 2: 43})
    assert set(counts[1]) == {14, 43}


def test_the_outlook_names_the_doubles_and_the_blanks():
    out = season_outlook(_fixtures())
    week = next(w for w in out if w["gw"] == 2)
    assert week["doubles"] == [1] and week["blanks"] == [4]


def test_a_gameweek_with_nothing_scheduled_is_absent_not_a_league_wide_blank():
    """Plan A8. The naive definition makes every team blank in every gameweek
    the file does not describe, which on a partial download is all of them."""
    out = season_outlook(_fixtures())
    assert {w["gw"] for w in out} == {1, 2}


def test_from_gw_slices_the_remaining_season():
    assert {w["gw"] for w in season_outlook(_fixtures(), from_gw=2)} == {2}


def test_an_empty_frame_is_an_empty_outlook_not_an_error():
    assert season_outlook(pd.DataFrame(columns=["gw", "home_id", "away_id"])) \
        == []


def test_todays_real_fixture_list_has_no_doubles_and_no_blanks():
    """The reality this cycle ships into, asserted so the empty state is
    written against a fact rather than a guess: 380 rows, 38 gameweeks, ten
    fixtures in each, twenty teams appearing once. Skipped where the file is
    absent, because a clone has no data directory."""
    import pytest

    from gaffer.data import store
    if not store.exists("live/fixtures_all.parquet"):
        pytest.skip("no fixture list on this clone")
    out = season_outlook(store.load("live/fixtures_all.parquet"))
    assert all(not w["doubles"] and not w["blanks"] for w in out)
