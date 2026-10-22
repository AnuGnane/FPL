"""Every script outside the archive is named in the GUIDE (holiday F-87).

ROADMAP candidate 7 and ``CLAUDE.md``'s layout list: ``scripts/`` holds the
replay drivers and the cycles' gate drivers, and v18g moved the ones nothing
runs to ``scripts/archive/``. A script neither named in ``docs/GUIDE.md``
nor archived is one a reader cannot find a reason for, which is how
eighteen piled up before F-87. No allowlist: a new script is named where
its kin are, or it goes to the archive. The launchd plists are §7's table's
by label, and ``__pycache__`` is the interpreter's.

F-180 adds the converse for the archive: every file under
``scripts/archive/`` is on its README's bullet list, and every name on that
list exists there, so a driver dropped in unrecorded or a line outliving its
file fails. The README's prose names live scripts too; only bullets count.
"""

from __future__ import annotations

import re
from pathlib import Path

GUIDE = Path("docs/GUIDE.md")
SCRIPTS = Path("scripts")
ARCHIVE = SCRIPTS / "archive"
README = ARCHIVE / "README.md"

# A bullet opens with the archived file's name in backticks (F-180).
_BULLET = re.compile(r"^- `([^`]+)`", re.M)


def _live_scripts() -> list[Path]:
    """Files under ``scripts/`` that are neither archived, a plist nor bytecode."""
    return sorted(
        p
        for p in SCRIPTS.rglob("*")
        if p.is_file()
        and "archive" not in p.relative_to(SCRIPTS).parts
        and "__pycache__" not in p.parts
        and p.suffix != ".plist"
    )


def test_there_are_live_scripts_to_check():
    assert len(_live_scripts()) > 20, _live_scripts()


def test_every_script_outside_the_archive_is_named_in_the_guide():
    text = GUIDE.read_text()
    # By its path, not its bare name: a new `scripts/probe.py` must not pass on
    # `scripts/v7b_probe.py`'s mention (F-87 review).
    unnamed = [
        str(p)
        for p in _live_scripts()
        if f"scripts/{p.relative_to(SCRIPTS).as_posix()}" not in text
    ]
    assert unnamed == [], unnamed


def _archived() -> list[str]:
    """Files under ``scripts/archive/`` other than its README and bytecode."""
    return sorted(
        p.relative_to(ARCHIVE).as_posix()
        for p in ARCHIVE.rglob("*")
        if p.is_file() and p != README and "__pycache__" not in p.parts
    )


def _bulleted(readme: str) -> list[str]:
    return sorted(_BULLET.findall(readme))


def test_every_archived_file_is_on_the_readme_list():
    files = _archived()
    assert files, "no archived file found; the scan is broken"
    named = set(_bulleted(README.read_text()))
    assert [f for f in files if f not in named] == []


def test_every_name_on_the_readme_list_is_an_archived_file():
    files = set(_archived())
    assert [n for n in _bulleted(README.read_text()) if n not in files] == []


def test_only_the_readme_bullets_count_as_names():
    readme = (
        "Prose names `scripts/replay_pair.sh`, a live script.\n\n"
        "- `a.py` — the spec's §G1.\n"
        "- `b.sh` — the spec's §G3, cites `c.py` in passing.\n"
    )
    assert _bulleted(readme) == ["a.py", "b.sh"]
