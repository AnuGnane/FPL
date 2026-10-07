"""install_automation.sh --status and its next-fire helper (holiday F-5).

The flag is read-only by contract: it asks launchctl ``list`` and nothing
else. The shell test stubs launchctl on PATH and fails if any other verb
reaches it, so a later edit that loads a job from the status path is caught.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

SCRIPT = Path("scripts/automation_status.py")
INSTALLER = Path("scripts/install_automation.sh")


def _load():
    spec = importlib.util.spec_from_file_location("automation_status", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


status = _load()

# A Wednesday, so Thursday's advise run is tomorrow and Tuesday's is six days off.
WED_NOON = datetime(2026, 10, 7, 12, 0)


def test_a_weekly_job_fires_on_its_next_weekday():
    entry = {"Weekday": 4, "Hour": 18, "Minute": 0}
    assert status.next_calendar_fire([entry], WED_NOON) == datetime(2026, 10, 8, 18, 0)


def test_a_daily_job_still_due_today_fires_today():
    entry = {"Hour": 17, "Minute": 0}
    assert status.next_calendar_fire([entry], WED_NOON) == datetime(2026, 10, 7, 17, 0)


def test_a_daily_job_already_past_today_fires_tomorrow():
    entry = {"Hour": 6, "Minute": 30}
    assert status.next_calendar_fire([entry], WED_NOON) == datetime(2026, 10, 8, 6, 30)


def test_the_minute_it_fires_is_not_its_next_fire():
    entry = {"Hour": 12, "Minute": 0}
    assert status.next_calendar_fire([entry], WED_NOON) == datetime(2026, 10, 8, 12, 0)


def test_an_array_of_slots_takes_the_earliest():
    entries = [{"Weekday": 6, "Hour": 18, "Minute": 30},
               {"Weekday": 0, "Hour": 18, "Minute": 30}]
    assert status.next_calendar_fire(entries, WED_NOON) == datetime(2026, 10, 10, 18, 30)


def test_weekday_seven_is_sunday_as_launchd_reads_it():
    assert (status.next_calendar_fire([{"Weekday": 7, "Hour": 9, "Minute": 0}], WED_NOON)
            == status.next_calendar_fire([{"Weekday": 0, "Hour": 9, "Minute": 0}], WED_NOON)
            == datetime(2026, 10, 11, 9, 0))


def test_a_left_out_minute_is_a_wildcard():
    entry = {"Hour": 12}
    assert status.next_calendar_fire([entry], WED_NOON) == datetime(2026, 10, 7, 12, 1)


def test_an_impossible_date_is_never():
    assert status.next_calendar_fire([{"Month": 2, "Day": 30}], WED_NOON) is None
    assert status.describe({"StartCalendarInterval": {"Month": 2, "Day": 30}},
                           WED_NOON) == "never"


def test_every_shipped_plist_has_a_next_fire_within_a_week():
    """The nine shipped plists are all weekly or daily: a None here means the
    helper misread one, and the status table would print "never" for a job
    that does run."""
    for path in sorted(Path("scripts").glob("com.gaffer.*.plist")):
        plist = status.load_plist(path)
        calendar = plist["StartCalendarInterval"]
        entries = calendar if isinstance(calendar, list) else [calendar]
        nxt = status.next_calendar_fire(entries, WED_NOON)
        assert nxt is not None, path.name
        assert (nxt - WED_NOON).days < 7, path.name


def test_non_calendar_schedules_are_named():
    assert status.describe({"StartInterval": 300}, WED_NOON) == "every 300s"
    assert status.describe({"RunAtLoad": True}, WED_NOON) == "at load only"
    assert status.describe({}, WED_NOON) == "no schedule"


@pytest.mark.skipif(shutil.which("zsh") is None, reason="the installer is a zsh script")
def test_the_status_flag_only_lists_and_reports_each_job(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    stub = bin_dir / "launchctl"
    # `advise` reads as loaded; every other label as not loaded. Any verb but
    # `list` exits 99 and is recorded, so the assertion below catches it.
    stub.write_text(
        "#!/bin/sh\n"
        f'echo "$*" >> "{calls}"\n'
        '[ "$1" = list ] || exit 99\n'
        '[ "$2" = com.gaffer.advise ]\n'
    )
    stub.chmod(0o755)
    home = tmp_path / "home"
    (home / "Library" / "LaunchAgents").mkdir(parents=True)
    (home / "Library" / "LaunchAgents" / "com.gaffer.prices.plist").write_text("")
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "HOME": str(home)}
    out = subprocess.run(["zsh", str(INSTALLER), "--status"], env=env,
                         capture_output=True, text=True, check=True).stdout
    rows = {ln.split()[0]: ln.split()[1] for ln in out.splitlines()[1:]}
    shipped = {p.stem for p in Path("scripts").glob("com.gaffer.*.plist")}
    assert set(rows) == shipped
    assert rows["com.gaffer.advise"] == "loaded"
    assert rows["com.gaffer.prices"] == "unloaded"
    assert rows["com.gaffer.backup"] == "missing"
    assert "?" not in out
    assert all(c.startswith("list ") for c in calls.read_text().splitlines())
    assert not (home / "Library" / "LaunchAgents" / "com.gaffer.advise.plist").exists()
