"""Every script outside the archive is named in the GUIDE (holiday F-87).

ROADMAP candidate 7 and ``CLAUDE.md``'s layout list: ``scripts/`` holds the
replay drivers and the cycles' gate drivers, and v18g moved the ones nothing
runs to ``scripts/archive/``. A script neither named in ``docs/GUIDE.md``
nor archived is one a reader cannot find a reason for, which is how
eighteen piled up before F-87. No allowlist: a new script is named where
its kin are, or it goes to the archive. The launchd plists are §7's table's
by label, and ``__pycache__`` is the interpreter's.
"""

from __future__ import annotations

from pathlib import Path

GUIDE = Path("docs/GUIDE.md")
SCRIPTS = Path("scripts")


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
    unnamed = [str(p) for p in _live_scripts() if p.name not in text]
    assert unnamed == [], unnamed
