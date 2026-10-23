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

Holiday F-193 asks it of functions: every public top-level ``def`` (and
``async def``) under ``src/gaffer/`` has a docstring. ``FUNCTIONS_ALLOWED``
maps each file to the number still without one on 2026-10-22, held exactly in
F-69's shape, so it can only shrink; F-194 and F-200 write the docstrings.

Holiday F-196 asks it of classes: every public top-level ``class`` under
``src/gaffer/`` has a docstring. ``CLASSES_ALLOWED`` maps each file to the
number still without one on 2026-10-23, held exactly in the same shape; F-197
and F-198 write them off the golden path, F-200 the golden ones, and the
orchestrator-only files stay on it for good.

Holiday F-199 asks it of ``scripts/``: the same function walker over the top
level only (``scripts/archive/`` is retired code, F-167's ruff exclude), with
``SCRIPTS_FUNCTIONS_ALLOWED`` in F-69's shape. Its one entry is
``s2_replay.py``, orchestrator-only (``CLAUDE.md``), which stays for good.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "gaffer"

ALLOWED = {"config.py"}

TESTS = ROOT / "tests"

# F-170 and F-171: the test modules still without a docstring, now only the
# two orchestrator-only files, which are the orchestrator's to document.
TESTS_ALLOWED = {
    "test_odds.py",
    "test_web_jobs.py",
}

# F-193: per file, the public top-level functions still without a docstring.
# Since F-194 only two kinds are left. The golden modules (imported or patched
# by ``tests/test_golden_board.py`` and ``tests/test_pipeline.py``, so under
# HOLIDAY.md's Merging rule 2 their docstrings are a ``needs-mac`` part 3) and
# the orchestrator-only ``web/routers/whatif.py`` (``CLAUDE.md``), which stays.
FUNCTIONS_ALLOWED = {
    "artifacts.py": 7,             # golden
    "brief.py": 7,                 # golden
    "config.py": 1,                # golden
    "data/bootstrap.py": 4,        # golden (patched by test_pipeline.py)
    "ladder.py": 1,                # golden
    "report/render.py": 1,         # golden (patched by test_pipeline.py)
    "tracking.py": 1,              # golden (patched by test_pipeline.py)
    "web/routers/advice.py": 1,    # golden
    "web/routers/whatif.py": 2,    # orchestrator-only, for good
}

CLASSES_ALLOWED = {
    "advise.py": 1,                # orchestrator-only, for good
    "artifacts.py": 1,             # golden
    "config.py": 1,                # golden
    "optimize/milp.py": 3,         # orchestrator-only, for good
    "served.py": 2,                # golden
    "web/jobs.py": 1,              # orchestrator-only, for good
}

SCRIPTS = ROOT / "scripts"

# F-199: per top-level script, the public functions still without a docstring.
SCRIPTS_FUNCTIONS_ALLOWED = {
    "s2_replay.py": 2,             # orchestrator-only, for good
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
    out = set()
    for path in sorted(tree.glob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        if not ast.get_docstring(ast.parse(text, filename=str(path))):
            out.add(path.name)
    return out


def _undocumented_functions(tree: Path) -> dict[str, int]:
    """Per file under ``tree``, how many top-level functions whose name does
    not start with ``_`` have no (or an empty) docstring; files with none are
    left out."""
    out = {}
    for path in sorted(tree.rglob("*.py")):
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        bare = sum(
            1 for node in module.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not node.name.startswith("_")
            and not ast.get_docstring(node))
        if bare:
            out[path.relative_to(tree).as_posix()] = bare
    return out


def _undocumented_classes(tree: Path) -> dict[str, int]:
    """Per file under ``tree``, how many top-level classes whose name does not
    start with ``_`` have no (or an empty) docstring; files with none are left
    out."""
    out = {}
    for path in sorted(tree.rglob("*.py")):
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        bare = sum(
            1 for node in module.body
            if isinstance(node, ast.ClassDef)
            and not node.name.startswith("_")
            and not ast.get_docstring(node))
        if bare:
            out[path.relative_to(tree).as_posix()] = bare
    return out


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


def test_every_public_function_outside_the_allowlist_has_a_docstring():
    stray = {f: n for f, n in _undocumented_functions(PACKAGE).items()
             if n > FUNCTIONS_ALLOWED.get(f, 0)}
    assert stray == {}


def test_each_allowlisted_file_holds_exactly_its_undocumented_count():
    found = _undocumented_functions(PACKAGE)
    counts = {f: found.get(f, 0) for f in FUNCTIONS_ALLOWED}
    assert counts == FUNCTIONS_ALLOWED


def test_a_bare_public_function_is_caught_and_private_or_nested_ones_are_not(
        tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text(
        '"""Module."""\n'
        "def bare():\n    pass\n"
        "async def bare_async():\n    pass\n"
        'def empty():\n    """"""\n'
        'def told():\n    """Why."""\n'
        "def _private():\n    pass\n"
        'class C:\n    def method(self):\n        pass\n'
        'def outer():\n    """Why."""\n    def inner():\n        pass\n')
    (tmp_path / "clean.py").write_text('def told():\n    """Why."""\n')
    assert _undocumented_functions(tmp_path) == {"pkg/mod.py": 3}


def _undocumented_script_functions(tree: Path = SCRIPTS) -> dict[str, int]:
    """F-199: the function walker over ``scripts/``, top level only."""
    return {f: n for f, n in _undocumented_functions(tree).items()
            if "/" not in f}


def test_every_public_script_function_outside_the_allowlist_has_a_docstring():
    stray = {f: n for f, n in _undocumented_script_functions().items()
             if n > SCRIPTS_FUNCTIONS_ALLOWED.get(f, 0)}
    assert stray == {}


def test_each_scripts_allowlisted_file_holds_exactly_its_undocumented_count():
    found = _undocumented_script_functions()
    counts = {f: found.get(f, 0) for f in SCRIPTS_FUNCTIONS_ALLOWED}
    assert counts == SCRIPTS_FUNCTIONS_ALLOWED


def test_only_top_level_scripts_count_and_the_archive_does_not(tmp_path):
    (tmp_path / "archive").mkdir()
    (tmp_path / "archive" / "old.py").write_text("def bare():\n    pass\n")
    (tmp_path / "live.py").write_text("def bare():\n    pass\n")
    assert _undocumented_script_functions(tmp_path) == {"live.py": 1}


def test_every_public_class_outside_the_allowlist_has_a_docstring():
    stray = {f: n for f, n in _undocumented_classes(PACKAGE).items()
             if n > CLASSES_ALLOWED.get(f, 0)}
    assert stray == {}


def test_each_class_allowlisted_file_holds_exactly_its_undocumented_count():
    found = _undocumented_classes(PACKAGE)
    counts = {f: found.get(f, 0) for f in CLASSES_ALLOWED}
    assert counts == CLASSES_ALLOWED


def test_a_bare_public_class_is_caught_and_private_or_nested_ones_are_not(
        tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text(
        '"""Module."""\n'
        "class Bare:\n    pass\n"
        'class Empty:\n    """"""\n'
        'class Told:\n    """Why."""\n'
        "class _Private:\n    pass\n"
        'class Outer:\n    """Why."""\n    class Inner:\n        pass\n'
        "def bare():\n    pass\n")
    (tmp_path / "clean.py").write_text('class Told:\n    """Why."""\n')
    assert _undocumented_classes(tmp_path) == {"pkg/mod.py": 2}
