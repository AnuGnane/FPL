"""Every standing job on one page, with the clock it is meant to keep.

v19a §2.3. Before this the Health tab knew one thing about automation: when
``logs/advise.log`` last moved. The other eight launchd agents were invisible,
so an agent that stopped being loaded — which is the failure this install has
actually had — announced itself only as a number going quietly stale on some
other hub, days later.

Two decisions carry most of the tests below.

The age is the *redirect log's* mtime. Every one of these jobs appends a line
whatever it did, so the mtime is the run stamp, and it is a stamp launchd
cannot lie about the way a "last ran" field written by the job itself could.

And nothing here raises. ``/api/health`` is polled by an open tab, and the
plist directory is a directory a user edits by hand. A plist somebody is
halfway through changing has to be one row reading "unreadable", never a 500
on the page they opened to find out what was wrong.
"""

from __future__ import annotations

import os
import plistlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gaffer.web.app import create_app
from gaffer.web.routers import meta
from gaffer.web.routers.meta import job_health

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def _plist(directory: Path, name: str, calendar, *,
           command: str = "cd . && uv run gaffer thing >> logs/thing.log 2>&1"
           ) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"com.gaffer.{name}.plist"
    path.write_bytes(plistlib.dumps({
        "Label": f"com.gaffer.{name}",
        # The real plists carry a `__PROJECT_DIR__` placeholder inside this
        # string, which is why the parse is `plistlib` and not a template
        # engine: it is valid XML either way.
        "ProgramArguments": ["/bin/zsh", "-lc", command],
        "StartCalendarInterval": calendar,
    }))
    return path


def _age(root: Path, log: str, hours: float) -> None:
    """Write the redirect log and backdate it, which is the only input the
    overdue rule has."""
    path = root / log
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("ran\n")
    stamp = (NOW - timedelta(hours=hours)).timestamp()
    os.utime(path, (stamp, stamp))


@pytest.fixture()
def scripts(tmp_path):
    return tmp_path / "scripts"


# --- the schedule sentence and the interval ---------------------------

def test_a_weekly_job_reads_as_its_day_and_time(scripts):
    _plist(scripts, "advise", {"Weekday": 4, "Hour": 18, "Minute": 0})
    row = job_health(scripts, log_root=scripts.parent, now=NOW)[0]
    assert row.label == "advise"
    assert row.schedule == "Thu 18:00"
    assert row.interval_hours == 168


def test_a_daily_job_says_daily_rather_than_naming_every_day(scripts):
    _plist(scripts, "prices", {"Hour": 23, "Minute": 15})
    row = job_health(scripts, log_root=scripts.parent, now=NOW)[0]
    assert row.schedule == "daily 23:15"
    assert row.interval_hours == 24


def test_two_weekday_slots_are_one_week_split_between_them(scripts):
    """The field scrape's shape. Each slot fires once a *week*, so two of them
    is 84 hours apart and not 12 — and the days keep the plist's own order,
    because launchd numbers Sunday 0 and sorting would print "Sun, Sat"."""
    _plist(scripts, "field", [{"Weekday": 6, "Hour": 18, "Minute": 30},
                              {"Weekday": 0, "Hour": 18, "Minute": 30}])
    row = job_health(scripts, log_root=scripts.parent, now=NOW)[0]
    assert row.schedule == "Sat, Sun 18:30"
    assert row.interval_hours == 84


def test_two_daily_slots_are_one_day_split_between_them(scripts):
    """The core-insights shape: twice every day is twelve hours, and both
    times are named because "daily" alone would not let a reader check the
    page against a log line."""
    _plist(scripts, "core-insights", [{"Hour": 6, "Minute": 30},
                                      {"Hour": 18, "Minute": 30}])
    row = job_health(scripts, log_root=scripts.parent, now=NOW)[0]
    assert row.schedule == "daily 06:30 and 18:30"
    assert row.interval_hours == 12


def test_slots_on_different_days_at_different_times_name_both(scripts):
    """No plist looks like this today. The sentence still has to be readable
    when one does, rather than silently dropping half the schedule."""
    _plist(scripts, "odd", [{"Weekday": 2, "Hour": 9, "Minute": 0},
                            {"Weekday": 5, "Hour": 17, "Minute": 30}])
    row = job_health(scripts, log_root=scripts.parent, now=NOW)[0]
    assert row.schedule == "Tue 09:00, Fri 17:30"


# --- the log, and whether the job kept its clock ----------------------

def test_the_log_is_parsed_out_of_the_command_the_plist_runs(scripts):
    """These plists redirect in a shell line rather than setting
    ``StandardOutPath``, so the file this page stats lives inside a string."""
    _plist(scripts, "backup", {"Hour": 23, "Minute": 45},
           command="cd __PROJECT_DIR__ && uv run gaffer backup "
                   ">> logs/backup.log 2>&1")
    row = job_health(scripts, log_root=scripts.parent, now=NOW)[0]
    assert row.log == "logs/backup.log"


def test_a_daily_job_is_not_overdue_after_thirty_five_hours(scripts):
    """Half an interval of grace. A nightly bank that starts late and takes
    four minutes must not read as missed the following evening."""
    _plist(scripts, "prices", {"Hour": 23, "Minute": 15})
    _age(scripts.parent, "logs/thing.log", 35)
    row = job_health(scripts, log_root=scripts.parent, now=NOW)[0]
    assert row.age_hours == 35
    assert row.overdue is False


def test_a_daily_job_is_overdue_after_thirty_seven_hours(scripts):
    """The other side of the same boundary: a whole extra half-day late is no
    longer a slow start, it is a run that did not happen."""
    _plist(scripts, "prices", {"Hour": 23, "Minute": 15})
    _age(scripts.parent, "logs/thing.log", 37)
    row = job_health(scripts, log_root=scripts.parent, now=NOW)[0]
    assert row.age_hours == 37
    assert row.overdue is True


def test_a_job_that_has_never_written_its_log_is_overdue(scripts):
    """The state this feature exists for: an agent that was never loaded has
    no log at all, and "never" is the strongest possible overdue, not an
    unknown to be rendered as fine."""
    _plist(scripts, "snapshot", {"Hour": 17, "Minute": 0})
    row = job_health(scripts, log_root=scripts.parent, now=NOW)[0]
    assert row.modified_at is None
    assert row.age_hours is None
    assert row.overdue is True


def test_a_weekly_job_is_judged_against_its_own_week(scripts):
    """The whole point of serving the interval: 100 hours is a dead nightly
    job and a perfectly healthy Thursday one."""
    _plist(scripts, "advise", {"Weekday": 4, "Hour": 18, "Minute": 0})
    _age(scripts.parent, "logs/thing.log", 100)
    assert job_health(scripts, log_root=scripts.parent,
                      now=NOW)[0].overdue is False


# --- degrading rather than raising ------------------------------------

def test_an_unreadable_plist_is_a_row_and_never_an_exception(scripts):
    """This directory is edited by hand and this endpoint is polled by a tab.
    A plist saved halfway through is one row saying so."""
    scripts.mkdir(parents=True)
    (scripts / "com.gaffer.broken.plist").write_text("<plist><dict>")
    row = job_health(scripts, log_root=scripts.parent, now=NOW)[0]
    assert row.label == "broken"
    assert row.schedule == "unreadable"
    assert row.interval_hours == 0
    assert row.overdue is True


def test_a_missing_scripts_directory_is_no_jobs_and_no_error(tmp_path):
    assert job_health(tmp_path / "nowhere", log_root=tmp_path, now=NOW) == []


def test_the_rows_are_sorted_by_label(scripts):
    """A table whose order depends on a directory listing reorders itself
    between polls, which is the one thing a status table must not do."""
    _plist(scripts, "review", {"Weekday": 2, "Hour": 9, "Minute": 0})
    _plist(scripts, "advise", {"Weekday": 4, "Hour": 18, "Minute": 0})
    _plist(scripts, "prices", {"Hour": 23, "Minute": 15})
    labels = [r.label for r in job_health(scripts, log_root=scripts.parent,
                                          now=NOW)]
    assert labels == ["advise", "prices", "review"]


# --- the shipped plists, and the route --------------------------------

def test_a_comment_containing_a_double_dash_is_still_a_readable_plist(
        scripts):
    """``scripts/com.gaffer.core-insights.plist`` documents a ``--refresh``
    flag inside an XML comment. ``plutil -lint`` passes it and launchd loads
    it; expat, which ``plistlib`` uses, calls it not-well-formed. Without the
    retry, this page reports a job that runs twice a day as unreadable."""
    scripts.mkdir(parents=True)
    (scripts / "com.gaffer.core-insights.plist").write_bytes(
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<plist version="1.0"><dict>\n'
        b'  <key>Label</key><string>com.gaffer.core-insights</string>\n'
        b'  <!-- `gaffer core-insights --refresh N` forces the last N. -->\n'
        b'  <key>StartCalendarInterval</key>\n'
        b'  <dict><key>Hour</key><integer>6</integer>'
        b'<key>Minute</key><integer>30</integer></dict>\n'
        b'</dict></plist>\n')
    row = job_health(scripts, log_root=scripts.parent, now=NOW)[0]
    assert row.label == "core-insights"
    assert row.schedule == "daily 06:30"


def test_every_shipped_plist_parses_into_a_row_with_a_schedule():
    """The real ``scripts/`` directory, placeholder and all: a new plist that
    this reader cannot make sense of should fail here and not on the page."""
    rows = job_health(Path("scripts"), now=NOW)
    assert len(rows) >= 9
    assert all(row.schedule != "unreadable" for row in rows)
    assert all(row.interval_hours > 0 for row in rows)
    assert all(row.log.startswith("logs/") for row in rows)


def test_the_health_route_carries_the_jobs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(meta, "PLIST_DIR", tmp_path / "scripts")
    _plist(tmp_path / "scripts", "prices", {"Hour": 23, "Minute": 15})
    response = TestClient(create_app()).get("/api/health")
    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert [j["label"] for j in jobs] == ["prices"]
    assert jobs[0]["schedule"] == "daily 23:15"
    # The advise log line stays beside them: it is the one job whose output a
    # reader wants quoted rather than only dated (v19a §2.3).
    assert "launchd" in response.json()
