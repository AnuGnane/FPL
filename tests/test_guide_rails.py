"""Every doc rail is named by path in GUIDE §10 (holiday F-179).

ROADMAP candidate 7 (housekeeping), in F-165's shape
(``tests/test_module_coverage.py``: every module named by a test, an
allowlist with a reason per entry). §10 "How the project measures itself"
names its rails by path, and on 2026-10-21 nineteen test modules that read
a doc or a config file were named nowhere in the GUIDE, so a reader of §10
could not find what holds the docs to the code. A doc rail is a
``tests/test_*.py`` whose source names ``README.md``, ``CLAUDE.md``,
``HOLIDAY.md``, ``docs/``, ``.github/``, ``pyproject.toml``,
``package.json`` or ``config.example.toml``; each is named in §10 unless
``INCIDENTAL`` says why it only reads one in passing.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.test_guide_commands import _section

GUIDE = Path("docs/GUIDE.md")
TESTS = Path("tests")
HEADING = "## 10. How the project measures itself"

_DOC = re.compile(
    r"(?<![\w.-])(?:(?:README|CLAUDE|HOLIDAY)\.md|pyproject\.toml"
    r"|package\.json|config\.example\.toml)(?![\w-])"
    r"|(?<![\w.-])(?:docs|\.github)/"
)

# A module that names a doc only in passing, with the reason it is not a
# rail on the docs; each was read by hand (F-179).
INCIDENTAL = {
    "tests/test_core_insights.py":
        "a docstring cites the example config's `train_seasons` as one "
        "caller; the module tests the archive's season list, not a doc",
    "tests/test_v12_w5_config_overlay.py":
        "matches the example file's name in the loader's missing-config "
        "error message; it reads no doc",
}


def _doc_rails(texts: dict[str, str]) -> list[str]:
    return sorted(name for name, text in texts.items() if _DOC.search(text))


def _unnamed(files: list[str], section: str) -> list[str]:
    return [
        f for f in files if f not in INCIDENTAL and f"`{f}`" not in section
    ]


def _texts() -> dict[str, str]:
    return {p.as_posix(): p.read_text() for p in sorted(TESTS.glob("test_*.py"))}


def test_every_doc_rail_is_named_in_guide_section_ten() -> None:
    files = _doc_rails(_texts())
    assert len(files) > 20, "few doc rails found; the scan is broken"
    section = _section(GUIDE.read_text(), HEADING)
    assert _unnamed(files, section) == []


def test_every_incidental_entry_is_a_module_that_names_a_doc() -> None:
    texts = _texts()
    stale = [f for f in INCIDENTAL if f not in texts or not _DOC.search(texts[f])]
    assert stale == []


def test_the_rail_names_a_doc_rail_the_section_misses() -> None:
    texts = {
        "tests/test_a.py": 'Path("docs/GUIDE.md").read_text()\n',
        "tests/test_b.py": 'open("pyproject.toml")\n',
        "tests/test_c.py": "def test_c(): ...\n",
        "tests/test_d.py": 'url = "https://x.github.com/y"\n',
    }
    section = HEADING + "\n\n`tests/test_b.py` pins the floor.\n"
    assert _doc_rails(texts) == ["tests/test_a.py", "tests/test_b.py"]
    assert _unnamed(_doc_rails(texts), section) == ["tests/test_a.py"]
