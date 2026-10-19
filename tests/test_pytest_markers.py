"""Every pytest marker in ``tests/`` is a built-in or registered (holiday F-132).

``CLAUDE.md``'s inner loop deselects with ``-m "not slow and not golden"``;
v18g §2.5 registered those two markers in ``pyproject.toml``. Without
``--strict-markers`` a misspelt marker deselects nothing and says nothing,
so the flag stands in ``addopts`` and this rail names the marker a future
run would fail collection on.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

PYPROJECT = Path("pyproject.toml")
TESTS = Path("tests")

# pytest's own marks, which --strict-markers accepts without registration.
BUILTIN = frozenset(
    {"parametrize", "skip", "skipif", "xfail", "usefixtures", "filterwarnings"}
)

MARK = re.compile(r"pytest\.mark\.([A-Za-z_]\w*)")


def _ini() -> dict:
    return tomllib.loads(PYPROJECT.read_text())["tool"]["pytest"]["ini_options"]


def _registered(ini: dict) -> set[str]:
    return {line.split(":", 1)[0].strip() for line in ini.get("markers", [])}


def _unregistered(texts: dict[str, str], registered: set[str]) -> list[str]:
    return sorted(
        f"{name}: {mark}"
        for name, text in texts.items()
        for mark in MARK.findall(text)
        if mark not in BUILTIN and mark not in registered
    )


def test_pyproject_adds_strict_markers() -> None:
    assert "--strict-markers" in _ini().get("addopts", "").split()


def test_every_marker_under_tests_is_builtin_or_registered() -> None:
    texts = {str(p): p.read_text() for p in sorted(TESTS.rglob("*.py"))}
    assert _unregistered(texts, _registered(_ini())) == []


def test_the_rail_names_a_misspelt_marker() -> None:
    # Built by concatenation so the whole-tree scan does not read it here.
    texts = {"tests/test_x.py": "@pytest." + "mark.slwo\ndef test_a(): ...\n"}
    assert _unregistered(texts, {"slow", "golden"}) == ["tests/test_x.py: slwo"]
