"""Every spec since the conventions pre-registers its gate (holiday F-145).

``CLAUDE.md`` "How a cycle runs" puts the gate and verdict rule in the spec
before anything runs, and ``CONVENTIONS.md`` §2 says gates are
pre-registered. Those conventions date from the measurement cycle v7b
(2026-08-30), so every spec dated that day or later names its gate. The rule
is that the word is there, not where: a heading, a bold label or prose all
count. In F-129's shape (``tests/test_roadmap_specs.py``).
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

SPECS = Path("docs/superpowers/specs")
CONVENTIONS_FROM = date(2026, 8, 30)
# Written before the conventions existed, so neither had a gate to name.
FROZEN = (
    "2026-08-23-fpl-ml-advisor-design.md",
    "2026-08-26-gaffer-v5.1-news-completion-design.md",
)
_DATED = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-.*\.md$")
_GATE = re.compile(r"\bgates?\b", re.IGNORECASE)


def _ungated(specs: Path) -> list[str]:
    """The specs dated on or after the conventions that never say gate."""
    misses = []
    for p in sorted(specs.glob("*.md")):
        m = _DATED.match(p.name)
        if m is None or p.name in FROZEN:
            continue
        if date(*map(int, m.groups())) < CONVENTIONS_FROM:
            continue
        if not _GATE.search(p.read_text()):
            misses.append(str(p))
    return misses


def test_there_are_specs_to_check():
    assert len(list(SPECS.glob("*.md"))) > 50


def test_every_spec_since_the_conventions_names_its_gate():
    assert _ungated(SPECS) == []


def test_the_frozen_specs_are_the_ones_without_a_gate():
    for name in FROZEN:
        assert not _GATE.search((SPECS / name).read_text()), name


def test_the_rail_bites_on_a_spec_dated_today_with_no_gate(tmp_path):
    today = date.today().isoformat()  # noqa: DTZ011 — any date past CONVENTIONS_FROM bites; the zone cannot move it
    (tmp_path / f"{today}-v99-design.md").write_text("# v99\n\nNo verdict rule.\n")
    (tmp_path / f"{today}-v98-design.md").write_text("# v98\n\n## Gates\n")
    (tmp_path / "2026-08-29-v7a-design.md").write_text("# v7a\n")
    assert _ungated(tmp_path) == [str(tmp_path / f"{today}-v99-design.md")]
