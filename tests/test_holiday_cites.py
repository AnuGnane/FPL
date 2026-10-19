"""Every holiday id the docs cite is a box in HOLIDAY.md (holiday F-123).

ROADMAP candidate 7, in F-110's shape (``tests/test_doc_pins.py``, the docs
read against their source as text). The README, the GUIDE, the ROADMAP,
the v20 spec, and since F-134 ``CLAUDE.md`` and
``docs/superpowers/CONVENTIONS.md`` cite ``F-<n>`` as the record of what closed a line and where a
script came from; nothing checked that the id exists or is done. Each cited
id must be a box in ``HOLIDAY.md``, and an id cited where the GUIDE says a
line is closed (a struck ``~~…~~`` span in §12.4 or §12.5, or a row of the
§12.5 readings table) must be a ticked one. An id cited as still open, as
ROADMAP "Where things stand" names F-92, is not read for its tick.
"""

from __future__ import annotations

import re
from pathlib import Path

DOCS = [Path("README.md"), Path("docs/GUIDE.md"),
        Path("docs/superpowers/ROADMAP.md"),
        Path("docs/superpowers/specs/2026-10-07-v20-model-cycle-design.md"),
        # F-134: CLAUDE.md cites F-74 and F-82; CONVENTIONS.md is where a
        # replay package's id lands next (F-126's shape applied here).
        Path("CLAUDE.md"), Path("docs/superpowers/CONVENTIONS.md")]
HOLIDAY = Path("HOLIDAY.md")

_ID = re.compile(r"\bF-(\d+)\b")
_BOX = re.compile(r"^- \[([ x])\] \*\*F-(\d+)\b", re.M)


def boxes(text: str) -> dict[int, bool]:
    """Each box's id and whether it is ticked."""
    return {int(n): mark == "x" for mark, n in _BOX.findall(text)}


def cited(text: str) -> set[int]:
    """Every ``F-<n>`` in ``text``, with or without the ``holiday`` prefix."""
    return {int(n) for n in _ID.findall(text)}


def struck_cites(text: str) -> set[int]:
    """The ids in each struck span and the parenthetical right after it.

    The GUIDE strikes the line and names what closed it just outside the
    tildes, ``~~the web button banking prices~~ (holiday F-3)``, so the span
    alone would read nothing.
    """
    out: set[int] = set()
    for span, after in re.findall(r"~~(.+?)~~(\s*\([^)]*\))?", text, re.S):
        out |= cited(span) | cited(after)
    return out


def closed_cites(guide: str) -> set[int]:
    """The ids GUIDE §12.4 and §12.5 cite as closed.

    A struck span records a line closed; a readings-table row records a
    script that shipped. Both must point at a ticked box.
    """
    section = re.search(r"^### 12\.4 .*?(?=^## 13\.)", guide, re.M | re.S)
    assert section, "GUIDE §12.4 to §12.5 not found"
    body = section.group(0)
    out: set[int] = set()
    out |= struck_cites(body)
    readings = re.search(r"^#### The readings\n.*?(?=^#|\Z)", body,
                         re.M | re.S)
    assert readings, "GUIDE §12.5 has no readings table"
    for row in re.findall(r"^\|.*\|$", readings.group(0), re.M):
        out |= cited(row)
    return out


def unboxed(texts: list[str], box: dict[int, bool]) -> list[int]:
    """The cited ids that are no box at all."""
    return sorted(set().union(*map(cited, texts)) - set(box))


def unticked(guide: str, box: dict[int, bool]) -> list[int]:
    """The ids cited as closed whose box is not ticked."""
    return sorted(n for n in closed_cites(guide) if not box.get(n, False))


def test_every_cited_holiday_id_is_a_box():
    box = boxes(HOLIDAY.read_text())
    assert box, "HOLIDAY.md has no boxes"
    assert unboxed([p.read_text() for p in DOCS], box) == []


def test_every_id_cited_as_closed_is_ticked():
    box = boxes(HOLIDAY.read_text())
    guide = Path("docs/GUIDE.md").read_text()
    assert struck_cites(guide), "no struck cites read: the regex went stale"
    assert closed_cites(guide), "no closed cites read: the regexes went stale"
    assert unticked(guide, box) == []


def test_the_rail_bites_on_an_unknown_id_and_an_open_one():
    box = boxes(HOLIDAY.read_text())
    assert unboxed(["closed by holiday F-999"], box) == [999]
    open_id = min(n for n, ticked in box.items() if not ticked)
    done_id = min(n for n, ticked in box.items() if ticked)
    guide = (f"### 12.4 Open\n~~a line~~ (holiday F-{open_id}) and "
             f"F-{done_id}\n### 12.5 Not planned\n#### The readings\n"
             "| `scripts/x.py` (holiday F-999) | X |\n## 13. End\n")
    assert unticked(guide, box) == [open_id, 999]
