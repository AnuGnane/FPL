"""The two launchd tables carry the plists' fire times (holiday F-97).

GUIDE §7 and the README's "Automation" section each tabulate the nine
``scripts/com.gaffer.*.plist`` jobs with a ``When`` cell. The README's
``com.gaffer.field`` row read "Sat & Sun 12:30" while the plist fires at
18:30, so this rail reads every plist's ``StartCalendarInterval`` and asserts
each table's row names every ``HH:MM`` it fires at and the three-letter day
for each ``Weekday`` it names. Membership only: prose around the times is
free.

Holiday F-115 reads the command too: every ``gaffer <command>`` in a plist's
``ProgramArguments`` must appear in backticks in its row's "What it does"
cell (bare or as ``gaffer <command>``), with a digest's ``--kind`` value
beside it. Both tables are held: the README's rows already named commands
(its ``advise`` row), so the rule is not narrowed to the GUIDE's.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

SCRIPTS = Path("scripts")
DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]  # launchd Weekday 0..6


def _load_status():
    spec = importlib.util.spec_from_file_location(
        "automation_status", SCRIPTS / "automation_status.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


load_plist = _load_status().load_plist


def _section(path: str, start: str, end_prefix: str) -> str:
    text = Path(path).read_text()
    head = text.index(start)
    tail = text.find(end_prefix, head + len(start))
    return text[head : tail if tail != -1 else len(text)]


TABLES = {
    "GUIDE §7": lambda: _section("docs/GUIDE.md", "## 7. The automation", "\n## 8."),
    "README Automation": lambda: _section("README.md", "## Automation\n", "\n## "),
}


def _when_cell(table: str, label: str) -> str | None:
    for line in table.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[1] == f"`{label}`":
            return cells[0]
    return None


def _fires(plist: dict) -> tuple[set[str], set[str]]:
    """The ``HH:MM`` times and three-letter days a plist's calendar names."""
    interval = plist.get("StartCalendarInterval", [])
    entries = interval if isinstance(interval, list) else [interval]
    times = {f"{e.get('Hour', 0):02d}:{e.get('Minute', 0):02d}" for e in entries}
    days = {DAYS[e["Weekday"] % 7] for e in entries if "Weekday" in e}
    return times, days


def missing(table: str, label: str, plist: dict) -> list[str]:
    """What the row for ``label`` fails to name; ``["no row"]`` if absent."""
    cell = _when_cell(table, label)
    if cell is None:
        return ["no row"]
    times, days = _fires(plist)
    return sorted(t for t in times | days if t not in cell)


PLISTS = sorted(SCRIPTS.glob("com.gaffer.*.plist"))


def test_there_are_plists_to_check():
    assert PLISTS


@pytest.mark.parametrize("table_name", sorted(TABLES))
@pytest.mark.parametrize("plist_path", PLISTS, ids=lambda p: p.stem)
def test_each_tables_when_cell_names_the_plists_times_and_days(table_name, plist_path):
    plist = load_plist(plist_path)
    gaps = missing(TABLES[table_name](), plist["Label"], plist)
    assert not gaps, f"{table_name} row for {plist['Label']} lacks {gaps}"


def test_a_wrong_time_in_a_row_fails_the_check():
    plist = {
        "Label": "com.gaffer.x",
        "StartCalendarInterval": [{"Weekday": 6, "Hour": 18, "Minute": 30}],
    }
    assert missing("| Sat 12:30 | `com.gaffer.x` | y |", "com.gaffer.x", plist) == ["18:30"]
    assert missing("| Sat 18:30 | `com.gaffer.x` | y |", "com.gaffer.x", plist) == []
    assert missing("| Sun 18:30 | `com.gaffer.x` | y |", "com.gaffer.x", plist) == ["Sat"]


_COMMAND = re.compile(r"\bgaffer ([a-z][a-z-]*)(?: --kind (\w+))?")


def _what_cell(table: str, label: str) -> str | None:
    for line in table.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[1] == f"`{label}`":
            return cells[2]
    return None


def unnamed_commands(table: str, label: str, plist: dict) -> list[str]:
    """The commands (with any ``--kind``) the plist runs that the row for
    ``label`` does not name in backticks; ``["no row"]`` if absent."""
    cell = _what_cell(table, label)
    if cell is None:
        return ["no row"]
    shell = " ".join(plist.get("ProgramArguments", []))
    gaps = []
    for command, kind in _COMMAND.findall(shell):
        want = f"{command} --kind {kind}" if kind else command
        if not re.search(rf"`(?:gaffer )?{re.escape(want)}[`\s:]", cell):
            gaps.append(want)
    return sorted(set(gaps))


def test_the_plists_name_the_commands_this_rail_reads():
    commands = {c for p in PLISTS
                for c, _ in _COMMAND.findall(
                    " ".join(load_plist(p).get("ProgramArguments", [])))}
    assert {"prices", "train", "advise", "digest", "field-scrape"} <= commands, commands


@pytest.mark.parametrize("table_name", sorted(TABLES))
@pytest.mark.parametrize("plist_path", PLISTS, ids=lambda p: p.stem)
def test_each_tables_row_names_the_commands_its_plist_runs(table_name, plist_path):
    plist = load_plist(plist_path)
    gaps = unnamed_commands(TABLES[table_name](), plist["Label"], plist)
    assert not gaps, f"{table_name} row for {plist['Label']} lacks {gaps}"


def test_an_advise_row_without_train_fails_the_check():
    plist = load_plist(SCRIPTS / "com.gaffer.advise.plist")
    table = TABLES["GUIDE §7"]()
    assert unnamed_commands(table, "com.gaffer.advise", plist) == []
    assert unnamed_commands(table.replace("then `train` ", "then "),
                            "com.gaffer.advise", plist) == ["train"]
