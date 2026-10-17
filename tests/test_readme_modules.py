"""Every module under ``src/gaffer/`` is named in the README (holiday F-106).

ROADMAP candidate 7, in F-87's shape (``tests/test_guide_scripts.py``): the
README's "Where things live" named seven modules and four of the eight
sub-packages, and eleven modules were named nowhere a reader would look. A
new module is given its line there, or this fails. Membership only, no count.
"""

from __future__ import annotations

import re
from pathlib import Path

README = Path("README.md")
PACKAGE = Path("src/gaffer")


def _names() -> list[str]:
    """Each module as ``name.py`` and each sub-package as ``name/``."""
    modules = [p.name for p in PACKAGE.glob("*.py") if p.name != "__init__.py"]
    packages = [
        f"{p.name}/"
        for p in PACKAGE.iterdir()
        if p.is_dir() and (p / "__init__.py").exists()
    ]
    return sorted(modules + packages)


def _section(text: str) -> str:
    head = text.index("## Where things live")
    stop = text.find("\n## ", head + 1)
    return text[head:] if stop == -1 else text[head:stop]


def _unnamed(names: list[str], text: str) -> list[str]:
    # In backticks on its own: `io.py` is not named by `price_io.py` (F-106).
    return [name for name in names if not re.search(rf"`{re.escape(name)}`", text)]


def test_the_package_has_the_names_this_rail_reads():
    names = _names()
    assert "advise.py" in names and "web/" in names, names
    assert "__init__.py" not in names and "__pycache__/" not in names


def test_every_module_and_sub_package_is_named_in_where_things_live():
    assert _unnamed(_names(), _section(README.read_text())) == []


def test_a_readme_missing_one_modules_line_fails_the_rail():
    section = _section(README.read_text())
    line = next(row for row in section.splitlines() if row.startswith("  - `tidy.py`"))
    assert _unnamed(_names(), section.replace(line + "\n", "")) == ["tidy.py"]
