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
import dataclasses
import re
import tomllib
from pathlib import Path

from gaffer.config import Config
from tests.test_readme_config import _FIELD as _README_FIELD

CONFIG = Path("src/gaffer/config.py")
EXAMPLE = Path("config.example.toml")


def _str(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(
        node.value, str) else None


def _section_of(node: ast.AST) -> str | None:
    # raw.get("<section>", ...) or raw["<section>"]  # noqa: ERA001 — the two shapes matched, not code
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


# (section, key) → the Config field each commented-out example key binds to
# (F-113): the README rail's mapping, plus the keys only the example names,
# each read from load_config's binding (config.py:586-646).
_FIELD = {
    **_README_FIELD,
    ("scenarios", "seed"): "scenarios_seed",
    ("scenarios", "transfer_threshold"): "transfer_threshold",
    ("scenarios", "irreversible_threshold"): "irreversible_threshold",
    ("odds", "player_props"): "player_props",
    ("odds", "ags_blend_weight"): "ags_blend_weight",
    ("understat", "enabled"): "understat_enabled",
    ("league", "stance"): "stance",
    ("news", "lineup_providers"): "news_lineup_providers",
}
# Commented keys whose value is not a Config default, by name (F-113):
# focus falls through to fpl.league_id when 0 (config.py:586), so 0 is its
# default and is asserted as such; api_key and token show a placeholder
# sentence, dir and rsync_target an example path, where Config holds "".
_FOCUS = ("league", "focus")
_PLACEHOLDERS = {("odds", "api_key"), ("web", "token"),
                 ("backup", "dir"), ("backup", "rsync_target")}
# A ``# key = ...`` line whose value is not TOML is prose, as
# config.example.toml's "# n = 0 disables the sweep" sentence is; the set is
# held exactly so a new one is seen, not skipped.
_PROSE = {("scenarios", "n")}


def _config_defaults() -> dict[str, object]:
    out: dict[str, object] = {}
    for f in dataclasses.fields(Config):
        if f.default is not dataclasses.MISSING:
            out[f.name] = f.default
        elif f.default_factory is not dataclasses.MISSING:
            out[f.name] = f.default_factory()
    return out


def _commented(text: str) -> tuple[list[tuple[str, str, object]],
                                   set[tuple[str, str]]]:
    """Each ``# key = value`` line under a ``[section]``, parsed with tomllib,
    and the (section, key) of each such line whose value is not TOML."""
    section, rows, prose = None, [], set()
    for line in text.splitlines():
        head = re.match(r"\[([a-z_]+)\]", line)
        if head:
            section = head.group(1)
            continue
        m = re.match(r"^# (\w+) = (.+)$", line)
        if not m or section is None:
            continue
        try:
            value = tomllib.loads(f"{m.group(1)} = {m.group(2)}")[m.group(1)]
        except tomllib.TOMLDecodeError:
            prose.add((section, m.group(1)))
            continue
        rows.append((section, m.group(1), value))
    return rows, prose


def _stale(text: str) -> list[str]:
    defaults = _config_defaults()
    rows, prose = _commented(text)
    wrong = [f"[{s}] {k} is prose the rail does not know"
             for s, k in sorted(prose - _PROSE)]
    for section, key, value in rows:
        if (section, key) in _PLACEHOLDERS:
            continue
        if (section, key) == _FOCUS:
            if value != 0:
                wrong.append(f"[{section}] {key} = {value!r}, falls through at 0")
            continue
        name = _FIELD.get((section, key))
        if name is None:
            wrong.append(f"[{section}] {key} has no Config field in the rail")
        elif value != defaults[name]:
            wrong.append(f"[{section}] {key} = {value!r}, "
                         f"Config.{name} = {defaults[name]!r}")
    return wrong


def test_the_example_reads_the_commented_keys_this_rail_checks():
    rows, prose = _commented(EXAMPLE.read_text())
    keys = {(s, k) for s, k, _ in rows}
    assert {("scenarios", "seed"), ("league", "focus"),
            ("odds", "player_props")} <= keys, keys
    assert prose == _PROSE, prose


def test_every_commented_default_in_the_example_equals_config():
    assert _stale(EXAMPLE.read_text()) == []


def test_an_example_with_one_commented_default_changed_fails_by_key():
    text = EXAMPLE.read_text()
    assert "# seed = 20260825\n" in text
    assert _stale(text.replace("# seed = 20260825\n", "# seed = 7\n")) == [
        "[scenarios] seed = 7, Config.scenarios_seed = 20260825"]
