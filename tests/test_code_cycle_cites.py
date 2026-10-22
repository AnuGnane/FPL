"""Every cycle a comment or docstring under ``src/gaffer/``, ``scripts/``,
``tests/`` or ``frontend/src/`` cites is one the ROADMAP ships or a spec
names (holiday F-149; ``tests/`` and ``frontend/src/`` since F-178).

``CLAUDE.md`` "Writing style": comments and docstrings cite the cycle and
section that introduced a rule (``v16 §4``), so a reader can find the
decision. A mistyped cycle points at nothing. F-140's ``shipped()``
(``tests/test_guide_history.py``) reads the ROADMAP's "## Shipped" headings;
a cite resolves by its exact cycle or by its bare major (``v4c`` from a
``v4`` heading, ``v12 W3`` from ``v12``), a bare major resolves when any
lettered cycle of it ships (``v4`` from ``v4a``), and v20, open and not yet
shipped, resolves through the spec filenames under ``docs/superpowers/specs/``
(``-v20-``). Only COMMENT tokens and ``ast`` docstrings are read, so a string
literal in code is not. In ``.ts``/``.tsx`` the ``//`` and ``/* */`` comments
are read, string and template literals skipped (F-178), so a URL's ``//``
in a string does not open one.
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


def _ts_texts(path: Path):
    """``(line, text)`` for each ``//`` and ``/* */`` comment in ``path``.

    F-178: scanned a line at a time, skipping quoted and template strings,
    so a ``//`` inside a string is not read as a comment. A quote the scanner
    cannot see the end of (a regex literal like ``/"/g``, an apostrophe in
    JSX text) costs the rest of that line only, since TS strings bar a bare
    newline; a template literal spanning lines is read as code, which errs
    towards reading more, not less.
    """
    in_block = False
    for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(),
                              start=1):
        i, n = 0, len(line)
        if in_block:
            end = line.find("*/")
            if end < 0:
                yield no, line
                continue
            yield no, line[:end]
            in_block, i = False, end + 2
        while i < n:
            c = line[i]
            if c in "'\"`":
                i += 1
                while i < n and line[i] != c:
                    i += 2 if line[i] == "\\" else 1
                i += 1
            elif line.startswith("//", i):
                yield no, line[i:]
                break
            elif line.startswith("/*", i):
                end = line.find("*/", i + 2)
                if end < 0:
                    yield no, line[i:]
                    in_block = True
                    break
                yield no, line[i:end + 2]
                i = end + 2
            else:
                i += 1


def unresolved(paths, have: set[str]) -> list[str]:
    out = []
    for path in paths:
        texts = (_ts_texts(path) if path.suffix in (".ts", ".tsx")
                 else _texts(path))
        for line, text in texts:
            for m in _CITE.finditer(text):
                if not resolves(m[1], m[2], have):
                    rel = path.relative_to(_ROOT) if path.is_relative_to(
                        _ROOT) else path
                    out.append(f"{rel}:{line} {m[0]}")
    return out


def _sources():
    # F-178: the tests and the frontend cite cycles far more than the code.
    return sorted([*(_ROOT / "src/gaffer").rglob("*.py"),
                   *(_ROOT / "scripts").glob("*.py"),
                   *(_ROOT / "tests").glob("test_*.py"),
                   *(_ROOT / "frontend/src").rglob("*.ts"),
                   *(_ROOT / "frontend/src").rglob("*.tsx")])


def test_the_sources_reach_the_tests_and_the_frontend():
    roots = {p.relative_to(_ROOT).parts[0] for p in _sources()}
    assert roots == {"src", "scripts", "tests", "frontend"}, roots
    tsx = [p for p in _sources() if p.suffix == ".tsx"]
    assert tsx and sum(1 for p in tsx for _ in _ts_texts(p)) > 100


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


def test_the_rail_bites_on_a_ts_comment_and_skips_a_ts_string(tmp_path):
    sample = tmp_path / "sample.tsx"
    sample.write_text('// per v16 §4\nconst u = "http://x/v98";\n'
                      '/* v97\n   v99 §1 */\nconst t = `// v96`;\n'
                      "const r = s.replace(/\"/g, '')\n// v95\n")
    # The regex literal's quote costs its own line, never the comment after.
    assert unresolved([sample], known()) == [f"{sample}:3 v97",
                                             f"{sample}:4 v99",
                                             f"{sample}:7 v95"]
