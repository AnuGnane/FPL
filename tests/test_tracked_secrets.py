"""The secrets rule, by rail (holiday F-138).

``CLAUDE.md`` "Secrets" runs the key grep by hand before a push, and the
open incident (ROADMAP "Where things stand", CONVENTIONS §8) is a key value
that reached a committed plan document. This widens the range-scoped
``test_the_branch_banks_no_data_and_no_config`` rails of the v12 W3 and W4
files to the whole tree: no tracked text file assigns a key-shaped value to
``api_key``, no machine-local config is tracked, and every directory
``CLAUDE.md``'s Layout calls untracked stays ignored. The value itself is
never known here, so the rail reads the shape (a long hex run), not the key.

Git is required: a missing ``git`` fails the rail rather than skipping it,
so the GUIDE's skip table (F-133) gains no row.
"""

from __future__ import annotations

import re
import secrets
import subprocess
from pathlib import Path

_ASSIGN = re.compile(r"""api_key\s*=\s*["']([^"']+)""")
_HEX = re.compile(r"[0-9a-f]{20,}")

# Run from the repo root wherever pytest starts, so a run from tests/ scans
# the whole tree, not its own subtree.
_ROOT = Path(__file__).resolve().parents[1]

# v17c §2.3: the golden board's fixture, written from golden_config() with
# no [odds] table; .gitignore un-ignores it by name.
_FIXTURE_CONFIG = "tests/data/golden_board/config.toml"

# CLAUDE.md "Layout": one made-up path under each untracked directory, and
# the two config files.
_IGNORED = ["data/raw/x", "models/x.joblib", "reports/x.json", "logs/x",
            "src/gaffer/web/static/x", ".claude/x", ".superpowers/x",
            "config.toml", "config.local.toml"]


def key_shaped(text: str) -> list[str]:
    """Each uncommented ``api_key`` value that is 20 or more characters and
    carries a 20-long hex run, the shape of the odds key."""
    hits = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        for value in _ASSIGN.findall(line):
            if len(value) >= 20 and _HEX.search(value):
                hits.append(line.strip())
    return hits


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          cwd=_ROOT)


def _tracked() -> list[str]:
    done = _git("ls-files")
    assert done.returncode == 0, done.stderr
    return done.stdout.splitlines()


def test_the_matcher_bites_on_a_hex_value_and_passes_a_commented_line():
    value = secrets.token_hex(16)
    assert key_shaped(f'api_key = "{value}"\n') == [f'api_key = "{value}"']
    assert key_shaped(f"odds_api_key='{'a' * 32}'\n")
    assert key_shaped(f'# api_key = "{value}"\n') == []
    assert key_shaped('api_key = "abc123"\n') == []
    assert key_shaped('api_key = "get one free at the-odds-api.com"\n') == []


def test_no_tracked_file_carries_a_key_shaped_value():
    found = {}
    for path in _tracked():
        try:
            with open(_ROOT / path, encoding="utf-8") as f:
                text = f.read()
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue  # a binary, or a path deleted in the working tree
        if hits := key_shaped(text):
            found[path] = len(hits)
    assert not found, f"key-shaped api_key values (count only): {found}"


def test_no_machine_local_config_is_tracked():
    configs = [p for p in _tracked()
               if p.rsplit("/", 1)[-1] in ("config.toml", "config.local.toml")]
    assert configs == [_FIXTURE_CONFIG], configs


def test_the_machine_local_paths_stay_ignored():
    missed = [p for p in _IGNORED if _git("check-ignore", "-q", p).returncode]
    assert not missed, f"no longer ignored: {missed}"
