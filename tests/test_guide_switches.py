"""The GUIDE names every v20 switch Health lists (holiday F-111).

ROADMAP candidate 7, in F-96's shape (``tests/test_guide_jobs.py``): Model →
Health lists each shipped-off arm's switch (holiday F-30's
``arm_switches()``), and GUIDE §5's *Health* bullet names them so a reader
can trace a screenshot's row to its constant. A switch added to Health
without its name in that bullet is a row the GUIDE never explains, so it
fails here. Membership only, in backticks: the count is Health's business.
"""

from __future__ import annotations

import re
from pathlib import Path

from gaffer.web.routers.meta import arm_switches

GUIDE = Path("docs/GUIDE.md")


def _health_bullet(text: str) -> str:
    """GUIDE §5's ``- *Health*:`` bullet, up to the next bullet."""
    section = re.search(r"^## 5\..*?(?=^## 6\.)", text, re.MULTILINE | re.DOTALL)
    assert section, "GUIDE §5 not found"
    bullet = re.search(r"^- \*Health\*:.*?(?=^- )", section.group(0), re.MULTILINE | re.DOTALL)
    assert bullet, "GUIDE §5 has no *Health* bullet"
    return bullet.group(0)


def unnamed_switches(bullet: str, names: list[str]) -> list[str]:
    """The switch names ``bullet`` does not carry in backticks."""
    return [name for name in names if f"`{name}`" not in bullet]


def test_the_guide_names_every_switch_health_lists():
    names = [s.name for s in arm_switches()]
    assert names, "arm_switches() returned nothing to check"
    assert unnamed_switches(_health_bullet(GUIDE.read_text()), names) == []


def test_a_health_bullet_missing_a_switch_fails():
    names = [s.name for s in arm_switches()]
    bullet = _health_bullet(GUIDE.read_text()).replace(f"`{names[0]}`", "")
    assert unnamed_switches(bullet, names) == [names[0]]
