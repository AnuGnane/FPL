"""Every live bash script parses, in the inner loop (holiday F-175).

F-168 and F-173 put ``bash -n`` on ``replay_pair.sh`` and ``shots.sh`` in CI;
this runs the same parse here, so a broken driver fails before the Mac runs a
replay or shoots a stage. Scripts are picked by their bash shebang:
``install_automation.sh`` is zsh, and F-57's CI step and F-5's test parse it
with ``zsh -n``.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TREES = (ROOT / "scripts", ROOT / "frontend" / "scripts")


def _bash_scripts() -> list[Path]:
    return sorted(
        p for tree in TREES for p in tree.rglob("*.sh")
        if "archive" not in p.relative_to(tree).parts
        and p.read_text(encoding="utf-8").partition("\n")[0].endswith("bash")
    )


def test_there_are_bash_scripts_to_parse():
    names = {p.name for p in _bash_scripts()}
    assert {"replay_pair.sh", "shots.sh"} <= names, names


@pytest.mark.parametrize("script", _bash_scripts(), ids=lambda p: p.name)
def test_every_live_bash_script_parses_under_bash_n(script):
    run = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
