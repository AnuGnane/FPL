"""schemas.py -> frontend/src/schemas.json (v12 W5 §6.6).

Run it and commit both outputs:

    .venv/bin/python scripts/gen_types.py
    cd frontend && npx vitest run src/types.generated.test.ts

`types.ts` is **not** generated and cannot be. Thirty of its exports have no
pydantic source — thirteen of them type the *inside* of payloads the server
declares as `dict[str, Any]` — and nine models are narrowed by hand in the
browser. A generator that overwrote `types.ts` would delete a third of the file
and stop every `advice.captain.name` in the tree from compiling (plan A9).

So the file splits. This script emits the JSON Schema; the vitest test
`frontend/src/types.generated.test.ts` compiles it with
`json-schema-to-typescript` and diffs the result against the committed
`frontend/src/types.generated.ts`; and `frontend/src/types.ts` keeps the
hand-written half and re-exports the generated one, so every existing
`import ... from '../types'` is unchanged.
"""

from __future__ import annotations

import json
import pathlib
import sys

WIRE_ONLY = (
    "AdviceLatest", "History", "ModelHealth", "Health", "CalibrationReport",
    "ReviewSummary", "Review",
    "PlayerRow", "PlayerExplain", "PlanTimeline", "PlayerRef",
)
"""Models the client narrows by hand, emitted as ``Wire<Name>``.

Literally "what the server sends" — so the hand-written narrowing keeps the
plain name its consumers already import and nothing collides. Two reasons a
model is on this list, and :data:`NARROWING_REASON` says which applies:

* six carry ``Any``, which the generator can only describe as an open record;
* three carry a list field the browser reads through ``?? []`` and whose
  hand-written comment says *why* the guard is there — a sentence the JSON
  Schema has no room for, since pydantic puts attribute docstrings nowhere the
  schema can see them.
"""

NARROWING_REASON = {
    "AdviceLatest":
        "advice: dict[str, Any] on the server, and every consumer in this "
        "tree reads advice.captain.name",
    "History":
        "backtests: a list of open records the History tab narrows per row",
    "ModelHealth":
        "metrics: an open record, keyed by whatever the model wrote",
    "Health":
        "model_health: an open record the health card narrows by hand",
    "CalibrationReport":
        "excluded: a list of open records, one per dropped fixture",
    "ReviewSummary":
        "best: an open record; `worst` is the same shape and rides along",
    "Review":
        "summary: a `$ref` at the wire type, and the client's narrowed "
        "`ReviewSummary` is what the tab reads `worst.lane` off",
    "PlayerRef":
        "position: `Advice` types the raw artifact, which the server hands "
        "over as `dict[str, Any]` and never validates — so the artifact's own "
        "`tag` and `frequency` are there and the enrichment may not be",
    "PlayerRow":
        "set_piece_manual: absent on a payload banked before the field "
        "existed, which is what the read sites' `?? []` is for",
    "PlayerExplain":
        "set_pieces_manual: absent on a payload banked before the field "
        "existed, which is what the read sites' `?? []` is for",
    "PlanTimeline":
        "alternatives: absent from a server older than the field, which is "
        "what PlannerBoard's `?? []` is for",
}
"""Why each :data:`WIRE_ONLY` model is narrowed: ``field: reason``.

The field name is checked against the live model, so a narrowing whose field
was renamed or deleted fails loudly instead of standing as a hand-written type
nobody dares touch.
"""

OPTIONAL_ON_THE_WIRE = {
    ("LeagueWhatIfRequest", "cached_only"):
        "This Week sets it and both league views omit it; "
        "WhatIfSim.test.tsx:55 pins that the body carries no such key.",
}
"""``(model, field) -> why this one field may be absent.``

Every other field is emitted ``required``, which is what the wire actually
carries: a response model is serialized on the way out with its defaults filled
in, so every key is present. Pydantic's own schema leaves a defaulted field out
of ``required``, and taking its word typed a hundred and seventy-nine unguarded
reads in the client as possibly-undefined — each of which would have been
answered with a `?? {}` guard against a case that cannot happen.

Request bodies are the direction where a default *can* be left out, and the
client builds all of them complete except this one. Listing the exception by
field rather than exempting every request model keeps the guard where the
omission is: a new partial body fails at its own call site, loudly, instead of
softening every request type in the tree.
"""

RENAME = {
    # The client suffixes a page-level payload with `Data` so the name does not
    # collide with a component or a lane name. Fourteen of these predate this
    # script and every one of them has consumers.
    "Confidence": "ConfidenceData",
    "Decomposition": "DecompositionData",
    "FixtureMatrix": "FixtureMatrixData",
    "FlagLatency": "FlagLatencyData",
    "Journal": "JournalData",
    "LeagueRace": "LeagueRaceData",
    "Misses": "MissesData",
    "NewsShadow": "NewsShadowData",
    "PenTracker": "PenTrackerData",
    "PresserGrades": "PresserGradesData",
    "Quality": "QualityData",
    "RivalDetail": "RivalDetailData",
    "Ticker": "TickerData",
    # The nine the browser narrows.
    "AdviceLatest": "WireAdviceLatest",
    "CalibrationReport": "WireCalibrationReport",
    "Health": "WireHealth",
    "History": "WireHistory",
    "ModelHealth": "WireModelHealth",
    "PlanTimeline": "WirePlanTimeline",
    "PlayerExplain": "WirePlayerExplain",
    "PlayerRef": "WirePlayerRef",
    "PlayerRow": "WirePlayerRow",
    "Review": "WireReview",
    "ReviewSummary": "WireReviewSummary",
}
"""Pydantic name -> TypeScript name.

``CalibrationReport``, ``Health`` and ``History`` are both renamed *and*
narrowed, and the ``Wire`` prefix wins because the hand-written
``CalibrationData``/``HealthData``/``HistoryData`` are the narrowings.
``test_every_wire_only_model_is_renamed_with_the_wire_prefix`` is what keeps
that consistent.
"""


def schema_path() -> str:
    return "frontend/src/schemas.json"


_NAME_TO_SCHEMA = ("properties", "patternProperties", "$defs", "definitions",
                   "dependentSchemas")
"""JSON Schema keywords whose value maps a *name* to a schema, not a keyword to
a value. Walking into one as if it were a schema treats every field name as a
keyword."""


def _strip_titles(node) -> None:
    """Drop pydantic's auto-generated ``title`` from everywhere but the model.

    Pydantic titles every property (``"title": "Opponent Short"``), and
    ``json-schema-to-typescript`` reads a title as "this shape deserves a name
    of its own": left in, they emit eight hundred standalone aliases —
    ``export type Name = string``, then ``Name1``, ``Code2``, ``Bytes1`` —
    which is a name collision waiting to happen and an export surface nobody
    asked for.
    """
    if isinstance(node, dict):
        node.pop("title", None)
        for key, value in node.items():
            if key in _NAME_TO_SCHEMA and isinstance(value, dict):
                # A map from *field name* to schema. Its keys are field names,
                # not keywords: `DigestSection.title` is a field called title,
                # and stripping it here deleted the field.
                for sub in value.values():
                    _strip_titles(sub)
            else:
                _strip_titles(value)
    elif isinstance(node, list):
        for value in node:
            _strip_titles(value)


def _field_sentences() -> dict:
    """``(model, field) -> the sentence written under it in schemas.py``.

    Pydantic carries an attribute docstring into a JSON Schema only when the
    model sets ``use_attribute_docstrings``, which here would be a hundred and
    forty-seven identical config lines. Reading them costs one ``ast`` walk and
    keeps schemas.py the single place the sentence is written — which matters
    more than usual, because the split deletes the hand-written interfaces
    those sentences were duplicated on.
    """
    import ast
    import inspect

    from gaffer.web import schemas

    out = {}
    for cls in ast.parse(inspect.getsource(schemas)).body:
        if not isinstance(cls, ast.ClassDef):
            continue
        for stmt, following in zip(cls.body, cls.body[1:]):
            if (isinstance(stmt, ast.AnnAssign)
                    and isinstance(stmt.target, ast.Name)
                    and isinstance(following, ast.Expr)
                    and isinstance(following.value, ast.Constant)
                    and isinstance(following.value.value, str)):
                out[(cls.name, stmt.target.id)] = inspect.cleandoc(
                    following.value.value)
    return out


def _models():
    from pydantic import BaseModel

    from gaffer.web import schemas

    out = []
    for name, obj in sorted(vars(schemas).items()):
        if (isinstance(obj, type) and issubclass(obj, BaseModel)
                and obj is not BaseModel
                and obj.__module__ == schemas.__name__):
            out.append((name, obj))
    return out


def build_schema() -> dict:
    """Every response model as one ``definitions`` document.

    ``definitions`` and not ``$defs``: ``json-schema-to-typescript`` reads the
    former, and a 2020-12 document compiles to one empty interface with
    nothing saying why.

    ``"serialization"`` mode: this document types what the wire carries, not
    what pydantic would coerce on the way in. ``required`` is then every field
    but the ones :data:`OPTIONAL_ON_THE_WIRE` names.

    Sorted throughout and emitted through :func:`serialize`, because the whole
    point is a diff that is stable across machines and interpreter runs.
    """
    from pydantic.json_schema import models_json_schema

    models = _models()
    _, top = models_json_schema(
        [(model, "serialization") for _, model in models],
        ref_template="#/definitions/{model}", title="Gaffer API")
    defs = top.get("$defs", {})
    sentences = _field_sentences()
    renamed = {}
    for name in sorted(defs):
        body = defs[name]
        _strip_titles(body)
        for field, prop in sorted(body.get("properties", {}).items()):
            sentence = sentences.get((name, field))
            if sentence and "description" not in prop:
                prop["description"] = sentence
            if not set(prop) - {"description", "default"}:
                # ``value: Any``. An empty schema compiles to an *object* —
                # `{[k: string]: unknown}` — so `row.value === true` stops
                # type-checking. `tsType` is json-schema-to-typescript's own
                # escape hatch and says the one true thing: unknown.
                prop["tsType"] = "unknown"
        if "properties" in body:
            body["required"] = [
                field for field in sorted(body["properties"])
                if (name, field) not in OPTIONAL_ON_THE_WIRE]
        # Put the title back, as the *renamed* name: it is what
        # json-schema-to-typescript names the interface, so a definition that
        # kept pydantic's title would emit `AdviceLatest` out of a definition
        # called `WireAdviceLatest` and the rename would be a no-op.
        body["title"] = RENAME.get(name, name)
        renamed[body["title"]] = body
    text = json.dumps({"definitions": renamed}, sort_keys=True)
    for old, new in RENAME.items():
        text = text.replace(f'"#/definitions/{old}"',
                            f'"#/definitions/{new}"')
    return json.loads(text)


def serialize(schema: dict) -> str:
    """The one way this document is ever written to disk."""
    return json.dumps(schema, sort_keys=True, indent=1) + "\n"


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    target = root / schema_path()
    target.write_text(serialize(build_schema()))
    print(f"wrote {target}")
    print("now run: cd frontend && npx vitest run src/types.generated.test.ts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
