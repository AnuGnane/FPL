"""Every test file that skips without local data is named in GUIDE §10 (holiday F-133).

ROADMAP candidate 7 and F-1's rule that a green gate means what it says, in
F-87's shape (``tests/test_guide_scripts.py``): fourteen files under
``tests/`` skip for a missing parquet, fixture list, built frontend, zsh or
git range, and §10's "What skips without local data" table says which and
what runs them. Membership only, no count and no allowlist; the section is
found by its heading as ``tests/test_guide_commands.py``'s ``_section``
finds §8.
"""

from __future__ import annotations

from pathlib import Path

from tests.test_guide_commands import _section

GUIDE = Path("docs/GUIDE.md")
TESTS = Path("tests")
HEADING = "### What skips without local data"

# Built by concatenation so this file's own text does not count as a skip.
SKIPS = ("pytest." + "skip(", "pytest." + "mark.skipif")


def _skipping(texts: dict[str, str]) -> list[str]:
    return sorted(
        name for name, text in texts.items() if any(s in text for s in SKIPS)
    )


def _unnamed(files: list[str], section: str) -> list[str]:
    return [f for f in files if f"`{f}`" not in section]


def test_every_file_that_skips_is_named_in_the_guide() -> None:
    texts = {p.as_posix(): p.read_text() for p in sorted(TESTS.rglob("*.py"))}
    files = _skipping(texts)
    assert files, "no skipping file found; the scan is broken"
    section = _section(GUIDE.read_text(), HEADING, "\n## ")
    assert _unnamed(files, section) == []


def test_the_rail_names_a_skipping_file_the_table_misses() -> None:
    texts = {
        "tests/test_a.py": "    pytest." + "skip('no parquet')\n",
        "tests/test_b.py": "def test_b(): ...\n",
    }
    section = HEADING + "\n\n| `tests/test_c.py` | x | y |\n"
    assert _unnamed(_skipping(texts), section) == ["tests/test_a.py"]
