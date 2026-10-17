"""``config.example.toml`` names every key ``load_config`` reads (holiday F-103).

ROADMAP candidate 7, in F-87's shape (``tests/test_guide_scripts.py``): the
example lacked eight of the keys the loader reads, so a fresh clone's copy did
not say they existed. The pairs come from parsing ``load_config`` with ``ast``:
each ``<name> = raw.get("<section>", {})`` binding and its
``<name>.get("<key>", ...)`` reads, the chained
``raw.get("<section>", {}).get("<key>")`` form (``[understat] enabled``,
``[model] xg_per_shot``) and ``raw["fpl"]["<key>"]``.

``[optimizer]`` and ``[data]`` are out of the walk: both are spread with
``**`` straight into ``Config(...)``, so their keys are the dataclass's field
names and no ``.get`` names them; this rail does not guess them. Membership
only, no count: ``Config`` stays pinned in ``tests/test_v13_degradation.py``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

CONFIG = Path("src/gaffer/config.py")
EXAMPLE = Path("config.example.toml")


def _str(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(
        node.value, str) else None


def _section_of(node: ast.AST) -> str | None:
    # raw.get("<section>", ...) or raw["<section>"]
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get" and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "raw" and node.args):
        return _str(node.args[0])
    if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
            and node.value.id == "raw"):
        return _str(node.slice)
    return None


def _read_pairs() -> set[tuple[str, str]]:
    tree = ast.parse(CONFIG.read_text())
    loader = next(node for node in tree.body
                  if isinstance(node, ast.FunctionDef)
                  and node.name == "load_config")
    bound: dict[str, str] = {}
    for node in ast.walk(loader):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            section = _section_of(node.value)
            if section is not None:
                bound[node.targets[0].id] = section
    pairs: set[tuple[str, str]] = set()
    for node in ast.walk(loader):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get" and node.args):
            key, owner = _str(node.args[0]), node.func.value
            if key is None:
                continue
            if isinstance(owner, ast.Name) and owner.id in bound:
                pairs.add((bound[owner.id], key))
            elif (section := _section_of(owner)) is not None:
                pairs.add((section, key))
        elif isinstance(node, ast.Subscript):
            key, section = _str(node.slice), _section_of(node.value)
            if key is not None and section is not None:
                pairs.add((section, key))
    return pairs


def _missing(pairs: set[tuple[str, str]], text: str) -> list[tuple[str, str]]:
    sections: dict[str, str] = {}
    for block in re.split(r"(?m)^(?=\[)", text):
        head = re.match(r"\[([a-z_]+)\]", block)
        if head:
            sections[head.group(1)] = block
    return sorted(
        (section, key) for section, key in pairs
        if not re.search(rf"(?m)^(# )?{re.escape(key)} =",
                         sections.get(section, "")))


def test_the_walk_finds_the_keys_this_rail_reads():
    pairs = _read_pairs()
    assert ("fpl", "entry_id") in pairs, pairs
    assert ("understat", "enabled") in pairs, pairs
    assert ("league", "focus") in pairs and ("web", "token") in pairs, pairs
    assert not any(section in ("optimizer", "data") for section, _ in pairs)


def test_every_key_load_config_reads_is_in_the_example():
    assert _missing(_read_pairs(), EXAMPLE.read_text()) == []


def test_an_example_missing_one_key_line_fails_the_rail():
    text = EXAMPLE.read_text()
    line = next(row for row in text.splitlines()
                if re.match(r"(# )?irreversible_threshold =", row))
    assert _missing(_read_pairs(), text.replace(line + "\n", "")) == [
        ("scenarios", "irreversible_threshold")]
