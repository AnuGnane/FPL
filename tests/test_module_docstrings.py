"""Holiday F-147: every module under ``src/gaffer/`` opens with a docstring.

``CLAUDE.md`` "Writing style in code and docs": comments and docstrings say
why, not what, and cite the cycle that introduced a rule. A module with no
docstring says neither, so this rail asks each one to say what it is for.

An ``__init__.py`` with an empty body is a package marker, not a module, and
is skipped. The allowlist holds the files still without a docstring and can
only shrink, in F-69's shape (``tests/test_noqa_reasons.py``): ``config.py``
is a golden import (``tests/test_golden_board.py``, ``tests/test_pipeline.py``),
so under HOLIDAY.md's Merging rule 2 its docstring is F-148's, the Mac's.

Holiday F-170 asks the same of ``tests/`` (``test_*.py`` only, so fixtures
and helpers are out), with its own allowlist ``TESTS_ALLOWED`` in the same
shape. ``test_odds.py`` and ``test_web_jobs.py`` are orchestrator-only
(``CLAUDE.md``), so a holiday run may not write their docstrings and they
stay on it for good.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "gaffer"

ALLOWED = {"config.py"}

TESTS = ROOT / "tests"

# F-170: the test modules still without a docstring. It only shrinks; the
# two orchestrator-only files are the orchestrator's to document.
TESTS_ALLOWED = {
    "test_league.py",
    "test_league_mode.py",
    "test_live.py",
    "test_live_gw.py",
    "test_match_odds.py",
    "test_milp.py",
    "test_minutes.py",
    "test_odds.py",
    "test_parse.py",
    "test_policy.py",
    "test_prices.py",
    "test_report.py",
    "test_scenarios.py",
    "test_store.py",
    "test_team_model.py",
    "test_tracking.py",
    "test_train.py",
    "test_understat.py",
    "test_web_app.py",
    "test_web_jobs.py",
    "test_web_league.py",
    "test_web_live.py",
    "test_web_meta.py",
    "test_web_players.py",
    "test_web_quality.py",
    "test_zeros_diagnostic.py",
}


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


def _undocumented_tests(tree: Path) -> set[str]:
    """Names of the ``test_*.py`` files directly under ``tree`` with no
    docstring; conftest and helpers are not test modules."""
    return {name for name in _undocumented(tree)
            if "/" not in name and name.startswith("test_")}


def test_every_module_outside_the_allowlist_opens_with_a_docstring():
    assert sorted(_undocumented(PACKAGE) - ALLOWED) == []


def test_the_allowlist_holds_exactly_the_modules_still_without_one():
    assert _undocumented(PACKAGE) & ALLOWED == ALLOWED


def test_every_test_module_outside_its_allowlist_opens_with_a_docstring():
    assert sorted(_undocumented_tests(TESTS) - TESTS_ALLOWED) == []


def test_the_tests_allowlist_holds_exactly_the_modules_still_without_one():
    assert _undocumented_tests(TESTS) & TESTS_ALLOWED == TESTS_ALLOWED


def test_a_module_without_a_docstring_is_caught_and_an_empty_init_is_not(
        tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "bare.py").write_text("x = 1\n")
    (tmp_path / "told.py").write_text('"""What this is for."""\nx = 1\n')
    (tmp_path / "empty_doc.py").write_text('""""""\nx = 1\n')
    assert _undocumented(tmp_path) == {"bare.py", "empty_doc.py"}


def test_only_top_level_test_files_count_in_the_tests_tree(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "test_nested.py").write_text("x = 1\n")
    (tmp_path / "conftest.py").write_text("x = 1\n")
    (tmp_path / "test_bare.py").write_text("x = 1\n")
    (tmp_path / "test_told.py").write_text('"""Why."""\nx = 1\n')
    assert _undocumented_tests(tmp_path) == {"test_bare.py"}
