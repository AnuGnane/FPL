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

from tests.test_guide_readings import _prefixes, _rows, _script, ap

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

# Holiday F-63: the v20 arms' scripts are not in the GUIDE's table; the
# appendix collects their lines by its own pattern (``_READING``), and each
# script's docstring names what it prints.
_V20 = [
    ("scripts/v20b_head.py", ["V20B_HEAD"]),
    ("scripts/v20c_head.py", ["V20C_HEAD"]),
    ("scripts/v20d_brier.py", ["V20D_BRIER"]),
    ("scripts/v20d_runs.py", ["V20D_RUN", "V20D_ROW"]),
]

# One per Thursday run read, so a cold tree, with none to read, need not
# show it (F-63, as _PER_GAMEWEEK above).
_PER_RUN = {"V20D_RUN"}


def test_the_table_gives_this_file_scripts_to_run():
    assert len(_TABLE) >= 11
    assert _SENTENCE_ON_COLD in dict(_TABLE)


def test_every_v20_prefix_is_one_the_appendix_collects():
    for script, prefixes in _V20:
        assert Path(ROOT / script).is_file(), script
        for prefix in prefixes:
            assert ap._READING.match(prefix), prefix


def _run_cold(script: str, tmp_path: Path) -> subprocess.CompletedProcess:
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
    return done


def _assert_keyed(script: str, prefixes: list[str], stdout: str) -> None:
    keys = [m.group(1) for line in stdout.splitlines() if (m := _KEY.match(line))]
    assert set(keys) <= set(prefixes), (script, keys)
    assert set(keys) - _PER_GAMEWEEK - _PER_RUN, (script, stdout)


@pytest.mark.parametrize(("script", "prefixes"), _TABLE, ids=[s for s, _ in _TABLE])
def test_a_reading_script_on_a_cold_tree_prints_its_line_and_exits_clean(
    script, prefixes, tmp_path
):
    done = _run_cold(script, tmp_path)
    if script == _SENTENCE_ON_COLD:
        return
    _assert_keyed(script, prefixes, done.stdout)


@pytest.mark.parametrize(("script", "prefixes"), _V20, ids=[s for s, _ in _V20])
def test_a_v20_script_on_a_cold_tree_prints_its_line_and_exits_clean(
    script, prefixes, tmp_path
):
    _assert_keyed(script, prefixes, _run_cold(script, tmp_path).stdout)
