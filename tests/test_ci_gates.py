"""CI runs every gate line ``CLAUDE.md`` names, and nothing it does not (holiday F-119).

ROADMAP candidate 7, holiday F-1's workflow held to the rules file.
``CLAUDE.md``'s Commands block names three gate lines (the ruff line, the
inner loop's marker expression and ``npm run check``) and
``.github/workflows/ci.yml`` runs them, with F-57's ``zsh -n`` installer
check beside them; nothing held the two together, so a gate added to one and
not the other drifted silently. A probe on 2026-10-18 found them agreeing,
so this holds a rule nothing held. When they disagree the workflow follows
``CLAUDE.md``, never the reverse.

The workflow is read by regex, not YAML: PyYAML is not in ``uv.lock`` and the
rail adds no dependency. A folded ``run: >-`` block is joined with spaces, as
YAML would fold it.
"""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOW = Path(".github/workflows/ci.yml")
RULES = Path("CLAUDE.md")
README = Path("README.md")

# The gate lines CLAUDE.md's Commands block names: each must be in one run step.
GATES = ['uvx ruff check src tests', '-m "not slow and not golden"', "npm run check"]

# A run step starting with one of these is a gate command and must be one the
# docs name.
CHECKED = ("uvx", "uv run", "npm run", "zsh -n")

# Set-up, not a gate: installing the locked environment and the zsh the
# installer check needs (F-57). Neither is a command a contributor runs to
# judge a change, so the docs need not name it.
SETUP = ("uv sync --locked", "sudo apt-get")

# A deselect is a per-machine exclusion: README's Tests section names it
# beside the command (test_config_toml_loads reads the untracked config.toml),
# so the command is matched without it and the test id is matched alone.
DESELECT = re.compile(r"\s+--deselect\s+(\S+)")

RUN = re.compile(r"^(\s*)(?:-\s+)?run:\s*(.*)$")


def run_steps(text: str) -> list[str]:
    """Every ``run:`` string of a workflow, folded blocks joined."""
    lines = text.splitlines()
    runs: list[str] = []
    i = 0
    while i < len(lines):
        m = RUN.match(lines[i])
        i += 1
        if not m:
            continue
        value = m.group(2).strip()
        if value in (">", ">-", "|", "|-"):
            # The key's own column, so `- run: >-` stops at a sibling key.
            indent = lines[i - 1].index("run:")
            body: list[str] = []
            while i < len(lines) and (
                not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > indent
            ):
                if lines[i].strip():
                    body.append(lines[i].strip())
                i += 1
            value = " ".join(body)
        runs.append(value)
    return runs


def readme_tests() -> str:
    """README's Tests section, from its heading to the next one."""
    text = README.read_text()
    start = text.index("\n## Tests\n")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


def problems(workflow: str, docs: str) -> list[str]:
    """What keeps a workflow's run steps from matching the gate lines the docs name."""
    runs = run_steps(workflow)
    found: list[str] = [
        f"no run step in {WORKFLOW} runs the gate {gate!r}"
        for gate in GATES
        if not any(gate in run for run in runs)]
    for run in runs:
        if run.startswith(SETUP) or not run.startswith(CHECKED):
            continue
        command = DESELECT.sub("", run)
        if command not in docs:
            found.append(
                f"{WORKFLOW} runs {command!r}, which neither {RULES} nor README's Tests names"
            )
        found.extend(
            f"{WORKFLOW} deselects {test_id}, which README's Tests does not name"
            for test_id in DESELECT.findall(run)
            if test_id not in docs)
    return found


def docs_text() -> str:
    return RULES.read_text() + "\n" + readme_tests()


def test_ci_runs_every_gate_line_the_rules_file_names_and_only_named_commands():
    assert problems(WORKFLOW.read_text(), docs_text()) == []


def test_a_workflow_without_the_ruff_step_fails_the_check():
    workflow = WORKFLOW.read_text()
    without = workflow.replace("run: uvx ruff check src tests", "run: echo skipped")
    assert without != workflow
    assert any("ruff" in p for p in problems(without, docs_text()))


def test_a_workflow_running_an_unnamed_command_fails_the_check():
    workflow = WORKFLOW.read_text() + "\n      - run: npm run nowhere-named\n"
    assert any("nowhere-named" in p for p in problems(workflow, docs_text()))


def test_a_folded_run_block_is_joined_as_yaml_folds_it():
    text = (
        'steps:\n  - name: x\n    run: >-\n      uv run pytest -q\n      -m "fast"\n'
        "  - run: >-\n      npm run check\n    working-directory: frontend\n"
    )
    assert run_steps(text) == ['uv run pytest -q -m "fast"', "npm run check"]
