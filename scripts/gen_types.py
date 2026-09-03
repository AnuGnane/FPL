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
    "ReviewSummary",
    "PlayerRow", "PlayerExplain", "PlanTimeline",
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
    "Review": "ReviewData",
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
    "PlayerRow": "WirePlayerRow",
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

    ``"serialization"`` mode and not ``"validation"``: this document types what
    the server *sends*, so a field pydantic would coerce on the way in is
    irrelevant and a field with a default is still emitted (and so is still
    optional here — which is what keeps the browser's ``?? []`` guards honest).

    Sorted throughout and emitted through :func:`serialize`, because the whole
    point is a diff that is stable across machines and interpreter runs.
    """
    from pydantic.json_schema import models_json_schema

    models = _models()
    _, top = models_json_schema(
        [(model, "serialization") for _, model in models],
        ref_template="#/definitions/{model}", title="Gaffer API")
    defs = top.get("$defs", {})
    renamed = {RENAME.get(name, name): defs[name] for name in sorted(defs)}
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
