"""The GUIDE's version history names every cycle the ROADMAP ships
(holiday F-140).

ROADMAP candidate 7, in F-129's shape (``tests/test_roadmap_specs.py``).
ROADMAP "## Shipped" holds one ``### <cycle> — …`` heading per shipped
cycle; GUIDE §11 opens each paragraph ``**v… —``. Nothing held the two
lists together, so a cycle could ship without a line in the history. The
GUIDE groups some cycles into one paragraph (v4, v7 and v9), so a cycle is
named when an opener is the cycle itself or its bare major. Headings that
are not a cycle (``### Hotfix 2026-09-04 — …``) are not read.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
ROADMAP = _ROOT / "docs/superpowers/ROADMAP.md"
GUIDE = _ROOT / "docs/GUIDE.md"

_CYCLE = re.compile(r"v(\d+)([a-z]?)(?![a-z])")
_HEADING = re.compile(r"^### (v\S*)", re.MULTILINE)
_OPENER = re.compile(r"^\*\*(v[^ *]+) —", re.MULTILINE)


def shipped(roadmap: str) -> set[str]:
    """Each cycle under "## Shipped", as ``v<major><letter?>``."""
    section = roadmap.split("\n## Shipped", 1)[1].split("\n## ", 1)[0]
    cycles = set()
    for head in _HEADING.findall(section):
        m = _CYCLE.match(head)
        cycles.add(f"v{m[1]}{m[2]}")
    return cycles


def named(guide: str) -> set[str]:
    """Each cycle a §11 opener names; ``v1–v3`` is the range, ``v10/v10b``
    both."""
    section = guide.split("\n## 11.", 1)[1].split("\n## 12", 1)[0]
    cycles = set()
    for opener in _OPENER.findall(section):
        for part in opener.split("/"):
            ends = [_CYCLE.match(e) for e in part.split("–")]
            if len(ends) == 2 and not ends[0][2] and not ends[1][2]:
                lo, hi = int(ends[0][1]), int(ends[1][1])
                cycles.update(f"v{n}" for n in range(lo, hi + 1))
            else:
                cycles.update(f"v{m[1]}{m[2]}" for m in ends if m)
    return cycles


def missing(roadmap: str, guide: str) -> list[str]:
    """The shipped cycles no opener names, exactly or by bare major."""
    have = named(guide)
    return sorted(c for c in shipped(roadmap)
                  if c not in have and _CYCLE.match(c)[1] not in
                  {_CYCLE.match(h)[1] for h in have if not _CYCLE.match(h)[2]})


def test_the_guide_history_names_every_shipped_cycle():
    roadmap = ROADMAP.read_text(encoding="utf-8")
    guide = GUIDE.read_text(encoding="utf-8")
    assert len(shipped(roadmap)) > 40
    gaps = missing(roadmap, guide)
    assert gaps == [], f"GUIDE §11 has no paragraph for {gaps}"


def test_a_heading_reads_as_its_cycle_and_an_opener_expands():
    roadmap = ("# R\n## Shipped\n\n### v3 / v3.1 — web\n### v5.1 — news\n"
               "### v7-ui — ui\n### v12 W1 — hygiene\n### v17a — wire\n"
               "### Hotfix 2026-09-04 — rule\n\n## Operational\n### v99 — no\n")
    assert shipped(roadmap) == {"v3", "v5", "v7", "v12", "v17a"}
    guide = ("# G\n## 11. History\n\n**v1–v3 — core.** x\n\n**v10/v10b — m.** y\n"
             "\n## 12. Pending\n\n**v50 — not history.**\n")
    assert named(guide) == {"v1", "v2", "v3", "v10", "v10b"}


def test_the_rail_bites_on_a_cycle_the_guide_never_names(tmp_path):
    (tmp_path / "ROADMAP.md").write_text(
        "# R\n## Shipped\n\n### v9b — polish\n### v20a — next\n### v4c — decide\n"
        "\n## Operational\n", encoding="utf-8")
    (tmp_path / "GUIDE.md").write_text(
        "# G\n## 11. History\n\n**v4 — measure.** x\n\n**v9 — pitch.** y\n"
        "\n**v20b — other.** z\n\n## 12. Pending\n", encoding="utf-8")
    assert missing((tmp_path / "ROADMAP.md").read_text(encoding="utf-8"),
                   (tmp_path / "GUIDE.md").read_text(encoding="utf-8")) == [
        "v20a"]
