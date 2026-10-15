"""Every reading script, run on a fresh clone, prints its line and exits clean
(holiday F-53).

Each holiday reading package promised that a missing log prints the line
with a reason, never a traceback, but each was tested only through its own
``main`` with patched paths. The night shift runs them as
``uv run python scripts/<name>.py``, so this runs each the same way: the
interpreter on the script's absolute path, from an empty working directory
(the scripts reach ``data/`` and ``reports/`` through working-directory
paths, so the tree is cold on any machine, the Mac included), with the
proxies pointed at a closed port so a fetch fails fast instead of passing.
The scripts and their prefixes come from the GUIDE's readings table, which
``tests/test_guide_readings.py`` already parses.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_guide_readings import _prefixes, _rows, _script

ROOT = Path(__file__).resolve().parent.parent

# v20 spec §3: the appendix collects the others' lines and prints none of its own.
_COLLECTOR = "scripts/v20_appendix.py"

# Printed once per gameweek read, so a cold tree, with none to read, need not
# show them (F-53).
_PER_GAMEWEEK = {"WALK_HITS_GW", "PCS_WINDOW", "PRESSER_GW", "NEWS_SHADOW_GW"}

# On a cold tree this prints a sentence by design, not a BACKFILL_RANK line;
# it is held to exit 0 and no traceback only (F-53).
_SENTENCE_ON_COLD = "scripts/backfill_overall_rank.py"

# A line's opening upper-case token, matched whole: PCS_WINDOWS is not PCS_WINDOW.
_KEY = re.compile(r"^([A-Z][A-Z0-9_]+)(?![A-Za-z0-9_])")

_CLOSED_PORT = "http://127.0.0.1:9"

_TABLE = [
    (_script(row[0]), _prefixes(row[1]))
    for row in _rows()
    if _script(row[0]) != _COLLECTOR
]


def test_the_table_gives_this_file_scripts_to_run():
    assert len(_TABLE) >= 11
    assert _SENTENCE_ON_COLD in dict(_TABLE)


@pytest.mark.parametrize(("script", "prefixes"), _TABLE, ids=[s for s, _ in _TABLE])
def test_a_reading_script_on_a_cold_tree_prints_its_line_and_exits_clean(
    script, prefixes, tmp_path
):
    env = {
        **os.environ,
        "HTTP_PROXY": _CLOSED_PORT,
        "HTTPS_PROXY": _CLOSED_PORT,
        "http_proxy": _CLOSED_PORT,
        "https_proxy": _CLOSED_PORT,
    }
    env.pop("NO_PROXY", None)
    env.pop("no_proxy", None)
    done = subprocess.run(
        [sys.executable, str(ROOT / script)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
    assert "Traceback" not in done.stderr, done.stderr
    if script == _SENTENCE_ON_COLD:
        return
    keys = [m.group(1) for line in done.stdout.splitlines() if (m := _KEY.match(line))]
    assert set(keys) <= set(prefixes), (script, keys)
    assert set(keys) - _PER_GAMEWEEK, (script, done.stdout)
