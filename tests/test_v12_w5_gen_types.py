"""v12 W5 §6.6 — the committed JSON Schema is the live models'.

The Python half of the types pipeline. The TypeScript half is
frontend/src/types.generated.test.ts, which compiles *this* file and diffs the
result against the committed types.generated.ts — so if this test is green and
that one is green, the browser's types are the server's.
"""
from __future__ import annotations

import ast
import inspect
import json
import pathlib
import re

from scripts.gen_types import (NARROWING_REASON, RENAME, WIRE_ONLY,
                               build_schema, schema_path, serialize)

REPO = pathlib.Path(__file__).resolve().parents[1]


def _live(module_only: bool = True) -> dict:
    from pydantic import BaseModel

    from gaffer.web import schemas

    return {name: obj for name, obj in vars(schemas).items()
            if isinstance(obj, type) and issubclass(obj, BaseModel)
            and obj is not BaseModel
            and (not module_only or obj.__module__ == schemas.__name__)}


def test_the_committed_schema_is_the_one_the_models_produce():
    committed = json.loads((REPO / schema_path()).read_text())
    assert committed == build_schema(), (
        "frontend/src/schemas.json is stale — run "
        "`.venv/bin/python scripts/gen_types.py` and commit both it and "
        "frontend/src/types.generated.ts")


def test_the_committed_schema_is_byte_for_byte_what_the_writer_writes():
    """Not just equal as JSON — equal as bytes.

    ``types.generated.ts`` is diffed against the *file*, so a schema that
    round-trips equal but serializes differently would make the TypeScript
    half fail with nothing in this half saying why.
    """
    assert (REPO / schema_path()).read_text() == serialize(build_schema())


def test_it_is_written_deterministically():
    """Twice in one process must be byte-identical, *without* sort_keys doing
    the work — the committed file is the writer's own key order, so it is that
    order which has to be stable, not a sorted view of it."""
    assert json.dumps(build_schema()) == json.dumps(build_schema())


def test_every_pydantic_model_in_schemas_py_is_in_it():
    live = set(_live())
    emitted = {RENAME.get(name, name) for name in live}
    assert set(build_schema()["definitions"]) == emitted


def test_no_two_response_models_share_a_name():
    """Two ``class NextFixture`` in one module is a def the generator cannot
    name: pydantic mangles both into ``gaffer__web__schemas__NextFixture__1``
    and ``__2``, and the second class silently shadows the first for every
    ``from .schemas import NextFixture`` in the tree."""
    from gaffer.web import schemas

    tree = ast.parse(inspect.getsource(schemas))
    names = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
    assert len(names) == len(set(names)), sorted(
        n for n in names if names.count(n) > 1)


def test_the_rename_map_names_only_models_that_exist():
    live = set(_live(module_only=False))
    assert set(RENAME) <= live
    assert set(WIRE_ONLY) <= live


def test_no_rename_lands_on_a_model_that_was_not_renamed():
    """``Review`` -> ``ReviewData`` is only safe while nothing is *called*
    ``ReviewData`` already. If a later cycle adds one, this says so instead of
    silently emitting one definition where there should be two."""
    live = set(_live())
    untouched = live - set(RENAME)
    assert set(RENAME.values()) & untouched == set()


def test_every_wire_only_model_is_renamed_with_the_wire_prefix():
    """The models the client narrows by hand (AdviceLatest.advice is
    dict[str, Any] on the server and an `Advice` interface in the browser).
    Emitting them under their plain names would collide with the narrowing and
    break every consumer."""
    for name in WIRE_ONLY:
        assert RENAME[name] == f"Wire{name}"


def test_every_narrowing_states_the_field_it_narrows_and_why():
    """A narrowing with no stated reason is a hand-written type nobody dares
    delete. Each one names the field it overrides, so the next reader can
    check whether the reason still holds."""
    assert set(NARROWING_REASON) == set(WIRE_ONLY)
    for name, reason in NARROWING_REASON.items():
        field, _, why = reason.partition(": ")
        assert field and why, name
        assert field in _live()[name].model_fields, (name, field)


def test_no_two_models_are_renamed_onto_one_name():
    assert len(set(RENAME.values())) == len(RENAME)


def test_every_ref_points_at_a_definition_that_exists():
    schema = build_schema()
    text = json.dumps(schema)
    refs = set(re.findall(r'"#/definitions/([A-Za-z0-9_]+)"', text))
    assert refs <= set(schema["definitions"])


def test_no_ref_still_points_at_a_pre_rename_name():
    """The rename is a text substitution over the whole document; a ``$ref``
    the substitution missed would compile to a TypeScript name that does not
    exist."""
    text = json.dumps(build_schema())
    for old in RENAME:
        assert f'"#/definitions/{old}"' not in text, old


def test_the_sentence_under_a_field_in_schemas_py_reaches_the_schema():
    """The split deletes a hundred hand-written interfaces and the comments on
    them. What survives has to be the sentence schemas.py already writes —
    pydantic drops attribute docstrings unless every model opts in, so the
    generator reads them itself.
    """
    props = build_schema()["definitions"]["SettingsPanel"]["properties"]
    assert props["unavailable"]["description"].startswith(
        "Whitelisted settings this build's ``Config`` does not have.")


def test_a_field_with_no_sentence_gets_no_description():
    """Not every field is documented, and inventing a description for one that
    is not would put the generator's voice in the browser."""
    props = build_schema()["definitions"]["SettingsPanel"]["properties"]
    assert "description" not in props["rows"]


def test_a_defaulted_field_is_still_required():
    """What the wire *carries*, not what pydantic would accept.

    A response model is serialized on the way out with its defaults filled in,
    so every key is present. Pydantic's own schema leaves a defaulted field out
    of ``required``, which typed a hundred and seventy-nine unguarded reads in
    the client as possibly-undefined — each of which would have been answered
    with a `?? {}` guard against a case that cannot happen.
    """
    panel = build_schema()["definitions"]["SettingsPanel"]
    assert set(panel["required"]) == set(panel["properties"])
    assert "rows" in panel["required"]


def test_the_fields_the_client_omits_are_optional_and_say_why():
    """Two of them, and both are request bodies where the omission *means*
    something: `cached_only` absent is "do the fetch", and `WatchRequest.note`
    absent is "say nothing about the note", which is not the same request as
    `note: ''`."""
    from scripts.gen_types import OPTIONAL_ON_THE_WIRE

    req = build_schema()["definitions"]["LeagueWhatIfRequest"]
    assert "cached_only" in req["properties"]
    assert "cached_only" not in req["required"]
    star = build_schema()["definitions"]["WatchRequest"]
    assert "note" in star["properties"]
    assert "note" not in star["required"]
    for (model, field), why in OPTIONAL_ON_THE_WIRE.items():
        assert field in _live()[model].model_fields, (model, field)
        assert len(why) > 20, (model, field)


def test_nothing_else_is_optional():
    """Two exceptions, and they are the listed ones. A third that crept in
    unlisted would soften a type in the browser with nothing saying why."""
    from scripts.gen_types import OPTIONAL_ON_THE_WIRE

    loose = {(name, field)
             for name, body in build_schema()["definitions"].items()
             for field in body.get("properties", {})
             if field not in body.get("required", [])}
    assert loose == {(RENAME.get(model, model), field)
                     for model, field in OPTIONAL_ON_THE_WIRE}


def test_a_field_actually_called_title_survives_the_title_strip():
    """Pydantic's auto-generated ``title`` is dropped everywhere but the model.
    ``DigestSection.title`` is a *field* with that name, and a strip that walked
    into the ``properties`` map deleted it — leaving a schema the digest card
    could not compile against and nothing saying which side was wrong."""
    section = build_schema()["definitions"]["DigestSection"]
    assert "title" in section["properties"]
    assert section["properties"]["title"] == {"type": "string"}


def test_a_bare_any_field_compiles_to_unknown_and_not_to_a_record():
    """``value: Any`` is one setting's value, of five different shapes —
    ``unknown``, which ``kind`` narrows. Left as an empty schema it compiled to
    ``{[k: string]: unknown}``, an object, and the tab's `value === true` stopped
    type-checking."""
    value = build_schema()["definitions"]["SettingRow"]["properties"]["value"]
    assert value["tsType"] == "unknown"


def test_the_root_uses_definitions_and_not_defs():
    """json-schema-to-typescript reads `definitions`. A 2020-12 `$defs`
    document compiles to a single empty interface and nothing says why."""
    schema = build_schema()
    assert "definitions" in schema and "$defs" not in schema
