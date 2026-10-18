"""The README names the frontend's directories and hubs (holiday F-118).

ROADMAP candidate 7, F-106's frontend half (``tests/test_readme_modules.py``):
"Where things live" gave ``frontend/`` one bullet and named none of
``frontend/src/``'s directories or hubs. Every directory directly under
``frontend/src/`` and ``frontend/src/hubs/``, and every hub file that is not
a test, is named in backticks there, bare or as the tail of a path. Membership
only, no count.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
README = ROOT / "README.md"
SRC = ROOT / "frontend/src"


def _names() -> list[str]:
    """Each directory as ``name/`` and each hub as ``Name.tsx``."""
    dirs = [f"{p.name}/" for root in (SRC, SRC / "hubs")
            for p in root.iterdir() if p.is_dir()]
    hubs = [p.name for p in (SRC / "hubs").glob("*.tsx") if ".test." not in p.name]
    return sorted(dirs + hubs)


def _section(text: str) -> str:
    head = text.index("## Where things live")
    stop = text.find("\n## ", head + 1)
    return text[head:] if stop == -1 else text[head:stop]


def _unnamed(names: list[str], text: str) -> list[str]:
    spans = re.findall(r"`([^`\n]+)`", text)
    return [name for name in names
            if not any(span == name or span.endswith("/" + name) for span in spans)]


def test_the_frontend_has_the_names_this_rail_reads():
    names = _names()
    assert "kit/" in names and "this-week/" in names and "ThisWeek.tsx" in names, names
    assert not any(".test." in name for name in names), names


def test_every_frontend_directory_and_hub_is_named_in_where_things_live():
    assert _unnamed(_names(), _section(README.read_text())) == []


def test_a_readme_missing_one_hubs_line_fails_the_rail():
    section = _section(README.read_text())
    line = next(row for row in section.splitlines() if row.startswith("    - `Live.tsx`"))
    assert _unnamed(_names(), section.replace(line + "\n", "")) == ["Live.tsx"]
