"""`CLAUDE.md`'s Commands block names real commands and npm scripts (holiday F-131).

ROADMAP candidate 7, in F-100's and F-119's shape: the fenced block under
`CLAUDE.md`'s "## Commands" is what a run types first, and nothing checked it
against the code. Every `gaffer <sub>` after `uv run` there is one of the
Typer app's commands (``tests.test_guide_commands._commands``), every
`npm run <script>` in `CLAUDE.md`, the README and the GUIDE is a key of
`frontend/package.json`'s ``scripts``, and every marker a `-m "<expr>"` in
the block names is registered in `pyproject.toml`. Membership only.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from tests.test_guide_commands import _commands

CLAUDE = Path("CLAUDE.md")
DOCS = [CLAUDE, Path("README.md"), Path("docs/GUIDE.md")]
PACKAGE = Path("frontend/package.json")
PYPROJECT = Path("pyproject.toml")

_BOOLEAN = {"not", "and", "or"}


def commands_block(text: str) -> str:
    """The first fenced block after `## Commands`."""
    head = text.index("## Commands")
    start = text.index("```", head)
    stop = text.index("```", start + 3)
    return text[start + 3:stop]


def gaffer_subcommands(block: str) -> list[str]:
    return re.findall(r"uv run gaffer ([a-z][a-z0-9-]*)", block)


def npm_scripts(text: str) -> list[str]:
    return re.findall(r"npm run ([a-z][a-z0-9:-]*)", text)


def marker_names(block: str) -> list[str]:
    names = []
    for expr in re.findall(r"""-m ["']([^"']+)["']""", block):
        names += [w for w in re.findall(r"[A-Za-z_]\w*", expr)
                  if w not in _BOOLEAN]
    return names


def registered_markers() -> set[str]:
    opts = tomllib.loads(PYPROJECT.read_text())["tool"]["pytest"]["ini_options"]
    return {m.split(":", 1)[0].strip() for m in opts.get("markers", [])}


def problems(block: str, docs: list[str], commands: list[str],
             scripts: set[str], markers: set[str]) -> list[str]:
    out = [f"gaffer {c} is not a command"
           for c in gaffer_subcommands(block) if c not in commands]
    out += [f"npm run {s} is not a package.json script"
            for text in docs for s in npm_scripts(text) if s not in scripts]
    out += [f"marker {m} is not registered"
            for m in marker_names(block) if m not in markers]
    return out


def _scripts() -> set[str]:
    return set(json.loads(PACKAGE.read_text())["scripts"])


def test_the_commands_block_names_real_commands_scripts_and_markers():
    block = commands_block(CLAUDE.read_text())
    assert gaffer_subcommands(block), "the block names no gaffer command"
    assert marker_names(block), "the block names no -m marker"
    docs = [p.read_text() for p in DOCS]
    assert any(npm_scripts(t) for t in docs), "the docs name no npm script"
    assert problems(block, docs, _commands(), _scripts(),
                    registered_markers()) == []


def test_a_misnamed_command_script_or_marker_fails_the_check():
    block = ('uv run gaffer advise\nuv run gaffer adivse\n'
             'pytest -q -m "not slow and not goldne"\n')
    docs = ["cd frontend && npm run check", "npm run chek"]
    assert problems(block, docs, ["advise"], {"check"},
                    {"slow", "golden"}) == [
        "gaffer adivse is not a command",
        "npm run chek is not a package.json script",
        "marker goldne is not registered"]
