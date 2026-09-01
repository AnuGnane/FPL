"""Where I stood overall, banked beside how I decided.

``grep -rn "overall_rank" src/ frontend/`` returned zero hits before this task:
the only ``rank`` in the tree is a mini-league standing position, which is a
different quantity about a different population. The number itself has been on
disk all along — ``my_decisions`` reads three fields out of the entry-history
row and this is a fourth.

The fact that has to travel with the field: **grades are banked, never
re-derived** (``review.py:24-26``, spec D2). So a row graded before this change
has no rank and will never acquire one, and the chart that draws the trajectory
must render a null as a gap — not a zero, and not a line interpolated through
it, which is the most confident lie the dashboard could tell.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from gaffer.data import store
from gaffer.data.my_entry import my_picks_path
from gaffer.review import my_decisions, season_summary

PLAYERS = pd.DataFrame([{"code": 100, "element": 7},
                        {"code": 101, "element": 8}])

MY_PICKS = [
    {"element": 7, "position": 1, "multiplier": 2, "is_captain": True,
     "is_vice_captain": False},
    {"element": 8, "position": 12, "multiplier": 0, "is_captain": False,
     "is_vice_captain": True},
]

ROW = {"event": 1, "points": 20, "total_points": 20, "event_transfers": 0,
       "event_transfers_cost": 0, "points_on_bench": 3,
       "overall_rank": 412_233, "rank": 90_112, "rank_sort": 90_112,
       "percentile_rank": 5, "value": 1002, "bank": 3}
"""The real key names, straight off ``<entry>-history.json``. The fixture is
the contract: ``rank`` beside ``overall_rank`` is exactly the pair this task
had to choose between."""


def _bank(tmp_path, monkeypatch, row):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr("gaffer.data.my_entry.RAW_LEAGUE",
                        tmp_path / "data/raw/league")
    store.save(PLAYERS, "live/players.parquet")
    path = my_picks_path("2026-27", 1, 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(MY_PICKS))
    (path.parent / "1-history.json").write_text(
        json.dumps({"current": [row], "chips": []}))
    return tmp_path


@pytest.fixture()
def banked_entry(tmp_path, monkeypatch):
    return _bank(tmp_path, monkeypatch, ROW)


@pytest.fixture()
def banked_entry_no_rank(tmp_path, monkeypatch):
    return _bank(tmp_path, monkeypatch,
                 {k: v for k, v in ROW.items() if k != "overall_rank"})


def test_my_decisions_carries_the_overall_rank(banked_entry):
    """``banked_entry`` writes a history JSON with the real key names FPL
    uses; the fixture is the contract."""
    mine = my_decisions(1, season="2026-27", entry_id=1)
    assert mine["overall_rank"] == 412_233


def test_a_history_row_without_the_key_is_None_not_zero(banked_entry_no_rank):
    mine = my_decisions(1, season="2026-27", entry_id=1)
    assert mine["overall_rank"] is None


def test_the_graded_row_carries_it_through(banked_entry):
    """``grade_gw_from`` reads it off ``mine`` the way it reads the bench
    points, so the number reaches the ledger rather than stopping at the
    reader."""
    from gaffer.review import grade_gw_from

    mine = my_decisions(1, season="2026-27", entry_id=1)
    actuals = pd.DataFrame([
        {"code": 100, "total_points": 9, "minutes": 90, "position": "MID"},
        {"code": 101, "total_points": 2, "minutes": 90, "position": "DEF"}])
    row = grade_gw_from(1, mine, None, actuals)
    assert row["overall_rank"] == 412_233


def test_a_row_banked_before_this_change_reads_as_unmeasured():
    """The consequence of "banked, never re-derived", asserted rather than
    assumed. An old row has no key at all, and ``.get`` must answer None
    rather than raising or defaulting to a rank of zero — which would be the
    best rank in the game."""
    old = {"gw": 1, "lanes": [], "points_on_bench": 2}
    assert old.get("overall_rank") is None


def test_the_summary_does_not_invent_a_rank_series():
    """This task adds a per-gameweek field and no season aggregate. A mean
    rank over a season is not a thing anyone wants and a *sum* of ranks is
    meaningless; the trajectory is drawn from ``gws[]`` directly."""
    out = season_summary([{"gw": 1, "lanes": [], "points_on_bench": 2}])
    assert "overall_rank" not in out
    assert "rank" not in out
