"""Every `gaffer <command>` the docs name is a real command (holiday F-151).

ROADMAP candidate 7, the converse of F-100 and F-105
(``tests/test_guide_commands.py``: GUIDE §8 and the README name every
command), in F-131's shape (``tests/test_claude_commands.py``). A renamed or
retired command leaves its mentions behind, so every backticked
`` `gaffer <word>` `` or `` `uv run gaffer <word>` `` in the docs below must be
one of the Typer app's commands. Only the first word after `gaffer` is read;
an option after it is not. `HOLIDAY.md` is left out: its ticked F-96 names
the `refresh-data` job kind in this form, and a queue line may quote a fake.
Membership only, no count.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.test_guide_commands import _commands

DOCS = [
    Path("docs/GUIDE.md"),
    Path("README.md"),
    Path("CLAUDE.md"),
    Path("docs/superpowers/ROADMAP.md"),
    Path("docs/superpowers/CONVENTIONS.md"),
    Path("docs/superpowers/specs/2026-10-07-v20-model-cycle-design.md"),
]

_NAMED = re.compile(r"`(?:uv run )?gaffer ([a-z][a-z-]*)")


def unknown_commands(paths: list[Path], known: set[str]) -> list[str]:
    """`file:line: word` for each named command `known` does not hold."""
    return [
        f"{path}:{number}: {word}"
        for path in paths
        for number, line in enumerate(path.read_text().splitlines(), 1)
        for word in _NAMED.findall(line)
        if word not in known
    ]


def test_every_command_the_docs_name_exists():
    stale = unknown_commands(DOCS, set(_commands()))
    assert not stale, "docs name commands the CLI does not have:\n" + "\n".join(stale)


def test_the_docs_still_name_commands_this_rail_reads():
    # A rail that matches nothing passes on anything (F-151).
    assert any(_NAMED.search(path.read_text()) for path in DOCS)


def test_a_made_up_command_is_caught(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("Run `gaffer advise` then `uv run gaffer frobnicate --now`.\n")
    assert unknown_commands([doc], set(_commands())) == [f"{doc}:1: frobnicate"]
