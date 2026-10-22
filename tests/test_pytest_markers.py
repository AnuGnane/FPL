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


# Holiday F-184: v18g §2.5 silenced five warning families by message so a new
# one still shows up, but only in a summary line no cloud run reads. "error"
# first turns a new warning into a failure that names its test; each ignore
# after it names its message and category and carries a `#` reason above it.
IGNORE = re.compile(r"ignore:.+:[A-Z]\w*Warning(:[\w\\.]+)?")


def _unreasoned_filters(text: str, filters: list[str]) -> list[str]:
    """The filters after "error" that are malformed or lack a ``#`` line above."""
    lines = [line.strip() for line in text.splitlines()]
    out = []
    for entry in filters[1:]:
        at = [i for i, line in enumerate(lines) if line in (f"'{entry}',", f'"{entry}",')]
        reasoned = len(at) == 1 and at[0] > 0 and lines[at[0] - 1].startswith("#")
        if not IGNORE.fullmatch(entry) or not reasoned:
            out.append(entry)
    return out


def test_a_new_warning_fails_the_suite() -> None:
    assert _ini()["filterwarnings"][0] == "error"


def test_every_ignored_warning_names_its_message_and_category_with_a_reason() -> None:
    text = PYPROJECT.read_text()
    assert _unreasoned_filters(text, _ini()["filterwarnings"]) == []


def test_the_rail_names_an_ignore_without_a_reason_or_a_category() -> None:
    text = (
        "filterwarnings = [\n    \"error\",\n    # why\n    'ignore:a b:DeprecationWarning',\n"
        "    'ignore:c d:FutureWarning',\n    # why\n    'ignore::DeprecationWarning',\n]\n"
    )
    filters = ["error", "ignore:a b:DeprecationWarning", "ignore:c d:FutureWarning",
               "ignore::DeprecationWarning"]
    assert _unreasoned_filters(text, filters) == ["ignore:c d:FutureWarning",
                                                  "ignore::DeprecationWarning"]
