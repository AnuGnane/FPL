"""Holiday F-69: every broad ``except`` says what it swallows and why.

v19h §1's rule (``CLAUDE.md``, "Writing style"): an ``except Exception:``
carries ``# noqa: BLE001 — <what is swallowed and why that is safe here>``,
and a bare ``noqa`` with no reason is not accepted. F-67, F-68 and F-69 gave
every site under ``src/`` and ``scripts/`` its reason except the files F-68
put out of scope by name; this rail keeps it that way.

The allowlist pins the count each of those files holds today, so a new bare
mark there fails too, and a fixed one fails until its count comes down here.

Holiday F-78 widened the rule from BLE001 to every code: each ``# noqa: <code>``
under ``src/``, ``scripts/`` and ``tests/`` gives its reason after `` — ``,
except ``E402`` (a ``sys.path`` edit before the import, evident) and ``F401``
on a line of an ``import`` statement (a re-export, evident). A combined mark
is split on commas and each code judged alone. BLE001 stays with the rail
above, whose allowlist already holds the orchestrator-only files.
"""
from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TREES = ("src", "scripts")

# F-68's out-of-scope files that remain: orchestrator-only (advise, web/jobs).
# F-77 gave the golden gate's modules (artifacts, brief, pipeline, served)
# their reasons and struck them. Value: the reasonless broad excepts held today.
ALLOWED = {
    "src/gaffer/advise.py": 1,
    "src/gaffer/web/jobs.py": 1,
}

BROAD = {"Exception", "BaseException"}
REASONED = re.compile(r"#\s*noqa: BLE001 — \S")


def _names(node: ast.expr | None) -> set[str]:
    if node is None:
        return set()
    if isinstance(node, ast.Tuple):
        return set().union(*(_names(e) for e in node.elts))
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Attribute):
        return {node.attr}
    return set()


def _reasonless(path: Path) -> list[int]:
    """Line numbers of broad handlers whose ``except`` line gives no reason."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    out = []
    for node in ast.walk(ast.parse(text, filename=str(path))):
        if isinstance(node, ast.ExceptHandler) and _names(node.type) & BROAD:
            if not REASONED.search(lines[node.lineno - 1]):
                out.append(node.lineno)
    return out


def _census() -> dict[str, list[int]]:
    found = {}
    for tree in TREES:
        for path in sorted((ROOT / tree).rglob("*.py")):
            bad = _reasonless(path)
            if bad:
                found[path.relative_to(ROOT).as_posix()] = bad
    return found


def test_every_broad_except_outside_the_allowlist_gives_its_reason():
    stray = {f: lines for f, lines in _census().items() if f not in ALLOWED}
    assert stray == {}


def test_each_allowlisted_file_holds_exactly_the_count_it_held_at_f69():
    counts = {f: len(_census().get(f, [])) for f in ALLOWED}
    assert counts == ALLOWED


def test_the_allowlist_names_only_files_that_exist():
    assert [f for f in ALLOWED if not (ROOT / f).is_file()] == []


def test_a_bare_mark_is_caught_and_a_reasoned_one_is_not(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text(
        "try:\n    pass\nexcept Exception:  # noqa: BLE001\n    pass\n"
        "try:\n    pass\nexcept (ValueError, BaseException):\n    pass\n"
        "try:\n    pass\nexcept Exception:  # noqa: BLE001 — a reason\n    pass\n"
        "try:\n    pass\nexcept Exception:  # noqa: BLE001 — \n    pass\n"
        "try:\n    pass\nexcept OSError:\n    pass\n",
        encoding="utf-8",
    )
    assert _reasonless(sample) == [3, 7, 15]


# --- F-78: every code, not BLE001 alone ------------------------------------

CODE_TREES = ("src", "scripts", "tests")
MARK = re.compile(r"#\s*noqa:\s*([A-Z]+\d+(?:\s*,\s*[A-Z]+\d+)*)(.*)")
REASON = re.compile(r"^\s*— \S")

# F-78's bare mark it may not fix: ``test_v12_w3_degradation.py`` is
# orchestrator-only (F-77 turned ``served.py``'s lambda into a def and struck
# it). Value: the reasonless marks each file holds.
CODE_ALLOWED = {
    "tests/test_v12_w3_degradation.py": 1,  # E731, the stale lambda
}


def _import_lines(tree: ast.AST) -> set[int]:
    return {
        line
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for line in range(node.lineno, (node.end_lineno or node.lineno) + 1)
    }


def _bare_marks(path: Path) -> list[tuple[int, str]]:
    """``(line, code)`` for each noqa code that needs a reason and has none."""
    text = path.read_text(encoding="utf-8")
    imports = _import_lines(ast.parse(text, filename=str(path)))
    out = []
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type != tokenize.COMMENT:
            continue
        mark = MARK.search(tok.string)
        if not mark or REASON.match(mark.group(2)):
            continue
        line = tok.start[0]
        for code in (c.strip() for c in mark.group(1).split(",")):
            if code in ("E402", "BLE001"):
                continue
            if code == "F401" and line in imports:
                continue
            out.append((line, code))
    return out


def _code_census() -> dict[str, list[tuple[int, str]]]:
    found = {}
    for tree in CODE_TREES:
        for path in sorted((ROOT / tree).rglob("*.py")):
            bad = _bare_marks(path)
            if bad:
                found[path.relative_to(ROOT).as_posix()] = bad
    return found


def test_every_noqa_code_outside_the_allowlist_gives_its_reason():
    stray = {f: marks for f, marks in _code_census().items() if f not in CODE_ALLOWED}
    assert stray == {}


def test_each_file_on_the_code_allowlist_holds_exactly_its_count():
    census = _code_census()
    counts = {f: len(census.get(f, [])) for f in CODE_ALLOWED}
    gone = [f for f, n in counts.items() if n == 0]
    assert counts == CODE_ALLOWED, (
        f"strike {gone} from CODE_ALLOWED: its bare marks are gone" if gone
        else "a bare noqa mark was added or fixed in an allowlisted file"
    )


def test_the_code_allowlist_names_only_files_that_exist():
    assert [f for f in CODE_ALLOWED if not (ROOT / f).is_file()] == []


def test_e402_and_f401_on_an_import_pass_bare_and_other_codes_do_not(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text(
        "import os  # noqa: E402,F401\n"
        "from os import (  # noqa: F401\n"
        "    path,  # noqa: F401\n"
        ")\n"
        "f = lambda: 1  # noqa: E731\n"
        "g = lambda: 2  # noqa: E731 — a reason\n"
        "x = 1  # noqa: F401\n"
        "s = '# noqa: E731'\n"
        "y = 2  # noqa: E731, F811\n",
        encoding="utf-8",
    )
    assert _bare_marks(sample) == [(5, "E731"), (7, "F401"), (9, "E731"), (9, "F811")]
