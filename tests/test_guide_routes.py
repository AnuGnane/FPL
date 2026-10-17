"""Every API route is named in GUIDE §5 (holiday F-102).

ROADMAP candidate 7, in F-87's and F-100's shape (``tests/test_guide_commands.py``):
§5 walked the hubs but named almost none of the paths behind them, so a new
route could go unnamed. The paths are read the way
``tests/test_v11_degradation.py`` reads them. Membership only, no count: the
total is pinned in the v11 file alone (the meta-rail,
``tests/test_v12_w1_degradation.py``).
"""

from __future__ import annotations

from pathlib import Path

from gaffer.web.app import create_app

GUIDE = Path("docs/GUIDE.md")


def _paths() -> list[str]:
    return list(create_app().openapi()["paths"])


def _section_five() -> str:
    text = GUIDE.read_text()
    head = text.index("## 5. ")
    return text[head:text.index("\n## 6. ", head)]


def _unnamed(paths: list[str], text: str) -> list[str]:
    # In backticks exactly as OpenAPI spells it, so `/api/plan` alone does not
    # stand in for `/api/plan/{gw}` (F-102).
    return [path for path in paths if f"`{path}`" not in text]


def test_openapi_lists_the_paths_this_rail_reads():
    paths = _paths()
    assert "/api/plan/{gw}" in paths and "/api/ask" in paths, paths


def test_every_api_route_is_named_in_guide_section_five():
    assert _unnamed(_paths(), _section_five()) == []


def test_a_section_five_missing_one_route_row_fails_the_rail():
    section = _section_five()
    row = next(line for line in section.splitlines()
               if line.startswith("| `/api/pens`"))
    assert _unnamed(_paths(), section.replace(row + "\n", "")) == ["/api/pens"]
