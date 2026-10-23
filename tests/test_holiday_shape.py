"""``HOLIDAY.md``'s own shape, by rail (holiday F-139).

ROADMAP candidate 7, in F-123's shape (``tests/test_holiday_cites.py``).
Many runs a day write the queue and nothing checked it: an id could repeat
or skip, a ``Depends on`` could name a box that does not exist or one queued
after it, and a package could forget its gate or its trace. Under
"### Implementation" the ids run F-1, F-2, … with no gap or repeat; every
dependency names an earlier box; every unticked box says how it is gated
(``Gate:`` or ``No gate``) and what it traces to.
"""

from __future__ import annotations

import re
from pathlib import Path

HOLIDAY = Path(__file__).resolve().parents[1] / "HOLIDAY.md"

_BOX = re.compile(r"^- \[([ x])\] \*\*F-(\d+)\b(.*)$", re.MULTILINE)
_DEPENDS = re.compile(r"Depends on (F-\d+(?:(?:,? and |, | to )F-\d+)*)")
_LINK = re.compile(r"(,? and |, | to )?F-(\d+)")
_ANY_BOX = re.compile(r"^- \[", re.MULTILINE)
TRACES = ("ROADMAP", "GUIDE", "spec", "CLAUDE.md", "CONVENTIONS", "README",
          "Inbox")
# Whole words, so "specific" or "inspect" is no trace.
_TRACE = re.compile(r"\b(?:" + "|".join(map(re.escape, TRACES)) + r")\b")


def implementation(text: str) -> str:
    """The "### Implementation" section, up to the next ``## `` heading."""
    return text.split("### Implementation", 1)[1].split("\n## ", 1)[0]


def depends(body: str) -> set[int]:
    """Every id a box's ``Depends on`` names; ``F-a to F-b`` is the range."""
    ids: set[int] = set()
    for chain in _DEPENDS.findall(body):
        last = None
        for joint, n in _LINK.findall(chain):
            n = int(n)
            if joint == " to " and last is not None:
                ids.update(range(last, n + 1))
            ids.add(n)
            last = n
    return ids


def problems(text: str) -> list[str]:
    """Each broken rule, naming the box and the rule."""
    section = implementation(text)
    boxes = _BOX.findall(section)
    ids = [int(n) for _, n, _ in boxes]
    found = []
    if len(_ANY_BOX.findall(section)) != len(boxes):
        found.append("a box line is not in the `- [ ] **F-<n>` form, so no "
                     "rule reads it")
    for want, got in enumerate(ids, start=1):
        if got != want:
            found.append(f"F-{got}: expected F-{want} (ids run F-1, F-2, "
                         "… with no gap or repeat)")
            break
    known = set(ids)
    for mark, n, body in boxes:
        own = int(n)
        for dep in sorted(depends(body)):
            if dep not in known:
                found.append(f"F-{own}: depends on F-{dep}, which is no box")
            elif dep >= own:
                found.append(f"F-{own}: depends on F-{dep}, which is not "
                             "earlier")
        if mark == " ":
            if "Gate:" not in body and "No gate" not in body:
                found.append(f"F-{own}: an unticked box names no gate")
            if not _TRACE.search(body):
                found.append(f"F-{own}: an unticked box names no trace")
    return found


def test_the_holiday_queue_keeps_its_shape():
    assert problems(HOLIDAY.read_text(encoding="utf-8")) == []


def test_the_rail_bites_on_a_gap_a_forward_dependency_and_a_gateless_box(
        tmp_path):
    queue = tmp_path / "HOLIDAY.md"
    queue.write_text(
        "### Implementation\n\n"
        "- [x] **F-1 One.** ROADMAP. Gate: ruff.\n"
        "- [ ] **F-2 Two.** Depends on F-4. ROADMAP. Gate: ruff.\n"
        "- [ ] **F-4 Four.** GUIDE. Nothing runs.\n"
        "- [ ] **F-5 Five.** Depends on F-1 to F-9. Gate: ruff, specific.\n"
        "- [ ] F-6 Six, with no bold id.\n"
        "\n## Inbox\n\n- [ ] **F-7 Not a package.**\n",
        encoding="utf-8")
    found = problems(queue.read_text(encoding="utf-8"))
    assert any(f.startswith("F-4: expected F-3") for f in found)
    assert "F-2: depends on F-4, which is not earlier" in found
    assert "F-4: an unticked box names no gate" in found
    assert "F-5: depends on F-9, which is no box" in found
    assert "F-5: depends on F-5, which is not earlier" in found
    assert "F-5: an unticked box names no trace" in found
    assert any(f.startswith("a box line is not") for f in found)
    assert not any(f.startswith(("F-6", "F-7")) for f in found)


def test_a_dependency_range_expands_and_a_list_reads_every_id():
    assert depends("Depends on F-135 and F-136 to F-138 merged") == {
        135, 136, 137, 138}
    assert depends("Depends on F-76, F-78, F-79 and F-82") == {76, 78, 79, 82}
