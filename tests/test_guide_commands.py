"""Every CLI command is named in GUIDE §8 and the README (holiday F-100).

ROADMAP candidate 7, in F-87's shape (``tests/test_guide_scripts.py``): both
docs name all of ``gaffer --help``'s commands today, but nothing held the
rule, so the next command could go unnamed. Membership only, no count.
"""

from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from gaffer.cli import app
from tests.test_cli import _plain

GUIDE = Path("docs/GUIDE.md")
README = Path("README.md")

# A row of the Commands box: the name follows the border, its continuation
# lines start with spaces instead (F-100).
_ROW = re.compile(r"^│ ([a-z][a-z0-9-]*)\s", re.MULTILINE)


def _commands() -> list[str]:
    # The way tests/test_cli.py reads them (holiday F-47): plain under any TERM.
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    return _ROW.findall(_plain(result.output))


def _section(text: str, start: str, end: str = "\n## ") -> str:
    head = text.index(start)
    stop = text.find(end, head + len(start))
    return text[head:] if stop == -1 else text[head:stop]


def _unnamed(names: list[str], text: str) -> list[str]:
    # `gaffer <name>` with its options inside the backticks, or a bare
    # `<name>` as in a slash list (`calibrate-injuries` / `calibrate-noise`);
    # the `advise` in `advise-fast` does not stand in for `advise` (F-100).
    return [
        name
        for name in names
        if not re.search(rf"`(gaffer )?{re.escape(name)}( [^`]*)?`", text)
    ]


def _guide_section() -> str:
    return _section(GUIDE.read_text(), "## 8. ", "\n## 9. ")


def _readme_section() -> str:
    return _section(README.read_text(), "## Commands")


def test_help_lists_the_commands_this_rail_reads():
    names = _commands()
    assert "advise" in names and "ui" in names, names


def test_every_cli_command_is_named_in_guide_section_eight_and_the_readme():
    names = _commands()
    assert _unnamed(names, _guide_section()) == []
    assert _unnamed(names, _readme_section()) == []


def test_a_readme_missing_one_commands_row_fails_the_rail():
    readme = _readme_section()
    row = next(line for line in readme.splitlines() if line.startswith("| `gaffer tidy"))
    assert _unnamed(_commands(), readme.replace(row + "\n", "")) == ["tidy"]
