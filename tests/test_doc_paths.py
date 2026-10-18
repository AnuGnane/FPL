"""Every file path the docs name resolves to a file (holiday F-107).

ROADMAP candidate 7, in F-59's shape (``tests/test_guide_anchors.py`` does
this for in-page links): a path in backticks with a directory and a file
suffix, in the README, the GUIDE or the ROADMAP, names a file one of the
roots the docs write from holds. A probe on 2026-10-17 found every such path
resolving, so this holds a rule nothing held; a stale path is fixed in the
doc, never here. Untracked roots, struck-through text and template paths
(``{season}``, ``gw{N}``) are not read.

Holiday F-112 adds ``CLAUDE.md``, which names some forty repo paths no test
read. It also writes bare names after a directory (``set_pieces.py`` and
``test_odds.py`` in the orchestrator-only list, ``app.py`` after ``web/``),
which the path rule above never matches, so for ``CLAUDE.md`` alone a bare
name is resolved against the roots joined to every directory its own
paragraph or bullet names. The README, GUIDE and ROADMAP write bare names in
prose about many directories at once, so for them bare names stay unread.
The bare rule catches a deleted or renamed file, not one named under the
wrong directory: any root joined to any directory of the block may hold it.
"""

from __future__ import annotations

import re
from pathlib import Path

DOCS = [
    Path("README.md"),
    Path("docs/GUIDE.md"),
    Path("docs/superpowers/ROADMAP.md"),
    Path("CLAUDE.md"),
]
RULES = Path("CLAUDE.md")

# The roots the docs write paths from: `web/routers/meta.py` is under
# src/gaffer/, `specs/…` under docs/superpowers/, `src/kit/…` under frontend/.
ROOTS = ["", "src", "src/gaffer", "src/gaffer/web", "docs/superpowers", "frontend", "frontend/src"]

# CLAUDE.md's untracked and machine-local list: a path there that no root
# holds exists only on the Mac (`models/train.py` is src/gaffer's, so it is read).
UNTRACKED = (
    "data/", "models/", "reports/", "logs/", "src/gaffer/web/static/",
    ".superpowers/", ".claude/", "config.toml", "config.local.toml",
)

# One word of a backtick span: a path with a directory and a file suffix, an
# optional `:12-34` line range or `::test_name` node id, and trailing punctuation.
_PATH = re.compile(
    r"^(?:\./)?((?:[\w.-]+/)+[\w.-]+\.(?:py|md|sh|toml|ts|tsx|plist|yml|json|css))"
    r"(?::[\d-]+|::\S+)?[,.;:)]*$"
)


def _paths(text: str) -> list[str]:
    text = re.sub(r"~~.*?~~", "", text, flags=re.DOTALL)
    found = []
    for span in re.findall(r"`([^`\n]+)`", text):
        for word in span.split():
            match = _PATH.match(word)
            if match and "{" not in word:
                found.append(match.group(1))
    return found

# A bare file name (F-112), and the directory part of a word (`web/`, the
# `tests/` of `tests/test_x.py`) that a bare name in the same block may sit in.
_BARE = re.compile(r"^([\w-][\w.-]*\.(?:py|md|sh|toml|ts|tsx|plist|yml|json|css))[,.;:)]*$")
_DIR = re.compile(r"^(?:\./)?((?:[\w.-]+/)+)")


def _bare_unresolved(text: str, root: Path) -> list[str]:
    """Bare names no root, joined to a directory their block names, holds."""
    text = re.sub(r"~~.*?~~", "", text, flags=re.DOTALL)
    missing = []
    # A block is a paragraph or one bullet of a list (F-112).
    for block in re.split(r"\n\s*\n|\n(?=- )", text):
        words = [w for span in re.findall(r"`([^`\n]+)`", block) for w in span.split()]
        dirs = {""} | {m.group(1) for w in words if (m := _DIR.match(w))}
        for word in words:
            match = _BARE.match(word)
            if not match or match.group(1).startswith(UNTRACKED):
                continue
            name = match.group(1)
            if not any((root / base / d / name).exists() for base in ROOTS for d in dirs):
                missing.append(name)
    return missing


def _unresolved(text: str, root: Path) -> list[str]:
    return [
        path
        for path in _paths(text)
        if not any((root / base / path).exists() for base in ROOTS)
        and not path.startswith(UNTRACKED)
    ]


def test_the_docs_name_the_paths_this_rail_reads():
    guide = _paths(Path("docs/GUIDE.md").read_text())
    assert "scripts/v7b_replay.py" in guide, guide[:10]
    assert "models/predict.py" in _paths(Path("docs/superpowers/ROADMAP.md").read_text())
    assert "tests/test_odds.py" in _paths(Path("README.md").read_text())
    assert "tests/test_golden_board.py" in _paths(RULES.read_text())


def test_every_path_the_docs_name_resolves():
    unresolved = {
        str(doc): missing for doc in DOCS if (missing := _unresolved(doc.read_text(), Path(".")))
    }
    assert unresolved == {}


def test_every_bare_name_claude_md_writes_resolves():
    assert _bare_unresolved(RULES.read_text(), Path(".")) == []


def test_a_text_naming_a_file_the_root_lacks_fails_the_rail(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "here.py").write_text("")
    text = (
        "Run `scripts/here.py`, then `scripts/gone.py --fast`; ~~`scripts/old.py`~~,"
        " `reports/gw{N}.json`, `data/live/prices.json` and `web/gone.ts:12-14`."
    )
    assert _unresolved(text, tmp_path) == ["scripts/gone.py", "web/gone.ts"]


def test_a_claude_md_naming_a_file_its_directory_lacks_fails_the_rail(tmp_path):
    (tmp_path / "src" / "gaffer" / "web").mkdir(parents=True)
    (tmp_path / "src" / "gaffer" / "web" / "app.py").write_text("")
    text = (
        "- `src/gaffer/` — `gone.py`, `web/` (FastAPI: `app.py`, `jobs.py`).\n"
        "- `tests/` — ~~`old.py`~~ and `config.toml`.\n"
    )
    assert _bare_unresolved(text, tmp_path) == ["gone.py", "jobs.py"]
    assert _unresolved("Read `src/gaffer/web/gone.py`.", tmp_path) == [
        "src/gaffer/web/gone.py"
    ]
