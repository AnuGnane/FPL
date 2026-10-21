"""Holiday F-165: every module under ``src/gaffer/`` is named by a test.

ROADMAP candidate 7 (housekeeping), F-153's question (``kit/coverage.test.ts``)
asked of the Python package. On 2026-10-21 F-164 gave the last two unnamed
modules (``models/modes.py`` and ``optimize/formation.py``, both cut out in
v18d §2 and reached only through their callers) tests of their own; this rail
keeps a new leaf module from landing the same way.

A module is named when some ``tests/*.py`` other than this file carries its
dotted path (``gaffer.models.modes``, not as the head of a longer name such
as ``gaffer.models.modes_extra``) or imports it as
``from gaffer.<pkg> import <module>`` (the form ``tests/test_v12_actuals.py``
uses for ``availability_eval``). ``web/routers/`` is skipped: F-157's
``tests/test_route_models.py`` and the ``tests/test_web_*.py`` files reach
those through the app. ``__init__.py`` is skipped as a package, not a module.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "gaffer"
SKIPPED_DIRS = (("web", "routers"),)

# Path under ``src/gaffer/`` to the reason no test names it. Empty on landing.
ALLOWED: dict[str, str] = {}


def _modules(package: Path) -> dict[str, str]:
    """Each module's path under ``package`` to its dotted name."""
    out = {}
    for path in sorted(package.rglob("*.py")):
        rel = path.relative_to(package)
        if path.name == "__init__.py":
            continue
        if any(rel.parts[:len(d)] == d for d in SKIPPED_DIRS):
            continue
        out[rel.as_posix()] = ".".join((package.name, *rel.with_suffix("").parts))
    return out


def _named(tests: Path, skip: Path | None = None) -> tuple[str, set[str]]:
    """Every test file's text, and the dotted names its ``from`` imports bind."""
    texts, imported = [], set()
    for path in sorted(tests.glob("*.py")):
        if skip is not None and path.resolve() == skip.resolve():
            continue
        text = path.read_text(encoding="utf-8")
        texts.append(text)
        for node in ast.walk(ast.parse(text, filename=str(path))):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.update(f"{node.module}.{a.name}" for a in node.names)
    return "\n".join(texts), imported


def _unnamed(package: Path, tests: Path, skip: Path | None = None) -> list[str]:
    text, imported = _named(tests, skip)
    return [
        rel for rel, dotted in _modules(package).items()
        if dotted not in imported
        and not re.search(re.escape(dotted) + r"(?![\w])", text)
    ]


def test_every_module_outside_the_allowlist_is_named_by_a_test():
    stray = [m for m in _unnamed(PACKAGE, ROOT / "tests", Path(__file__))
             if m not in ALLOWED]
    assert stray == []


def test_every_allowlisted_module_still_needs_its_entry():
    unnamed = set(_unnamed(PACKAGE, ROOT / "tests", Path(__file__)))
    assert [m for m in ALLOWED if m not in unnamed] == []


def _tree(tmp_path: Path, tests: dict[str, str]) -> tuple[Path, Path]:
    pkg = tmp_path / "src" / "gaffer"
    for rel in ("__init__.py", "models/__init__.py", "models/modes.py",
                "models/modes_extra.py", "web/routers/players.py", "top.py"):
        (pkg / rel).parent.mkdir(parents=True, exist_ok=True)
        (pkg / rel).write_text("", encoding="utf-8")
    tdir = tmp_path / "tests"
    tdir.mkdir()
    for name, body in tests.items():
        (tdir / name).write_text(body, encoding="utf-8")
    return pkg, tdir


def test_a_module_nobody_names_is_caught_and_routers_and_inits_are_not(tmp_path):
    pkg, tdir = _tree(tmp_path, {"test_a.py": "from gaffer import top\n"})
    assert _unnamed(pkg, tdir) == ["models/modes.py", "models/modes_extra.py"]


def test_a_longer_name_does_not_stand_in_for_its_prefix(tmp_path):
    pkg, tdir = _tree(tmp_path, {
        "test_a.py": "import gaffer.top\nimport gaffer.models.modes_extra\n",
    })
    assert _unnamed(pkg, tdir) == ["models/modes.py"]


def test_a_dotted_path_and_a_from_import_both_name_a_module(tmp_path):
    pkg, tdir = _tree(tmp_path, {
        "test_a.py": "from gaffer.models.modes import DNP\n",
        "test_b.py": "from gaffer.models import (\n    modes_extra,\n)\n"
                     "from gaffer import top\n",
    })
    assert _unnamed(pkg, tdir) == []
