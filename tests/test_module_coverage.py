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

Holiday F-174 asks the same of ``scripts/``: every live script (F-87's
``_live_scripts()``: not the archive, not a plist) is named by its file name
in some ``tests/test_*.py``, or imported there by its bare stem
(``import v7b_composite``, the form ``tests/test_v7b_composite.py`` uses). The
two unnamed on 2026-10-22 sit on ``SCRIPTS_ALLOWED``, F-170's shape: it can
only shrink, and F-175 empties it. The package counted three, but
``v7b_legacy_minutes.py`` is imported by stem in ``tests/test_v7b_driver.py``.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from tests.test_guide_scripts import _live_scripts

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "gaffer"
SKIPPED_DIRS = (("web", "routers"),)

# Path under ``src/gaffer/`` to the reason no test names it. Empty on landing.
ALLOWED: dict[str, str] = {}

# F-174: the live scripts no test names yet; F-175 gives each a test.
SCRIPTS_ALLOWED = {
    "eval_milestone.py",  # the milestone evaluation
    "replay_pair.sh",  # the bash driver that runs an arm against its control
}


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


def _unnamed_scripts(scripts: list[Path], tests: Path, skip: Path | None = None) -> list[str]:
    """F-174: file names of ``scripts`` no ``tests/test_*.py`` names or imports."""
    texts, imported = [], set()
    for path in sorted(tests.glob("test_*.py")):
        if skip is not None and path.resolve() == skip.resolve():
            continue
        text = path.read_text(encoding="utf-8")
        texts.append(text)
        for node in ast.walk(ast.parse(text, filename=str(path))):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module)
    text = "\n".join(texts)
    # Behind a word boundary, so `v7b_probe.py` does not name a `probe.py`.
    return [
        p.name for p in scripts
        if p.stem not in imported
        and not re.search(r"(?<![\w])" + re.escape(p.name), text)
    ]


def test_every_live_script_outside_the_allowlist_is_named_by_a_test():
    stray = [s for s in _unnamed_scripts(_live_scripts(), ROOT / "tests", Path(__file__))
             if s not in SCRIPTS_ALLOWED]
    assert stray == []


def test_every_allowlisted_script_still_needs_its_entry():
    unnamed = set(_unnamed_scripts(_live_scripts(), ROOT / "tests", Path(__file__)))
    assert sorted(SCRIPTS_ALLOWED - unnamed) == []


def test_a_script_nobody_names_is_caught_and_a_name_or_bare_import_names_one(tmp_path):
    scripts = [tmp_path / n for n in ("probe.py", "v7b_probe.py", "head.py", "pair.sh")]
    tdir = tmp_path / "tests"
    tdir.mkdir()
    (tdir / "test_a.py").write_text(
        '"""Runs scripts/v7b_probe.py and scripts/pair.sh."""\nimport head\n',
        encoding="utf-8",
    )
    (tdir / "helper.py").write_text('"""probe.py"""\n', encoding="utf-8")
    assert _unnamed_scripts(scripts, tdir) == ["probe.py"]
