"""The three layering rails v18d bought, and the planted faults that prove
they can still fail (v18d §1 gate item 3).

What group A and group B established, and what these hold:

1. The core does not import the web layer. Only ``gaffer/cli.py`` and
   ``gaffer/mcp_server.py`` may name ``gaffer.web``, because they *are* the
   web layer's callers — the ruling is recorded in the v18d spec. Anything
   else importing it, at module top or from inside a function, is the tool
   depending on FastAPI to compute a transfer.
2. The top-level import graph is acyclic. A cycle is what makes a
   function-body import look necessary in the first place.
3. The seven function-body imports that existed only to dodge a cycle stay
   gone, and the three private names other modules reached across a module
   boundary for stay unreachable — ``formation_legal`` now lives in
   ``optimize/formation.py``, ``code_for`` in ``data/match_odds.py`` and
   ``cap`` in ``config.py``, each public where it sits.

Every rail is a function over a root directory, so each one runs twice: once
over the real ``src/`` and once over a tree planted under ``tmp_path`` with
exactly the fault it is meant to catch. A rail that scanned nothing would pass
its real-tree assertion silently forever; the planted half is what stops that.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"

SURFACES = {"gaffer/cli.py", "gaffer/mcp_server.py"}
"""The two modules allowed to import ``gaffer.web`` (v18d §1)."""

LAZY_EDGES = [
    ("gaffer/inputs.py", "gaffer.advise"),
    ("gaffer/snapshot.py", "gaffer.advise"),
    ("gaffer/config.py", "gaffer.price_timing"),
    ("gaffer/served.py", "gaffer.price_timing"),
    ("gaffer/artifacts.py", "gaffer.overrides"),
    ("gaffer/optimize/chip_policy.py", "gaffer.optimize.chips"),
    ("gaffer/models/dnp_calibrate.py", "gaffer.models.minutes"),
]
"""The seven cycle-dodging function-body imports group B hoisted."""

PRIVATE_REACHES = [
    ("gaffer.backtest", "_formation_legal"),
    ("gaffer.match_odds", "_code_for"),
    ("gaffer.data.match_odds", "_code_for"),
    ("gaffer.advise", "_cap"),
]
"""The private names that used to be imported across a module boundary."""


def _modules(root: Path) -> list[tuple[str, Path]]:
    """``(posix path relative to root, path)`` for every module under
    ``root/gaffer``, sorted so a failure reads the same way twice."""
    pkg = root / "gaffer"
    return sorted(((p.relative_to(root).as_posix(), p)
                   for p in pkg.rglob("*.py")), key=lambda pair: pair[0])


def _module_name(rel: str) -> str:
    name = "gaffer." + ".".join(Path(rel).with_suffix("").parts[1:])
    return name[:-9] if name.endswith(".__init__") else name.rstrip(".")


def _imported(node: ast.AST) -> list[str]:
    """The ``gaffer.*`` names one import statement names, dotted."""
    if isinstance(node, ast.Import):
        return [a.name for a in node.names if a.name.startswith("gaffer")]
    if isinstance(node, ast.ImportFrom) and node.module:
        if not node.module.startswith("gaffer"):
            return []
        return [node.module] + [f"{node.module}.{a.name}" for a in node.names]
    return []


def web_imports_outside_web(root: Path) -> list[str]:
    """Modules outside ``gaffer/web/`` that import it, surfaces excepted.

    The whole AST is walked, not just ``tree.body``: an import hidden in a
    function body is the same dependency, only harder to see.
    """
    found = []
    for rel, path in _modules(root):
        if rel.startswith("gaffer/web/") or rel in SURFACES:
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if any(name == "gaffer.web" or name.startswith("gaffer.web.")
                   for name in _imported(node)):
                found.append(rel)
                break
    return found


def _top_level_graph(root: Path) -> dict[str, set[str]]:
    """Module -> the modules it imports at its own top level.

    ``tree.body`` only, so an ``if TYPE_CHECKING:`` block is ignored by
    construction: it is not a module-top statement and it does not run.
    """
    mods = {_module_name(rel): path for rel, path in _modules(root)}
    graph: dict[str, set[str]] = {}
    for name, path in mods.items():
        edges = set()
        for node in ast.parse(path.read_text()).body:
            for target in _imported(node):
                if target in mods:
                    edges.add(target)
        graph[name] = edges
    return graph


def top_level_cycles(root: Path) -> list[tuple[str, str]]:
    """Top-level edges ``(a, b)`` where ``b`` reaches back to ``a``."""
    graph = _top_level_graph(root)

    def reaches(start: str, goal: str) -> bool:
        seen, stack = set(), [start]
        while stack:
            here = stack.pop()
            if here == goal:
                return True
            if here in seen:
                continue
            seen.add(here)
            stack.extend(graph.get(here, ()))
        return False

    return sorted((a, b) for a, edges in graph.items() for b in edges
                  if reaches(b, a))


def _nested_imports(tree: ast.AST) -> list[str]:
    """Every ``gaffer.*`` name imported from inside a function or class."""
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, (ast.Import, ast.ImportFrom)):
                out.extend(_imported(inner))
    return out


def absent_lazy_imports(root: Path,
                        edges: list[tuple[str, str]]) -> list[str]:
    """Pairs from ``edges`` whose function-body import has come back."""
    by_rel = dict(_modules(root))
    found = []
    for rel, target in edges:
        path = by_rel.get(rel)
        if path is None:
            continue
        names = _nested_imports(ast.parse(path.read_text()))
        if any(name == target or name.startswith(f"{target}.")
               for name in names):
            found.append(f"{rel} imports {target} in a body")
    return found


def private_reaches(root: Path,
                    names: list[tuple[str, str]]) -> list[str]:
    """Any module importing one of the named private names from another."""
    found = []
    for rel, path in _modules(root):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            for module, private in names:
                if node.module != module:
                    continue
                if any(a.name == private for a in node.names):
                    found.append(f"{rel} imports {module}.{private}")
    return found


def _plant(root: Path, files: dict[str, str]) -> Path:
    """Write a fake ``gaffer`` package under ``root`` and return ``root``."""
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def test_nothing_outside_the_web_layer_imports_the_web_layer():
    assert web_imports_outside_web(SRC) == []


def test_a_core_module_reaching_into_the_web_layer_is_reported(tmp_path):
    root = _plant(tmp_path, {
        "gaffer/__init__.py": "",
        "gaffer/web/__init__.py": "",
        "gaffer/web/x.py": "y = 1\n",
        "gaffer/core.py": "def f():\n    from gaffer.web.x import y\n"
                          "    return y\n",
        "gaffer/cli.py": "from gaffer.web.x import y\n",
    })
    assert web_imports_outside_web(root) == ["gaffer/core.py"]


def test_the_top_level_import_graph_has_no_cycles():
    assert top_level_cycles(SRC) == []


def test_a_planted_pair_of_mutual_top_level_imports_is_reported(tmp_path):
    root = _plant(tmp_path, {
        "gaffer/__init__.py": "",
        "gaffer/a.py": "import gaffer.b\n",
        "gaffer/b.py": "import gaffer.a\n",
    })
    cycles = top_level_cycles(root)
    assert cycles
    named = {name for edge in cycles for name in edge}
    assert {"gaffer.a", "gaffer.b"} <= named


def test_the_seven_cycle_dodging_body_imports_stay_gone():
    assert absent_lazy_imports(SRC, LAZY_EDGES) == []


def test_a_replanted_body_import_of_advise_is_reported(tmp_path):
    root = _plant(tmp_path, {
        "gaffer/__init__.py": "",
        "gaffer/advise.py": "x = 1\n",
        "gaffer/inputs.py": "def f():\n    from gaffer.advise import x\n"
                            "    return x\n",
    })
    assert absent_lazy_imports(root, LAZY_EDGES) == [
        "gaffer/inputs.py imports gaffer.advise in a body"]


def test_the_three_private_names_are_never_reached_for_again():
    assert private_reaches(SRC, PRIVATE_REACHES) == []


def test_a_replanted_reach_for_a_private_backtest_name_is_reported(tmp_path):
    root = _plant(tmp_path, {
        "gaffer/__init__.py": "",
        "gaffer/backtest.py": "def _formation_legal(p):\n    return True\n",
        "gaffer/optimize.py": "from gaffer.backtest import _formation_legal\n",
    })
    assert private_reaches(root, PRIVATE_REACHES) == [
        "gaffer/optimize.py imports gaffer.backtest._formation_legal"]


def test_every_rail_actually_scanned_the_real_tree():
    """The rails above assert on empty lists, which an empty scan also
    satisfies; this is what says the scan found the repo."""
    rels = [rel for rel, _ in _modules(SRC)]
    assert len(rels) > 50
    assert "gaffer/advise.py" in rels
    assert any(rel.startswith("gaffer/web/routers/") for rel in rels)
    assert len(_top_level_graph(SRC)) == len(rels)
