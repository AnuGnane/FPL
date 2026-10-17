"""The README's configuration block shows ``Config``'s defaults (holiday F-104).

ROADMAP candidate 7, in F-103's shape (``tests/test_config_example.py``):
README §Configuration promises its ``toml`` block shows the defaults "as
``src/gaffer/config.py`` declares them", and nothing held the promise. Each
(section, key) is mapped to the ``Config`` field ``load_config`` binds it to
(``_FIELD`` below), and its value must equal that field's default.

``[data] train_seasons`` is the one exception: the block shows the seasons
this tree trains on while the field defaults to an empty list, so for it the
rail asserts a list of ``YYYY-YY`` strings. ``[fpl]`` ``entry_id`` and
``league_id`` have no default, so the rail asserts they are present. A key
the loader does not read fails the rail by name.
"""

from __future__ import annotations

import dataclasses
import re
import tomllib
from pathlib import Path

from gaffer.config import Config

README = Path("README.md")

# (section, key) → the Config field load_config binds it to. [optimizer] and
# [data] are spread with ** so their keys are field names; the rest are read
# key by key from config.py's load_config onward (F-104).
_FIELD = {
    ("optimizer", "horizon"): "horizon",
    ("optimizer", "decay"): "decay",
    ("optimizer", "vice_weight"): "vice_weight",
    ("optimizer", "bench_weight"): "bench_weight",
    ("optimizer", "ft_value"): "ft_value",
    ("optimizer", "itb_value"): "itb_value",
    ("optimizer", "hit_cost"): "hit_cost",
    ("optimizer", "price_timing"): "price_timing",
    ("optimizer", "alt_plan_max_gap"): "alt_plan_max_gap",
    ("optimizer", "max_hits"): "max_hits",
    ("optimizer", "max_transfers"): "max_transfers",
    ("optimizer", "hit_bar"): "hit_bar",
    ("optimizer", "top_n"): "top_n",
    ("model", "xg_per_shot"): "xg_per_shot",
    ("scenarios", "n"): "scenarios_n",
    ("scenarios", "draw_availability"): "draw_availability",
    ("scenarios", "decision_priors"): "decision_priors",
    ("data", "current_season"): "current_season",
}
_NO_DEFAULT = {("fpl", "entry_id"), ("fpl", "league_id")}
_SEASONS = ("data", "train_seasons")


def _block() -> str:
    text = README.read_text()
    head = text.index("## Configuration")
    start = text.index("```toml\n", head) + len("```toml\n")
    return text[start:text.index("```", start)]


def _defaults() -> dict[str, object]:
    out: dict[str, object] = {}
    for f in dataclasses.fields(Config):
        if f.default is not dataclasses.MISSING:
            out[f.name] = f.default
        elif f.default_factory is not dataclasses.MISSING:
            out[f.name] = f.default_factory()
    return out


def _wrong(block: str) -> list[str]:
    defaults = _defaults()
    parsed = tomllib.loads(block)
    seen = {(s, k) for s, keys in parsed.items() for k in keys}
    wrong = [f"[{s}] {k} missing" for s, k in sorted(_NO_DEFAULT - seen)]
    for section, key in sorted(seen):
        value = parsed[section][key]
        if (section, key) in _NO_DEFAULT:
            continue
        if (section, key) == _SEASONS:
            if not (isinstance(value, list) and value and all(
                    isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}", v)
                    for v in value)):
                wrong.append(f"[{section}] {key} = {value!r} not seasons")
            continue
        name = _FIELD.get((section, key))
        if name is None:
            wrong.append(f"[{section}] {key} is not read by load_config")
        elif value != defaults[name]:
            wrong.append(f"[{section}] {key} = {value!r}, "
                         f"Config.{name} = {defaults[name]!r}")
    return wrong


def test_the_mapping_names_real_config_fields():
    names = {f.name for f in dataclasses.fields(Config)}
    assert set(_FIELD.values()) <= names, set(_FIELD.values()) - names


def test_the_readme_block_shows_the_config_defaults():
    assert _wrong(_block()) == []


def test_a_block_with_one_value_changed_fails_the_rail():
    block = _block()
    assert "decay = 0.85 " in block
    assert _wrong(block.replace("decay = 0.85 ", "decay = 0.9 ")) == [
        "[optimizer] decay = 0.9, Config.decay = 0.85"]


def test_a_key_the_loader_does_not_read_fails_the_rail_by_name():
    block = _block().replace("[model]\n", "[model]\nshot_head = true\n")
    assert _wrong(block) == ["[model] shot_head is not read by load_config"]
