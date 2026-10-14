"""The GUIDE's readings table names only prefixes the appendix collects
(holiday F-51).

``docs/GUIDE.md`` §12.5's "The readings" table lists each holiday script
that prints a reading and the line prefixes it prints. The night shift
pastes what ``scripts/v20_appendix.py`` collects, so a prefix the table
names and ``READINGS`` does not would be a line the GUIDE promises and the
appendix drops. The table is parsed from the file, so it cannot drift.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, "scripts")

import v20_appendix as ap  # noqa: E402 — scripts/ is not a package; the path insert must come first

GUIDE = Path("docs/GUIDE.md")

_HEADING = "#### The readings"


def _rows() -> list[list[str]]:
    """The table's body rows, each a list of its cells."""
    text = GUIDE.read_text()
    assert _HEADING in text
    section = text.split(_HEADING, 1)[1]
    rows = []
    for line in section.splitlines():
        if line.startswith("#"):
            break
        if not line.startswith("|") or set(line) <= set("|-: "):
            continue
        rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows[1:]  # the header row


def _script(cell: str) -> str:
    match = re.search(r"scripts/\w+\.py", cell)
    assert match, cell
    return match.group(0)


def _prefixes(cell: str) -> list[str]:
    return re.findall(r"`([A-Z][A-Z0-9_]+)`", cell)


def test_the_table_lists_every_reading_script():
    scripts = {_script(row[0]) for row in _rows()}
    assert {script for script, _ in ap.READINGS} <= scripts
    assert "scripts/v20_appendix.py" in scripts


def test_every_prefix_the_table_names_is_one_the_appendix_collects():
    collected = dict(ap.READINGS)
    for row in _rows():
        script, prefixes = _script(row[0]), _prefixes(row[1])
        if script == "scripts/v20_appendix.py":
            assert prefixes == []
            continue
        assert prefixes, script
        assert set(prefixes) == set(collected[script]), script


def test_each_row_says_whether_its_verdict_is_a_card_an_arm_or_a_ruling():
    for row in _rows():
        if _script(row[0]) == "scripts/v20_appendix.py":
            continue
        assert row[3].split()[0].strip("*:") in {"card", "arm", "ruling"}, row
