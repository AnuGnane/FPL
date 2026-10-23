"""ruff lints for the Python the project runs (holiday F-136).

ROADMAP candidate 7, in F-110's shape (``tests/test_doc_pins.py``, one
number read from its home and held against the lines that quote it). The
floor's home is ``requires-python`` in ``pyproject.toml``; ruff's
``target-version`` and ``.python-version`` must name the same major.minor.
They had drifted: ruff said ``py311`` while the project required 3.12, so
it linted for a Python nothing ran.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


def ruff_target_mismatch(pyproject: str, python_version: str) -> str | None:
    """Return why the three disagree, or None when they name one floor."""
    data = tomllib.loads(pyproject)
    m = re.search(r">=\s*(\d+)\.(\d+)", data["project"]["requires-python"])
    if m is None:
        return "requires-python has no >= bound"
    major, minor = m.groups()
    problems = []
    target = data["tool"]["ruff"]["target-version"]
    if target != f"py{major}{minor}":
        problems.append(f"ruff target-version is {target}, the floor is {major}.{minor}")
    pinned = python_version.strip()
    if pinned != f"{major}.{minor}" and not pinned.startswith(f"{major}.{minor}."):
        problems.append(f".python-version is {pinned}, the floor is {major}.{minor}")
    return "; ".join(problems) or None


def test_ruff_targets_the_python_floor():
    problem = ruff_target_mismatch(
        Path("pyproject.toml").read_text(), Path(".python-version").read_text()
    )
    assert problem is None, problem


def test_a_target_below_the_floor_fails(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nrequires-python = ">=3.12"\n\n[tool.ruff]\ntarget-version = "py311"\n'
    )
    problem = ruff_target_mismatch(pyproject.read_text(), "3.13\n")
    assert problem is not None
    assert "py311" in problem and ".python-version is 3.13" in problem


def test_ruff_selects_the_pyupgrade_family():
    """Holiday F-188 turned ``UP`` on; dropping it from ``select`` would let
    ``timezone.utc`` and quoted annotations creep back without a word."""
    data = tomllib.loads(Path("pyproject.toml").read_text())
    assert "UP" in data["tool"]["ruff"]["lint"]["select"]


def test_ruff_selects_the_simplify_family():
    """Holiday F-189 turned ``SIM`` on, in F-188's shape: the family stays
    selected or this fails, so it cannot be dropped silently."""
    data = tomllib.loads(Path("pyproject.toml").read_text())
    assert "SIM" in data["tool"]["ruff"]["lint"]["select"]


def test_ruff_selects_the_c4_pie_ret_and_era_families():
    """Holiday F-201 turned ``C4``, ``PIE``, ``RET`` and ``ERA`` on, in
    F-188's shape: each family stays selected or this fails."""
    data = tomllib.loads(Path("pyproject.toml").read_text())
    select = data["tool"]["ruff"]["lint"]["select"]
    assert {"C4", "PIE", "RET", "ERA"} <= set(select)


def test_ruff_selects_the_ble_family_and_strikes_unused_noqa():
    """Holiday F-204 turned ``BLE`` on, so the ``# noqa: BLE001`` marks
    ``CLAUDE.md`` asks for are read by ruff rather than being comments, and
    ``RUF100`` with it, so a mark that guards nothing fails the gate."""
    data = tomllib.loads(Path("pyproject.toml").read_text())
    select = data["tool"]["ruff"]["lint"]["select"]
    assert {"BLE", "RUF100"} <= set(select)


def test_ruff_selects_the_pytest_style_family_without_the_composite_assert():
    """Holiday F-205 turned ``PT`` on, in F-188's shape, with ``PT018`` ruled
    out: the tests' composite asserts read as one sentence, and splitting 656
    of them names no new failure."""
    data = tomllib.loads(Path("pyproject.toml").read_text())
    lint = data["tool"]["ruff"]["lint"]
    assert "PT" in lint["select"]
    assert "PT018" in lint["ignore"]
