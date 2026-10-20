"""Holiday F-147: every module under ``src/gaffer/`` opens with a docstring.

``CLAUDE.md`` "Writing style in code and docs": comments and docstrings say
why, not what, and cite the cycle that introduced a rule. A module with no
docstring says neither, so this rail asks each one to say what it is for.

An ``__init__.py`` with an empty body is a package marker, not a module, and
is skipped. The allowlist holds the files still without a docstring and can
only shrink, in F-69's shape (``tests/test_noqa_reasons.py``): ``config.py``
is a golden import (``tests/test_golden_board.py``, ``tests/test_pipeline.py``),
so under HOLIDAY.md's Merging rule 2 its docstring is F-148's, the Mac's.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "gaffer"

ALLOWED = {"config.py"}


def _undocumented(tree: Path) -> set[str]:
    """Paths, relative to ``tree``, of modules that open with no docstring."""
    out = set()
    for path in sorted(tree.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if path.name == "__init__.py" and not text.strip():
            continue
        if not ast.get_docstring(ast.parse(text, filename=str(path))):
            out.add(path.relative_to(tree).as_posix())
    return out


def test_every_module_outside_the_allowlist_opens_with_a_docstring():
    assert sorted(_undocumented(PACKAGE) - ALLOWED) == []


def test_the_allowlist_holds_exactly_the_modules_still_without_one():
    assert _undocumented(PACKAGE) & ALLOWED == ALLOWED


def test_a_module_without_a_docstring_is_caught_and_an_empty_init_is_not(
        tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "bare.py").write_text("x = 1\n")
    (tmp_path / "told.py").write_text('"""What this is for."""\nx = 1\n')
    (tmp_path / "empty_doc.py").write_text('""""""\nx = 1\n')
    assert _undocumented(tmp_path) == {"bare.py", "empty_doc.py"}
