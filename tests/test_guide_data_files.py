"""Every data file the code spells is named in GUIDE §9 (holiday F-117).

ROADMAP candidate 7, in F-106's shape (``tests/test_readme_modules.py``): §9
named six logs and three report files while ``src/gaffer`` spelled
thirty-odd, so a new file could go unnamed. A name is a quoted literal ending
in ``.parquet``, ``.jsonl``, ``.json``, ``.toml`` or ``.csv`` that starts with
a letter, digit or underscore, so a suffix such as ``".meta.json"`` is not a
name. ``config.toml`` and ``config.local.toml`` are configuration, not data.
A name counts as named when a backtick span in §9 ends with it, so
``data/live/field_eo_log.parquet`` names ``field_eo_log.parquet``. Membership
only, no count.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
GUIDE = ROOT / "docs/GUIDE.md"
SRC = ROOT / "src/gaffer"
CONFIGURATION = {"config.toml", "config.local.toml"}

_NAME = re.compile(r"""["']([A-Za-z0-9_][A-Za-z0-9_.-]*\.(?:parquet|jsonl|json|toml|csv))["']""")


def _names() -> set[str]:
    return {name for path in SRC.rglob("*.py")
            for name in _NAME.findall(path.read_text())} - CONFIGURATION


def _section_nine() -> str:
    text = GUIDE.read_text()
    head = text.index("## 9. ")
    return text[head:text.index("\n## 10. ", head)]


def _unnamed(names: set[str], section: str) -> list[str]:
    spans = re.findall(r"`([^`\n]+)`", section)
    return sorted(name for name in names
                  if not any(span == name or span.endswith("/" + name)
                             for span in spans))


def test_the_walk_finds_the_codes_data_files():
    names = _names()
    assert len(names) >= 20, sorted(names)
    assert "player_gw.parquet" in names and "config.toml" not in names, sorted(names)


def test_every_data_file_the_code_spells_is_named_in_guide_section_nine():
    assert _unnamed(_names(), _section_nine()) == []


def test_a_section_nine_missing_one_name_fails_the_rail():
    section = _section_nine().replace("`pen_tracker.json`", "pen_tracker")
    assert _unnamed(_names(), section) == ["pen_tracker.json"]
