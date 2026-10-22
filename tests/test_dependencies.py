"""Holiday F-182: the declared dependencies and the imports agree both ways.

In holiday F-103's shape (``tests/test_config_example.py``, the file and the
code agree both ways): every distribution ``pyproject.toml`` declares is
imported somewhere, and every third-party name the code imports is declared.
Before this rail nothing read ``[project].dependencies`` against the code.

Two allowlists hold the exceptions, each to exactly its entries in F-69's
shape (``tests/test_noqa_reasons.py``), so a stale entry fails as a new gap
does. ``ENGINES`` are declared packages loaded by a name string, never by an
``import``. ``TRANSITIVE`` are imported names that ride on a declared package
(checked against ``uv.lock``, 2026-10-22); declaring them outright would move
``uv.lock``, which is Anu's call (F-182's ruling, default no).

The runtime set is read against ``src/gaffer/`` and ``scripts/`` (outside the
archive), the dev group against ``tests/``.
"""
from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Distribution name to import name, where the two differ.
IMPORT_NAME = {"scikit-learn": "sklearn", "tomli-w": "tomli_w"}

# Declared, never imported by name. Value: what loads it.
ENGINES = {
    "pyarrow": "pandas' parquet engine, read_parquet/to_parquet",
    "highspy": "PuLP's HiGHS solver, chosen by a solver name string",
}

# Imported, not declared. Value: the declared package it rides on.
TRANSITIVE = {
    "numpy": "pandas",
    "joblib": "scikit-learn",
    "pydantic": "fastapi",
    "starlette": "fastapi",
    "scipy": "scikit-learn",
}

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _imports_of(spec: str) -> str:
    dist = _NAME.match(spec.strip()).group(0).lower()
    return IMPORT_NAME.get(dist, dist.replace("-", "_"))


def _first_party() -> set[str]:
    # The scripts and the tests import each other's modules by stem (a
    # sys.path edit), and the suite imports its helpers through ``tests``.
    stems = {p.stem for p in (ROOT / "scripts").glob("*.py")}
    return stems | {"gaffer", "scripts", "tests"}


def _imported(*trees: str) -> dict[str, set[str]]:
    """Top-level third-party names imported under ``trees``, with the files."""
    skip = set(sys.stdlib_module_names) | _first_party()
    found: dict[str, set[str]] = {}
    for tree in trees:
        for path in sorted((ROOT / tree).rglob("*.py")):
            rel = path.relative_to(ROOT)
            if "archive" in rel.parts:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module]
                else:
                    continue
                for name in names:
                    top = name.split(".")[0]
                    if top not in skip:
                        found.setdefault(top, set()).add(rel.as_posix())
    return found


def _runtime() -> set[str]:
    return {_imports_of(s) for s in _pyproject()["project"]["dependencies"]}


def _dev() -> set[str]:
    return {_imports_of(s) for s in _pyproject()["dependency-groups"]["dev"]}


def test_every_declared_runtime_dependency_is_imported_or_an_engine():
    used = _imported("src/gaffer", "scripts")
    unused = sorted(_runtime() - set(used) - set(ENGINES))
    assert unused == []


def test_every_third_party_import_in_the_code_is_declared_or_transitive():
    used = _imported("src/gaffer", "scripts")
    undeclared = {n: sorted(f) for n, f in used.items() if n not in _runtime() | set(TRANSITIVE)}
    assert undeclared == {}


def test_every_dev_dependency_is_imported_by_the_suite():
    unused = sorted(_dev() - set(_imported("tests")))
    assert unused == []


def test_every_third_party_import_in_the_suite_is_declared_or_transitive():
    known = _runtime() | _dev() | set(TRANSITIVE)
    undeclared = {n: sorted(f) for n, f in _imported("tests").items() if n not in known}
    assert undeclared == {}


def test_each_engine_is_declared_and_never_imported():
    assert set(ENGINES) <= _runtime()
    assert set(ENGINES) & set(_imported("src/gaffer", "scripts", "tests")) == set()


def test_each_transitive_name_is_imported_undeclared_and_rides_on_a_declared_package():
    used = set(_imported("src/gaffer", "scripts")) | set(_imported("tests"))
    assert set(TRANSITIVE) <= used
    assert set(TRANSITIVE) & (_runtime() | _dev()) == set()
    declared = {_NAME.match(s).group(0).lower() for s in _pyproject()["project"]["dependencies"]}
    assert set(TRANSITIVE.values()) <= declared


def test_the_transitive_names_ride_on_their_package_in_the_lock():
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    deps = {p["name"]: {d["name"] for d in p.get("dependencies", [])} for p in lock["package"]}
    missing = {n: on for n, on in TRANSITIVE.items() if n not in deps.get(on, set())}
    assert missing == {}
