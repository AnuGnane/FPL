"""The two data-gated tables hold the same nine rows (holiday F-124).

ROADMAP candidate 7, holiday F-49's line: ROADMAP "Data-gated" (Row |
Unblocks when | Expected) and GUIDE §12.2 (Surface | Needs | Where it
stands) describe the same rows in two voices, and F-49 levelled them by
hand once. A package that moves one row leaves the other behind; this reads
both as text and holds them level on the row count, the ``W<n>`` tags and
how many read met. On a disagreement the ROADMAP follows the GUIDE, the
fuller record.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

GUIDE = Path("docs/GUIDE.md")
ROADMAP = Path("docs/superpowers/ROADMAP.md")
_GUIDE_HEADING = "### 12.2 Waiting on data, not code"
_ROADMAP_HEADING = "### Data-gated"


def _rows(text: str, heading: str) -> list[list[str]]:
    """The first table's body rows under ``heading``, each a list of cells.

    ``tests/test_guide_readings.py``'s ``_rows``, taking the heading.
    """
    start = next((i for i, line in enumerate(text.splitlines())
                  if line.startswith(heading)), None)
    assert start is not None, f"{heading!r} not found"
    rows = []
    for line in text.splitlines()[start + 1:]:
        if line.startswith("#"):
            break
        if not line.startswith("|") or set(line) <= set("|-: "):
            continue
        rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows[1:]  # the header row


def roadmap_rows(text: str) -> list[tuple[str, bool, str]]:
    """``(W<n>, met, row)``: the Row cell's leading tag, ``**met**`` in Expected."""
    out = []
    for row in _rows(text, _ROADMAP_HEADING):
        tag = re.match(r"(W\d+)\b", row[0])
        out.append((tag.group(1) if tag else "?", "**met**" in row[-1], row[0]))
    return out


def guide_rows(text: str) -> list[tuple[str, bool, str]]:
    """``(W<n>, met, row)``: the Surface cell's trailing ``(W<n>)``.

    Met is ``**Filled.**`` opening the last cell.
    """
    out = []
    for row in _rows(text, _GUIDE_HEADING):
        tag = re.search(r"\((W\d+)\)\s*$", row[0])
        out.append((tag.group(1) if tag else "?",
                    row[-1].startswith("**Filled.**"), row[0]))
    return out


def disagreements(guide: list[tuple[str, bool, str]],
                  roadmap: list[tuple[str, bool, str]]) -> list[str]:
    """Each way the two tables differ, naming the rows on each side."""
    out = []
    if len(guide) != 9 or len(roadmap) != 9:
        out.append(f"rows: GUIDE {len(guide)}, ROADMAP {len(roadmap)}, "
                   "expected nine each")
    untagged = [f"{side} {row}" for side, rows in (("GUIDE", guide),
                                                     ("ROADMAP", roadmap))
                for tag, _, row in rows if tag == "?"]
    if untagged:
        out.append(f"no W tag: {untagged}")
    g_tags, r_tags = Counter(t for t, _, _ in guide), Counter(t for t, _, _ in roadmap)
    if g_tags != r_tags:
        out.append(f"W tags: GUIDE only {sorted((g_tags - r_tags).elements())}, "
                   f"ROADMAP only {sorted((r_tags - g_tags).elements())}")
    g_met = [row for _, met, row in guide if met]
    r_met = [row for _, met, row in roadmap if met]
    if len(g_met) != len(r_met):
        out.append(f"met: GUIDE {len(g_met)} {g_met}, "
                   f"ROADMAP {len(r_met)} {r_met}")
    return out


def test_the_two_data_gated_tables_agree():
    guide = guide_rows(GUIDE.read_text())
    roadmap = roadmap_rows(ROADMAP.read_text())
    assert disagreements(guide, roadmap) == []


def test_a_row_filled_on_one_side_only_fails():
    guide = guide_rows(GUIDE.read_text())
    roadmap = roadmap_rows(ROADMAP.read_text())
    _, _, row = next(r for r in roadmap if not r[1])
    moved = [(t, met or r == row, r) for t, met, r in roadmap]
    found = disagreements(guide, moved)
    assert len(found) == 1 and found[0].startswith("met:")
    assert row in found[0]
    dropped = disagreements(guide[1:], roadmap)
    assert any(d.startswith("rows:") for d in dropped)
    assert f"ROADMAP only ['{guide[0][0]}']" in next(
        d for d in dropped if d.startswith("W tags:"))
    stripped = [("?", met, r) for _, met, r in guide]
    assert any(d.startswith("no W tag:") and guide[0][2] in d
               for d in disagreements(stripped, [("?", m, r) for _, m, r in roadmap]))
