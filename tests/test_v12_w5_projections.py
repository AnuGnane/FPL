"""v12 W5 §6.4 — the EP table advise acted on, frozen and dated.

The table is already persisted at reports/solve_state_gw{N}.parquet, but that
is one slot per gameweek and advise runs several times a week — Tuesday,
Thursday, after Friday's pressers, sometimes after kickoff. What Review reads
on Tuesday is therefore the *last* run, which may be the post-deadline one.

The advice payload has not had this problem since v9c: ADVICE_HISTORY keeps 20
runs and journal.latest_run_per_gw picks the newest one written before the
deadline. This gives the EP table the same treatment and, deliberately, the
same rule.
"""
from __future__ import annotations

import pandas as pd
import pytest

from gaffer.artifacts import (POOL_COLS, SolveState, latest_projection_before,
                              projection_snapshots, save_solve_state)


def _pool(codes=(100, 200), gws=(5, 6)) -> pd.DataFrame:
    rows = [{"code": c, "name": f"P{c}", "position": "MID", "team_code": 1,
             "cost": 80, "sell": 80, "owned": c == 100, "gw": g,
             "ep_raw": 4.0 + c / 100} for c in codes for g in gws]
    return pd.DataFrame(rows, columns=POOL_COLS)


def _state(gw=5, at="2026-09-01T09:00:00+00:00", pool=None) -> SolveState:
    return SolveState(
        gw=gw, gws=[5, 6], deadline="2026-09-04T17:30:00+00:00",
        generated_at=at, mode="weekly", bank=15, free_transfers=1,
        owned_codes=[100], lam=0.0, league_eo={}, avail_by_gw={},
        opt={"decay": 0.85, "hit_cost": 4},
        pool=_pool() if pool is None else pool)


@pytest.fixture(autouse=True)
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("gaffer.config.serving_config",
                        lambda: type("C", (), {"current_season": "2026-27"})())
    return tmp_path


def test_saving_a_solve_state_also_freezes_the_pool(here):
    save_solve_state(_state())
    snaps = projection_snapshots("2026-27", 5)
    assert len(snaps) == 1
    frame = pd.read_parquet(snaps[0].path)
    assert list(frame.columns) == POOL_COLS
    assert len(frame) == 4


def test_two_runs_at_different_seconds_are_two_snapshots(here):
    """Two slots rather than one, which is the whole point of the directory.

    Named for what it actually proves. The stamp's resolution is one second,
    so two runs that *started inside the same second* would share a filename
    and the later would silently replace the earlier; this pins the case the
    versioning exists for, and ``ProjectionSnapshot.stamp`` records the
    collision it does not.
    """
    save_solve_state(_state(at="2026-09-01T09:00:00+00:00"))
    save_solve_state(_state(at="2026-09-03T18:00:00+00:00"))
    assert len(projection_snapshots("2026-27", 5)) == 2


def test_snapshots_come_back_oldest_first(here):
    save_solve_state(_state(at="2026-09-03T18:00:00+00:00"))
    save_solve_state(_state(at="2026-09-01T09:00:00+00:00"))
    stamps = [s.stamp for s in projection_snapshots("2026-27", 5)]
    assert stamps == sorted(stamps)


def test_another_season_is_not_this_seasons(here, monkeypatch):
    """Element ids remap every season and codes do not, but a directory
    selected by a glob is exactly the shape of that mistake."""
    save_solve_state(_state())
    monkeypatch.setattr("gaffer.config.serving_config",
                        lambda: type("C", (), {"current_season": "2027-28"})())
    save_solve_state(_state())
    assert len(projection_snapshots("2026-27", 5)) == 1
    assert len(projection_snapshots("2027-28", 5)) == 1


def test_another_gameweek_is_not_this_one(here):
    save_solve_state(_state(gw=5))
    save_solve_state(_state(gw=6))
    assert len(projection_snapshots("2026-27", 5)) == 1


def test_the_newest_run_before_the_deadline_wins(here):
    save_solve_state(_state(at="2026-09-01T09:00:00+00:00"))
    save_solve_state(_state(at="2026-09-04T09:00:00+00:00"))
    save_solve_state(_state(at="2026-09-05T09:00:00+00:00"))   # after
    chosen = latest_projection_before("2026-27", 5,
                                      "2026-09-04T17:30:00+00:00")
    assert chosen.stamp.startswith("20260904T09")
    assert chosen.post_deadline is False


def test_all_runs_late_gives_the_newest_and_flags_it(here):
    """journal.latest_run_per_gw's rule, verbatim: a flagged comparison is
    worth more than a missing row as long as it cannot pass itself off as
    foresight."""
    save_solve_state(_state(at="2026-09-05T09:00:00+00:00"))
    save_solve_state(_state(at="2026-09-06T09:00:00+00:00"))
    chosen = latest_projection_before("2026-27", 5,
                                      "2026-09-04T17:30:00+00:00")
    assert chosen.stamp.startswith("20260906T09")
    assert chosen.post_deadline is True


def test_a_snapshot_stamped_at_the_deadline_second_is_late(here):
    """The boundary is strict, and it is strict on purpose.

    journal.latest_run_per_gw's own rule is ``written < deadline`` — a run
    banked *at* the deadline second is not a run banked before it, because
    one second of resolution cannot tell 17:30:00.0 from 17:30:00.9 and the
    second of those has seen the lineups. With only that snapshot on disk the
    reader takes its late branch rather than counting it as in-time.
    """
    save_solve_state(_state(at="2026-09-04T17:30:00+00:00"))
    chosen = latest_projection_before("2026-27", 5,
                                      "2026-09-04T17:30:00+00:00")
    assert chosen.stamp == "20260904T173000Z"
    assert chosen.post_deadline is True


def test_a_snapshot_one_second_earlier_is_in_time(here):
    """The other side of the same boundary, so the ``<`` cannot quietly
    become a ``<=`` in one direction or an off-by-one in the other."""
    save_solve_state(_state(at="2026-09-04T17:29:59+00:00"))
    chosen = latest_projection_before("2026-27", 5,
                                      "2026-09-04T17:30:00+00:00")
    assert chosen.stamp == "20260904T172959Z"
    assert chosen.post_deadline is False


def test_no_snapshot_at_all_is_None_and_not_an_exception(here):
    assert latest_projection_before("2026-27", 5,
                                    "2026-09-04T17:30:00+00:00") is None


def test_an_unparseable_deadline_takes_the_newest_and_flags_it(here):
    save_solve_state(_state())
    chosen = latest_projection_before("2026-27", 5, "not a date")
    assert chosen is not None
    assert chosen.post_deadline is True


def test_the_solve_state_itself_is_written_exactly_as_before(here):
    """The snapshot is a second artifact, never a replacement. Every caller of
    load_solve_state must be untouched."""
    from gaffer.artifacts import load_solve_state

    save_solve_state(_state())
    back = load_solve_state(5)
    assert back.bank == 15 and back.free_transfers == 1
    assert len(back.pool) == 4
