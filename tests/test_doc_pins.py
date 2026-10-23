"""The pins the docs quote match the rails that hold them (holiday F-110).

ROADMAP candidate 7, in F-104's shape (``tests/test_readme_config.py``, the
docs read against the code). The three headline pins each have one home, a
bare assert in a rail file (``CLAUDE.md``'s pin table and the v12 meta-rail
say which). This rail reads each number from that home as text, by regex,
and never edits it; then it asserts the current-state lines quote the same
three numbers: ``CLAUDE.md``'s pin table, the README's rails paragraph,
the ROADMAP's "Where things stand" pins line and GUIDE §12's intro pins
line. The shipped cycles' history ("Pins 52 / 12 / 62" under a v19 block)
is not read: those lines record what held then.
"""

from __future__ import annotations

import re
from pathlib import Path

# The one home of each pin and the spelling of its bare assert there.
_RAILS = {
    "routes": (Path("tests/test_v11_degradation.py"), r"assert len\(paths\) == (\d+)"),
    "job kinds": (
        Path("tests/test_v12_w1_degradation.py"),
        r"assert len\(JOB_KINDS\) == (\d+)",
    ),
    "config": (Path("tests/test_v13_degradation.py"), r"assert len\(names\) == (\d+)"),
}

# Each doc's current-state line, as one regex with the three numbers in
# rails order (routes, job kinds, Config), and the section it is read from:
# (start heading regex, or None for the whole file).
_W = r"\s+"
_DOCS = {
    "CLAUDE.md": (
        None,
        (r"\| API routes \| (\d+) \|.*?\n\| `JOB_KINDS` \| (\d+) \|.*?\n"
         r"\| `Config` fields \| (\d+) \|"),
    ),
    "README.md": (
        r"^## Tests",
        (rf"API{_W}routes{_W}\((\d+)\),{_W}job{_W}kinds{_W}\((\d+)\),"
         rf"{_W}`Config`{_W}fields{_W}\((\d+)\)"),
    ),
    "docs/superpowers/ROADMAP.md": (
        r"^## Where things stand",
        (rf"Pins:{_W}routes{_W}(\d+){_W}\(`tests/test_v11_degradation\.py`\),"
         rf"{_W}job{_W}kinds{_W}(\d+){_W}\(`tests/test_v12_w1_degradation\.py`\),"
         rf"{_W}`Config`{_W}(\d+){_W}\(`tests/test_v13_degradation\.py`\)"),
    ),
    "docs/GUIDE.md": (
        r"^## 12\.",
        (rf"Pins:{_W}routes{_W}(\d+){_W}\(`tests/test_v11_degradation\.py`\),"
         rf"{_W}job{_W}kinds{_W}(\d+){_W}\(`tests/test_v12_w1_degradation\.py`\),"
         rf"{_W}`Config`{_W}(\d+){_W}\(`tests/test_v13_degradation\.py`\)"),
    ),
}


def _rail_pins() -> tuple[int, int, int]:
    out = []
    for name, (path, pattern) in _RAILS.items():
        found = re.findall(pattern, path.read_text())
        assert len(found) == 1, f"{path}: {len(found)} matches for the {name} pin"
        out.append(int(found[0]))
    return tuple(out)


def _section(text: str, heading: str | None) -> str:
    """The text from ``heading`` to the next ``## `` heading (all if None)."""
    if heading is None:
        return text
    m = re.search(heading, text, re.MULTILINE)
    assert m, f"no heading matching {heading!r}"
    rest = text[m.end():]
    nxt = re.search(r"^## ", rest, re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def doc_pin_mismatch(
    name: str, text: str, rails: tuple[int, int, int]
) -> str | None:
    """None when ``text`` (the doc ``name``) quotes ``rails``; else why not."""
    heading, pattern = _DOCS[name]
    m = re.search(pattern, _section(text, heading), re.DOTALL)
    if m is None:
        return f"{name}: its pins line was not found"
    quoted = tuple(int(g) for g in m.groups())
    if quoted != rails:
        return f"{name} quotes routes/job kinds/Config {quoted}, the rails hold {rails}"
    return None


def test_the_rails_each_hold_their_pin_once():
    assert all(n > 0 for n in _rail_pins())


def test_the_docs_quote_the_pins_the_rails_hold():
    rails = _rail_pins()
    problems = [
        p
        for name in _DOCS
        if (p := doc_pin_mismatch(name, Path(name).read_text(), rails)) is not None
    ]
    assert problems == []


def test_a_readme_quoting_a_wrong_route_count_fails():
    rails = _rail_pins()
    wrong = (
        "## Tests\n\nthe counts a later change must not move silently - API routes\n"
        f"({rails[0] + 1}), job kinds ({rails[1]}), `Config` fields ({rails[2]}), the files\n"
    )
    problem = doc_pin_mismatch("README.md", wrong, rails)
    assert problem is not None and "README.md" in problem
