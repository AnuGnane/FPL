"""Every CLI command is named in GUIDE §8 and the README (holiday F-100).

ROADMAP candidate 7, in F-87's shape (``tests/test_guide_scripts.py``): both
docs name all of ``gaffer --help``'s commands today, but nothing held the
rule, so the next command could go unnamed. Membership only, no count.
Since F-105 every option of every command is held to §8 the same way.
Since F-191 every command is also invoked by some test beyond ``--help``,
or sits in ``UNEXERCISED`` until one is written.
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


# An option row of a command's Options box: the long name follows the border,
# after an optional `*` (required) and short flag; the `--no-x` of a pair sits
# later on the same row, so only `--x` is read (holiday F-105).
_OPTION = re.compile(r"^│ (?:\* )?\s*(?:-[a-zA-Z],?\s+)?(--[a-z][a-z0-9-]*)", re.MULTILINE)


def _options(name: str) -> list[str]:
    result = CliRunner().invoke(app, [name, "--help"])
    assert result.exit_code == 0, name
    return [o for o in _OPTION.findall(_plain(result.output)) if o != "--help"]


def _unnamed_options(options: list[str], text: str) -> list[str]:
    # Inside one backtick span of the section, `--n` not standing in for `--no-x`.
    spans = re.findall(r"`([^`]*)`", text)
    return [
        option
        for option in options
        if not any(re.search(rf"{re.escape(option)}(?![a-z0-9-])", span) for span in spans)
    ]


def test_help_lists_the_options_this_rail_reads():
    assert "--open-browser" in _options("ui")
    assert "--no-open-browser" not in _options("ui")


def test_every_cli_option_is_named_in_guide_section_eight():
    section = _guide_section()
    missing = {
        name: unnamed
        for name in _commands()
        if (unnamed := _unnamed_options(_options(name), section))
    }
    assert missing == {}


def test_a_section_missing_one_options_mention_fails_the_rail():
    section = _guide_section()
    assert "`--lan` serves" in section
    assert _unnamed_options(["--lan"], section.replace("`--lan` serves", "serves")) == ["--lan"]


# A test invokes a command when its name opens the argument list of a
# ``runner.invoke(app, [...])`` (or ``cli.app``), or follows the gaffer
# executable in a ``subprocess.run([...])`` argv (holiday F-191).
_INVOKED = re.compile(
    r'invoke\(\s*(?:cli\.)?app,\s*\[\s*"([a-z][a-z0-9-]*)"(?!\s*,\s*"--help"\s*\])'
)
_SPAWNED = re.compile(r'subprocess\.run\(\s*\[\s*[^,\]]*gaffer[^,\]]*,\s*"([a-z][a-z0-9-]*)"')

# The commands no test invokes beyond ``--help``, held exactly in F-69's shape:
# a new command without a test fails the rail, and so does a test written for
# one listed here until its line is struck (F-191; F-192 emptied it with
# ``tests/test_cli_commands.py``).
UNEXERCISED: set[str] = set()


def _exercised(sources: list[str]) -> set[str]:
    found: set[str] = set()
    for text in sources:
        found.update(_INVOKED.findall(text))
        found.update(_SPAWNED.findall(text))
    return found


def _test_sources() -> list[str]:
    return [p.read_text(encoding="utf-8") for p in sorted(Path("tests").glob("test_*.py"))
            if p.name != "test_guide_commands.py"]


def test_every_cli_command_is_exercised_by_a_test_or_allowlisted():
    unexercised = set(_commands()) - _exercised(_test_sources())
    assert unexercised - UNEXERCISED == set()


def test_each_allowlisted_command_is_still_unexercised_and_still_a_command():
    exercised = _exercised(_test_sources())
    assert UNEXERCISED & exercised == set()
    assert UNEXERCISED - set(_commands()) == set()


def test_the_rail_reads_invoke_and_subprocess_and_skips_a_bare_help():
    sample = (
        'runner.invoke(app, ["advise", "--gw", "7"])\n'
        'result = runner.invoke(\n    cli.app,\n    ["tidy"],\n)\n'
        'subprocess.run([str(gaffer), "refresh"], cwd=tmp)\n'
        'runner.invoke(app, ["train", "--help"])\n'
    )
    assert _exercised([sample]) == {"advise", "tidy", "refresh"}
