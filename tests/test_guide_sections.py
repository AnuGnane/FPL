"""Every GUIDE section the docs cite by ``§`` is a heading (holiday F-137).

ROADMAP candidate 7, in F-107's and F-108's shape (``tests/test_doc_paths.py``
and ``tests/test_guide_anchors.py``, the docs' paths and links read against
what they point at). The docs cite GUIDE sections as ``GUIDE §12.5`` and
``docs/GUIDE.md §9``, and the GUIDE cites its own as a bare ``§12.4``;
nothing failed when a section was renumbered and a citation went nowhere.

Outside the GUIDE only a ``§`` whose preceding word is ``GUIDE`` or
``GUIDE.md`` is read: the other docs cite spec sections far more often.
Inside the GUIDE every ``§`` is read unless the word before it marks a spec
citation (a cycle id, ``spec``, ``design``, ``plan``, ``CONVENTIONS``, a
possessive of the first two, or a ``.md`` path in backticks); those name
spec files, which ``tests/test_roadmap_specs.py`` holds. A dangling
citation is fixed in the doc, never by adding a heading.
"""

from __future__ import annotations

import re
from pathlib import Path

GUIDE = Path("docs/GUIDE.md")
OTHER_DOCS = (
    Path("README.md"),
    Path("CLAUDE.md"),
    Path("HOLIDAY.md"),
    Path("docs/superpowers/ROADMAP.md"),
    Path("docs/superpowers/CONVENTIONS.md"),
    Path("docs/superpowers/specs/2026-10-07-v20-model-cycle-design.md"),
)

_SECTION = r"§\s?(\d+(?:\.\d+)?)"
_GUIDE_CITE = re.compile(r"GUIDE(?:\.md)?`?\s+" + _SECTION)
_ANY_CITE = re.compile(r"(\S*)\s*" + _SECTION)
_SPEC_MARK = re.compile(
    r"v\d+[a-z]?\d*|W\d+|spec|design|plan|CONVENTIONS|spec's|design's|`[^`]*\.md`"
)


def guide_sections(text: str) -> set[str]:
    """The numbers of the GUIDE's ``## N.`` and ``### N.M`` headings."""
    sections = set()
    for line in text.splitlines():
        if m := re.match(r"## (\d+)\. ", line):
            sections.add(m.group(1))
        elif m := re.match(r"### (\d+\.\d+) ", line):
            sections.add(m.group(1))
    return sections


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def dangling_citations(name: str, text: str, sections: set[str], *, is_guide: bool) -> list[str]:
    """Each ``§`` citation of a GUIDE section that is not a heading, as
    ``file:line §N``."""
    found = []
    if is_guide:
        for m in _ANY_CITE.finditer(text):
            word = m.group(1).lstrip("(")
            if not word:
                before = text[: m.start()].split()
                word = before[-1].lstrip("(") if before else ""
            if _SPEC_MARK.fullmatch(word.rstrip(",;:")):
                continue
            if m.group(2) not in sections:
                found.append(f"{name}:{_line(text, m.start(2))} §{m.group(2)}")
    else:
        for m in _GUIDE_CITE.finditer(text):
            if m.group(1) not in sections:
                found.append(f"{name}:{_line(text, m.start(1))} §{m.group(1)}")
    return found


def test_every_cited_guide_section_is_a_heading():
    sections = guide_sections(GUIDE.read_text())
    assert {"1", "12", "12.0", "12.5", "13"} <= sections
    dangling = dangling_citations(str(GUIDE), GUIDE.read_text(), sections, is_guide=True)
    for doc in OTHER_DOCS:
        dangling += dangling_citations(str(doc), doc.read_text(), sections, is_guide=False)
    assert dangling == [], "GUIDE sections cited but not headings:\n" + "\n".join(dangling)


def test_a_citation_of_a_missing_section_fails(tmp_path):
    sections = guide_sections("## 1. What gaffer is\n\n### 1.2 More\n")
    doc = tmp_path / "doc.md"
    doc.write_text("See GUIDE §1.2,\nthen `docs/GUIDE.md` §99 and v20 spec §6.1.\n")
    assert dangling_citations("doc.md", doc.read_text(), sections, is_guide=False) == [
        "doc.md:2 §99"
    ]
    guide = "## 1. What gaffer is\n\nAs §99 says, and as v20 §99 and spec §99 do not.\n"
    assert dangling_citations("GUIDE.md", guide, {"1"}, is_guide=True) == ["GUIDE.md:3 §99"]
