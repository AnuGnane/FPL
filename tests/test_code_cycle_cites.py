"""Every cycle a comment or docstring under ``src/gaffer/`` or ``scripts/``
cites is one the ROADMAP ships or a spec names (holiday F-149).

``CLAUDE.md`` "Writing style": comments and docstrings cite the cycle and
section that introduced a rule (``v16 §4``), so a reader can find the
decision. A mistyped cycle points at nothing. F-140's ``shipped()``
(``tests/test_guide_history.py``) reads the ROADMAP's "## Shipped" headings;
a cite resolves by its exact cycle or by its bare major (``v4c`` from a
``v4`` heading, ``v12 W3`` from ``v12``), a bare major resolves when any
lettered cycle of it ships (``v4`` from ``v4a``), and v20, open and not yet
shipped, resolves through the spec filenames under ``docs/superpowers/specs/``
(``-v20-``). Only COMMENT tokens and ``ast`` docstrings are read, so a string
literal in code is not.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

from tests.test_guide_history import ROADMAP, shipped

_ROOT = Path(__file__).resolve().parents[1]
SPECS = _ROOT / "docs/superpowers/specs"
_CITE = re.compile(r"\bv(\d+)([a-z]?)(?: W[1-5])?\b")
_SPEC = re.compile(r"-v(\d+)([a-z]?)-")


def known() -> set[str]:
    """The shipped cycles and the cycles a spec filename names."""
    specs = {f"v{m[1]}{m[2]}" for p in SPECS.glob("*.md")
             for m in _SPEC.finditer(p.name)}
    return shipped(ROADMAP.read_text(encoding="utf-8")) | specs


def resolves(major: str, letter: str, have: set[str]) -> bool:
    if f"v{major}{letter}" in have or f"v{major}" in have:
        return True
    return not letter and any(re.fullmatch(rf"v{major}[a-z]", h) for h in have)


def _texts(path: Path):
    """``(line, text)`` for each comment and docstring in ``path``."""
    source = path.read_text(encoding="utf-8")
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT:
            yield tok.start[0], tok.string
    for node in ast.walk(ast.parse(source, filename=str(path))):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                first = body[0].lineno
                for i, line in enumerate(body[0].value.value.splitlines()):
                    yield first + i, line


def unresolved(paths, have: set[str]) -> list[str]:
    out = []
    for path in paths:
        for line, text in _texts(path):
            for m in _CITE.finditer(text):
                if not resolves(m[1], m[2], have):
                    rel = path.relative_to(_ROOT) if path.is_relative_to(
                        _ROOT) else path
                    out.append(f"{rel}:{line} {m[0]}")
    return out


def _sources():
    return sorted([*(_ROOT / "src/gaffer").rglob("*.py"),
                   *(_ROOT / "scripts").glob("*.py")])


def test_every_cycle_a_comment_cites_is_shipped_or_named_by_a_spec():
    assert unresolved(_sources(), known()) == []


def test_a_bare_major_and_a_workstream_resolve_through_their_cycle():
    have = {"v4a", "v8", "v12"}
    assert resolves("4", "", have)
    assert resolves("8", "g", have)
    assert resolves("12", "", have)
    assert not resolves("4", "e", have)


def test_the_rail_bites_on_a_cycle_nobody_ships(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text('"""Cites v16 §4."""\n# per v99 §1\nX = "v98 §2"\n')
    assert unresolved([sample], known()) == [f"{sample}:2 v99"]
