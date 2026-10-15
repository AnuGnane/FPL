"""Holiday F-69: every broad ``except`` says what it swallows and why.

v19h §1's rule (``CLAUDE.md``, "Writing style"): an ``except Exception:``
carries ``# noqa: BLE001 — <what is swallowed and why that is safe here>``,
and a bare ``noqa`` with no reason is not accepted. F-67, F-68 and F-69 gave
every site under ``src/`` and ``scripts/`` its reason except the files F-68
put out of scope by name; this rail keeps it that way.

The allowlist pins the count each of those files holds today, so a new bare
mark there fails too, and a fixed one fails until its count comes down here.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TREES = ("src", "scripts")

# F-68's out-of-scope files: orchestrator-only (advise, web/jobs) or the golden
# gate's modules (artifacts, brief, pipeline, served), each a needs-mac package
# of its own when Anu is back. Value: the reasonless broad excepts held today.
ALLOWED = {
    "src/gaffer/advise.py": 1,
    "src/gaffer/web/jobs.py": 1,
    "src/gaffer/artifacts.py": 1,
    "src/gaffer/brief.py": 6,
    "src/gaffer/pipeline.py": 1,
    "src/gaffer/served.py": 1,
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
