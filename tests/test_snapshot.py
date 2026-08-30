"""The daily availability log: what the news said, stamped with the day."""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.artifacts import AVAILABILITY_COLS
from gaffer.errors import GafferError
from gaffer.snapshot import (SNAPSHOT_COLS, SNAPSHOT_PATH, append_snapshot,
                             load_snapshot_log, next_unfinished_gw,
                             run_snapshot, snap_date, snapshot_rows)


def _avail() -> pd.DataFrame:
    """A news-sharpened availability frame, in availability_frame's shape."""
    return pd.DataFrame({
        "code": [1, 2],
        "status": ["d", "a"],
        "chance_of_playing": [50.0, None],
        "injury_type": ["hamstring", None],
        "expected_return_gw": [4.0, None],
        "p_start_hint": [0.4, None],
        "source": ["ffs", None],
        "fetched_at": ["2026-08-30T09:00:00+00:00", None]})


def _events() -> pd.DataFrame:
    return pd.DataFrame({"gw": [1, 2, 3], "finished": [True, False, False]})


def test_the_log_columns_are_the_availability_columns_stamped():
    """The log reuses artifacts' column contract rather than restating it, so
    a column added to the availability frame lands here for free."""
    assert SNAPSHOT_COLS == ["season", "gw", "snap_date"] + AVAILABILITY_COLS


def test_the_snapshot_gameweek_is_the_first_unfinished_one():
    """``is_next`` goes false in the hours a gameweek is being played, and a
    snapshot taken then still belongs to that week's news cycle."""
    assert next_unfinished_gw(_events()) == 2


def test_a_finished_season_has_no_gameweek_to_snapshot():
    with pytest.raises(GafferError):
        next_unfinished_gw(pd.DataFrame({"gw": [1], "finished": [True]}))


def test_the_rows_carry_the_season_the_gameweek_and_the_day():
    rows = snapshot_rows(_avail(), gw=2, season="2026-27", day="2026-08-30")
    assert list(rows.columns) == SNAPSHOT_COLS
    assert set(rows["season"]) == {"2026-27"}
    assert set(rows["gw"]) == {2}
    assert set(rows["snap_date"]) == {"2026-08-30"}
    assert sorted(rows["code"]) == [1, 2]
    assert rows.set_index("code").loc[1, "injury_type"] == "hamstring"


def test_a_flags_only_frame_still_writes_the_full_schema():
    """News off, or every source down: the log keeps one shape all season, so
    the corrector reads one table rather than a union of weekly shapes."""
    flags = pd.DataFrame({"code": [1], "status": ["a"],
                          "chance_of_playing": [None]})
    rows = snapshot_rows(flags, gw=2, season="2026-27", day="2026-08-30")
    assert list(rows.columns) == SNAPSHOT_COLS
    assert rows["source"].isna().all()
    assert rows["p_start_hint"].isna().all()


def test_the_day_is_utc_and_dashed():
    day = snap_date()
    assert len(day) == 10 and day[4] == "-" and day[7] == "-"


def test_an_absent_log_reads_as_an_empty_frame(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    out = load_snapshot_log()
    assert out.empty
    assert list(out.columns) == SNAPSHOT_COLS


def test_the_first_write_creates_the_log(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    rows = snapshot_rows(_avail(), gw=2, season="2026-27", day="2026-08-30")
    assert append_snapshot(rows) == 2
    assert (tmp_path / SNAPSHOT_PATH).exists()
    assert len(load_snapshot_log()) == 2


def test_a_second_run_the_same_day_replaces_that_days_rows(tmp_path,
                                                           monkeypatch):
    """The job can be re-run by hand, and a duplicated afternoon would weight
    that day twice in whatever trains on this log. The later run wins: it is
    the news that stood at the end of the day."""
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    append_snapshot(snapshot_rows(_avail(), gw=2, season="2026-27",
                                  day="2026-08-30"))
    later = _avail()
    later.loc[0, "status"] = "i"
    append_snapshot(snapshot_rows(later, gw=2, season="2026-27",
                                  day="2026-08-30"))
    out = load_snapshot_log()
    assert len(out) == 2
    assert set(out["snap_date"]) == {"2026-08-30"}
    assert out.set_index("code").loc[1, "status"] == "i"


def test_a_later_day_appends_rather_than_replaces(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    append_snapshot(snapshot_rows(_avail(), gw=2, season="2026-27",
                                  day="2026-08-30"))
    append_snapshot(snapshot_rows(_avail(), gw=2, season="2026-27",
                                  day="2026-08-31"))
    out = load_snapshot_log()
    assert len(out) == 4
    assert sorted(set(out["snap_date"])) == ["2026-08-30", "2026-08-31"]


def test_a_normal_append_leaves_no_temp_file_behind(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    append_snapshot(snapshot_rows(_avail(), gw=2, season="2026-27",
                                  day="2026-08-30"))
    assert not list((tmp_path / "live").glob("*.tmp"))


def test_a_write_that_dies_leaves_the_banked_log_untouched(tmp_path,
                                                           monkeypatch):
    """Append-by-rewrite means every day's write puts the whole log at risk.
    A launchd job killed mid-write must not cost the season's history."""
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    append_snapshot(snapshot_rows(_avail(), gw=2, season="2026-27",
                                  day="2026-08-30"))
    real_save = store_mod.save

    def half_written(df, rel):
        real_save(df.head(0), rel)
        raise OSError("the disk filled up")

    monkeypatch.setattr(store_mod, "save", half_written)
    with pytest.raises(OSError):
        append_snapshot(snapshot_rows(_avail(), gw=2, season="2026-27",
                                      day="2026-08-31"))
    monkeypatch.setattr(store_mod, "save", real_save)
    out = load_snapshot_log()
    assert len(out) == 2
    assert set(out["snap_date"]) == {"2026-08-30"}
    assert not list((tmp_path / "live").glob("*.tmp"))


def _cfg():
    from gaffer.config import Config

    return Config(entry_id=1, league_id=2, current_season="2026-27")


def _wire(monkeypatch, tmp_path, avail=None, boom=False):
    """Point the run at fakes: no network, no bootstrap, no news fetchers."""
    from gaffer.data import store as store_mod

    class _Client:
        def get_bootstrap(self):
            if boom:
                raise RuntimeError("the FPL API is down")
            return {"events": []}

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr("gaffer.api.client.FPLClient", lambda *a, **k: _Client())
    monkeypatch.setattr("gaffer.data.bootstrap.build_players",
                        lambda raw: pd.DataFrame())
    monkeypatch.setattr("gaffer.data.bootstrap.build_teams",
                        lambda raw: pd.DataFrame())
    monkeypatch.setattr("gaffer.data.bootstrap.build_events",
                        lambda raw: _events())
    monkeypatch.setattr("gaffer.advise.news_availability",
                        lambda *a, **kw: _avail() if avail is None else avail)
    monkeypatch.setattr("gaffer.snapshot.snap_date", lambda *a: "2026-08-30")


def test_a_run_banks_todays_rows_and_says_so(tmp_path, monkeypatch, capsys):
    _wire(monkeypatch, tmp_path)
    assert run_snapshot(cfg=_cfg()) == 2
    assert "Snapshot: 2 availability rows for gw2 at 2026-08-30." \
        in capsys.readouterr().out
    out = load_snapshot_log()
    assert list(out.columns) == SNAPSHOT_COLS
    assert set(out["season"]) == {"2026-27"}


def test_two_runs_in_one_day_leave_one_days_rows(tmp_path, monkeypatch):
    """Gate G1(b): the daily job is safe to trigger by hand."""
    _wire(monkeypatch, tmp_path)
    run_snapshot(cfg=_cfg())
    run_snapshot(cfg=_cfg())
    assert len(load_snapshot_log()) == 2


def test_a_dead_fetch_prints_one_line_and_banks_nothing(tmp_path, monkeypatch,
                                                        capsys):
    """Gate G1(c). A launchd job has nowhere to report a traceback, and a
    scheduled job that dies loudly every afternoon gets uninstalled."""
    _wire(monkeypatch, tmp_path, boom=True)
    assert run_snapshot(cfg=_cfg()) is None
    printed = capsys.readouterr().out.strip().splitlines()
    assert len(printed) == 1
    assert printed[0].startswith("availability snapshot not written:")
    assert not (tmp_path / SNAPSHOT_PATH).exists()


def test_an_empty_availability_frame_banks_nothing(tmp_path, monkeypatch):
    _wire(monkeypatch, tmp_path, avail=pd.DataFrame())
    assert run_snapshot(cfg=_cfg()) is None
    assert not (tmp_path / SNAPSHOT_PATH).exists()


def test_the_snapshot_plist_runs_the_command_daily_at_five(tmp_path):
    """F1 is a scheduling change as much as a code one: a log nobody writes
    to banks nothing, and the whole value is one row per day."""
    import plistlib
    from pathlib import Path

    raw = Path("scripts/com.gaffer.snapshot.plist").read_text(encoding="utf-8")
    assert "__PROJECT_DIR__" in raw
    plist = plistlib.loads(
        raw.replace("__PROJECT_DIR__", str(tmp_path)).encode("utf-8"))
    assert plist["Label"] == "com.gaffer.snapshot"
    assert plist["StartCalendarInterval"] == {"Hour": 17, "Minute": 0}
    command = plist["ProgramArguments"][-1]
    assert "uv run gaffer snapshot" in command
    assert "logs/snapshot.log" in command
    assert str(tmp_path) in command


def test_the_installer_installs_the_snapshot_job():
    from pathlib import Path

    body = Path("scripts/install_automation.sh").read_text(encoding="utf-8")
    names = body.split("for name in")[1].split(";")[0]
    assert "snapshot" in names
