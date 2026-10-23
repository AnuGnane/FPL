"""CI's Python and Node versions each read one pinned file (holiday F-150).

ROADMAP candidate 7 (housekeeping), in F-136's shape
(``tests/test_ruff_target.py``: one floor, every reader equal to it). The
workflow read ``.python-version`` for Python but said ``node-version: 22`` as
a literal, so the Node the gate runs on was pinned nowhere a developer reads.
Now ``frontend/.nvmrc`` holds the major, the workflow reads it, and
``package.json``'s ``engines.node`` is the same floor.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/ci.yml"
NVMRC = ROOT / "frontend/.nvmrc"
PACKAGE = ROOT / "frontend/package.json"

_LITERAL = re.compile(r"^\s*(python|node)-version:", re.MULTILINE)
_NODE_FILE = re.compile(r"^\s*node-version-file:\s*(\S+)\s*$", re.MULTILINE)


def literals(workflow: str) -> list[str]:
    """The ``*-version:`` keys a workflow sets as a literal, not a file."""
    return _LITERAL.findall(workflow)


def test_the_workflow_sets_no_version_as_a_literal():
    assert literals(WORKFLOW.read_text(encoding="utf-8")) == []


def test_node_reads_the_nvmrc_and_package_json_holds_the_same_floor():
    files = _NODE_FILE.findall(WORKFLOW.read_text(encoding="utf-8"))
    assert files and set(files) == {"frontend/.nvmrc"}
    major = NVMRC.read_text(encoding="utf-8")
    assert re.fullmatch(r"\d+\n", major)
    engines = json.loads(PACKAGE.read_text(encoding="utf-8"))["engines"]
    assert engines["node"] == f">={major.strip()}"


def test_the_rail_bites_on_a_literal_node_version(tmp_path):
    sample = tmp_path / "ci.yml"
    sample.write_text("      - uses: actions/setup-node@v4\n"
                      "        with:\n          node-version: 22\n"
                      "          python-version-file: .python-version\n")
    assert literals(sample.read_text()) == ["node"]
