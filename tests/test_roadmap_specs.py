"""Every spec and plan under ``docs/superpowers/`` is named in the ROADMAP
(holiday F-129).

ROADMAP candidate 7, in F-87's shape (``tests/test_guide_scripts.py``): a
file nothing names is one a reader cannot find a reason for. The ROADMAP is
the index of cycles, so each spec and plan is named there by its filename,
at the end of the block of the cycle it belongs to (v17d's "Spec ``…``, plan
``…``" form). ``HOLIDAY.md`` and the GUIDE name some of them too; this rail
does not read them. No allowlist.
"""

from __future__ import annotations

import re
from pathlib import Path

ROADMAP = Path("docs/superpowers/ROADMAP.md")
DIRS = (Path("docs/superpowers/specs"), Path("docs/superpowers/plans"))


def _files() -> list[Path]:
    return sorted(p for d in DIRS for p in d.glob("*.md"))


def _misses(text: str, files: list[Path]) -> list[str]:
    """The files whose name ``text`` does not hold as a whole name."""
    # Bounded on both sides, so `v17d-pipeline.md` does not pass on
    # `v17d-pipeline-design.md` nor `v8a.md` on a longer name ending in it.
    return [
        str(p)
        for p in files
        if not re.search(rf"(?<![\w-]){re.escape(p.name)}(?![\w-])", text)
    ]


def test_there_are_specs_and_plans_to_check():
    names = {p.parent.name for p in _files()}
    assert names == {"specs", "plans"} and len(_files()) > 100, len(_files())


def test_every_spec_and_plan_is_named_in_the_roadmap():
    assert _misses(ROADMAP.read_text(), _files()) == []


def test_the_rail_bites_on_a_roadmap_missing_one():
    files = [Path("docs/superpowers/specs/2026-09-07-v17d-pipeline-design.md"),
             Path("docs/superpowers/plans/2026-09-07-v17d-pipeline.md")]
    text = "Spec `2026-09-07-v17d-pipeline-design.md`."
    assert _misses(text, files) == [str(files[1])]
