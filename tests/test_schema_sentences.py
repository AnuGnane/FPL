"""Every field of every wire model carries a sentence (holiday F-121).

ROADMAP candidate 7, in F-103's shape (``tests/test_config_example.py``).
``scripts/gen_types.py`` copies the docstring written under each annotated
field of ``src/gaffer/web/schemas.py`` into ``types.generated.ts``, so a field
without one reaches the frontend unexplained. GUIDE §12.4 counted 1,024 of
1,031 carrying one; F-121 wrote the seven missing ones, and this rail keeps
the count at every field. The allowlist is empty; a new field gets its
sentence in ``schemas.py``, never an entry here.

The rail reads the models ``schemas.py`` defines, the ones
``_field_sentences()`` walks and GUIDE §12.4's 1,031 counts. ``_models()``
also yields the nine ``gaffer.served`` models ``WIRE_EXPORTS`` re-exports;
their fields are written in ``served.py``, which the generator does not read
and which sits on the golden path, so they stay outside this rail (F-121's
ruling 1).
"""

from __future__ import annotations

from gaffer.web import schemas
from scripts.gen_types import _field_sentences, _models

# (model, field) pairs excused from carrying a sentence. Empty since F-121.
ALLOWED: frozenset[tuple[str, str]] = frozenset()


def missing_sentences(models, sentences) -> list[str]:
    """``Model.field`` for every wire field with no sentence under it."""
    return [
        f"{name}.{field}"
        for name, model in models
        if model.__module__ == schemas.__name__
        for field in model.model_fields
        if (name, field) not in sentences and (name, field) not in ALLOWED
    ]


def test_the_walk_finds_the_models_and_sentences_this_rail_reads():
    models = _models()
    assert sum(m.__module__ == schemas.__name__ for _, m in models) > 100
    assert ("PlanSummary", "gw") in _field_sentences()


def test_every_wire_field_carries_a_sentence():
    assert missing_sentences(_models(), _field_sentences()) == []


def test_a_field_without_a_sentence_fails_the_rail_by_name():
    sentences = dict(_field_sentences())
    del sentences[("PlanSummary", "gw")]
    assert "PlanSummary.gw" in missing_sentences(_models(), sentences)
