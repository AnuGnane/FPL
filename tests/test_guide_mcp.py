"""GUIDE §8 names every tool ``gaffer mcp`` serves (holiday F-114).

ROADMAP candidate 7, in F-100's shape (``tests/test_guide_commands.py``): the
``gaffer mcp`` bullet said "Six read tools" and named none. The names are the
keys of ``mcp_server.TOOLS``, the dict ``build_server`` registers; importing
it needs no ``mcp`` package (that import sits inside ``build_server``) and
starts no server. Membership against the GUIDE; the one count is the walk's
six, the number the bullet itself states.
"""

from __future__ import annotations

from gaffer.mcp_server import TOOLS
from tests.test_guide_commands import _guide_section


def _unnamed(names: list[str], text: str) -> list[str]:
    return [name for name in names if f"`{name}`" not in text]


def test_the_walk_finds_the_six_tools_this_rail_reads():
    names = list(TOOLS)
    assert len(names) == 6, names
    assert "projections" in names and "health" in names, names


def test_every_mcp_tool_is_named_in_guide_section_eight():
    assert _unnamed(list(TOOLS), _guide_section()) == []


def test_a_section_with_one_tool_unnamed_fails_the_rail():
    section = _guide_section()
    assert "`ledger`" in section
    assert _unnamed(list(TOOLS), section.replace("`ledger`", "ledger")) == [
        "ledger"]
