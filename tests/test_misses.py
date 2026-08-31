"""The week's biggest forecast errors, joined off two banked artifacts.

The interesting question is not the arithmetic, it is *which gameweek*: the
newest components file is normally next week's and has no results at all,
while the newest results may predate the oldest components file on a clone
that has just been set up. So the subject under test is mostly the
intersection, and the empty intersection.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.artifacts import save_components
from gaffer.misses import MISS_ROWS, biggest_misses, scoreable_gw


def _components(gw: int, rows) -> pd.DataFrame:
    return pd.DataFrame([
        {"code": code, "element": code, "name": name, "position": pos,
         "team_code": 3, "team_name": "Arsenal", "gw": gw, "opp_code": 4,
         "opp_name": "City", "was_home": 1.0, "kickoff_time": None,
         "p_play": 0.9, "p60": 0.8, "ep": ep}
        for code, name, pos, ep in rows])


RESULTS = pd.DataFrame([
    {"code": 11, "gw": 5, "total_points": 16, "minutes": 90},
    {"code": 22, "gw": 5, "total_points": 1, "minutes": 12},
    {"code": 33, "gw": 5, "total_points": 6, "minutes": 90},
])

PLAYERS = pd.DataFrame({
    "code": [11, 22, 33], "element": [11, 22, 33],
    "name": ["Saka", "Sub", "Gabriel"], "position": ["MID", "FWD", "DEF"],
    "now_cost": [100, 60, 55]})


@pytest.fixture()
def banked(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    RESULTS.to_parquet(tmp_path / "data/live/player_gw.parquet", index=False)
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    save_components(_components(5, [(11, "Saka", "MID", 5.5),
                                    (22, "Sub", "FWD", 2.0),
                                    (33, "Gabriel", "DEF", 4.0)]), 5)
    # Next week's file, written by the most recent advise run: newer, and
    # with nothing played in it.
    save_components(_components(6, [(11, "Saka", "MID", 6.0)]), 6)
    return tmp_path


def test_the_scoreable_gameweek_is_the_newest_one_with_both(banked):
    """A7: not the newest components file, which is next week's."""
    assert scoreable_gw() == 5


def test_no_results_at_all_is_no_scoreable_gameweek(banked):
    (banked / "data/live/player_gw.parquet").unlink()
    assert scoreable_gw() is None


def test_no_components_at_all_is_no_scoreable_gameweek(banked):
    for gw in (5, 6):
        (banked / f"reports/components_gw{gw}.parquet").unlink()
    assert scoreable_gw() is None


def test_the_misses_are_sorted_by_absolute_error(banked):
    rows = biggest_misses(5)
    assert [r["code"] for r in rows] == [11, 33, 22]
    assert rows[0]["miss"] == pytest.approx(10.5)   # 16 actual, 5.5 forecast
    assert rows[2]["miss"] == pytest.approx(-1.0)


def test_every_row_carries_its_context(banked):
    row = biggest_misses(5)[0]
    assert row["name"] == "Saka" and row["position"] == "MID"
    assert row["price"] == pytest.approx(10.0)
    assert row["actual"] == 16 and row["ep"] == pytest.approx(5.5)
    assert row["minutes"] == 90


def test_a_double_gameweek_is_one_row(banked):
    """Two fixtures, one forecast for the week and one points total."""
    save_components(pd.concat([
        _components(5, [(11, "Saka", "MID", 3.0)]),
        _components(5, [(11, "Saka", "MID", 2.5)])], ignore_index=True), 5)
    rows = [r for r in biggest_misses(5) if r["code"] == 11]
    assert len(rows) == 1 and rows[0]["ep"] == pytest.approx(5.5)


def test_a_player_with_no_result_row_is_left_out_not_zeroed(banked):
    """An inner join, on purpose: a player the results frame does not cover
    has not scored nought, he is unknown."""
    save_components(_components(5, [(11, "Saka", "MID", 5.5),
                                    (99, "Ghost", "MID", 7.0)]), 5)
    assert 99 not in {r["code"] for r in biggest_misses(5)}


def test_the_list_is_capped(banked):
    save_components(_components(5, [(c, f"P{c}", "MID", 1.0)
                                    for c in range(1, 40)]), 5)
    results = pd.DataFrame([{"code": c, "gw": 5, "total_points": c,
                             "minutes": 90} for c in range(1, 40)])
    results.to_parquet(banked / "data/live/player_gw.parquet", index=False)
    assert len(biggest_misses(5)) == MISS_ROWS


def test_a_missing_player_snapshot_still_lists_the_misses(banked):
    """Names and prices are context, not the finding."""
    (banked / "data/live/players.parquet").unlink()
    rows = biggest_misses(5)
    assert rows[0]["code"] == 11
    assert rows[0]["name"] == "11" and rows[0]["price"] is None


def test_an_unscoreable_gameweek_is_an_empty_list(banked):
    assert biggest_misses(6) == []
    assert biggest_misses(99) == []
