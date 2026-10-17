"""Every file path the docs name resolves to a file (holiday F-107).

ROADMAP candidate 7, in F-59's shape (``tests/test_guide_anchors.py`` does
this for in-page links): a path in backticks with a directory and a file
suffix, in the README, the GUIDE or the ROADMAP, names a file one of the
roots the docs write from holds. A probe on 2026-10-17 found every such path
resolving, so this holds a rule nothing held; a stale path is fixed in the
doc, never here. Untracked roots, struck-through text and template paths
(``{season}``, ``gw{N}``) are not read.
"""

from __future__ import annotations

import re
from pathlib import Path

DOCS = [Path("README.md"), Path("docs/GUIDE.md"), Path("docs/superpowers/ROADMAP.md")]

# The roots the docs write paths from: `web/routers/meta.py` is under
# src/gaffer/, `specs/…` under docs/superpowers/, `src/kit/…` under frontend/.
ROOTS = ["", "src", "src/gaffer", "src/gaffer/web", "docs/superpowers", "frontend", "frontend/src"]

# CLAUDE.md's untracked and machine-local list: a path there exists only on the Mac.
UNTRACKED = (
    "data/", "models/", "reports/", "logs/", "src/gaffer/web/static/",
    ".superpowers/", ".claude/", "config.toml", "config.local.toml",
)

# One word of a backtick span: a path with a directory and a file suffix, an
# optional `:12-34` line range and trailing punctuation after it.
_PATH = re.compile(
    r"^(?:\./)?((?:[\w.-]+/)+[\w.-]+\.(?:py|md|sh|toml|ts|tsx|plist|yml|json|css))"
    r"(?::[\d-]+)?[,.;:)]*$"
)


def _paths(text: str) -> list[str]:
    text = re.sub(r"~~.*?~~", "", text, flags=re.DOTALL)
    found = []
    for span in re.findall(r"`([^`\n]+)`", text):
        for word in span.split():
            match = _PATH.match(word)
            if match and "{" not in word and not match.group(1).startswith(UNTRACKED):
                found.append(match.group(1))
    return found


def _unresolved(text: str, root: Path) -> list[str]:
    return [
        path
        for path in _paths(text)
        if not any((root / base / path).exists() for base in ROOTS)
    ]


def test_the_docs_name_the_paths_this_rail_reads():
    guide = _paths(Path("docs/GUIDE.md").read_text())
    assert "scripts/v7b_replay.py" in guide, guide[:10]
    assert not any(path.startswith("data/") for path in guide)


def test_every_path_the_docs_name_resolves():
    unresolved = {
        str(doc): missing for doc in DOCS if (missing := _unresolved(doc.read_text(), Path(".")))
    }
    assert unresolved == {}


def test_a_text_naming_a_file_the_root_lacks_fails_the_rail(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "here.py").write_text("")
    text = "Run `scripts/here.py`, then `scripts/gone.py --fast`; ~~`scripts/old.py`~~."
    assert _unresolved(text, tmp_path) == ["scripts/gone.py"]
