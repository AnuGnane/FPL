"""scripts/c1_replay_cover.py, what the two logs cover for C1's replay half
(holiday F-79).

Synthetic logs: a season the shadow log covers from GW5 to GW38, one with a
gap, a season still in progress and no log at all, so each branch of the
rule is seen to bite.
"""

from __future__ import annotations

import json
import sys

import pandas as pd

from gaffer.data import store
from gaffer.news_shadow import SHADOW_PATH

sys.path.insert(0, "scripts")

import c1_replay_cover  # noqa: E402 — scripts/ is not a package; the path insert must come first


def _log(season: str, gws) -> pd.DataFrame:
    return pd.DataFrame({"season": season, "gw": list(gws), "code": 1})


FULL = _log("2025-26", range(1, 39))
GAPPED = _log("2025-26", [gw for gw in range(5, 39) if gw != 20])
RUNNING = _log("2026-27", range(5, 9))


def test_a_fully_covered_replayable_season_makes_the_replay_runnable():
    out = c1_replay_cover.cover_reading(FULL, None, ["2025-26"], "2026-27")
    cell = out["shadow"]["2025-26"]
    assert cell["covered"] == cell["of"] == 34 and cell["share"] == 1.0
    assert cell["rows"] == 38 and (cell["gw_min"], cell["gw_max"]) == (1, 38)
    assert out["qualifying"] == ["2025-26"]
    assert out["verdict"].startswith("runnable")
    assert out["reason"] is None


def test_a_covered_season_the_replay_cannot_take_does_not_qualify():
    out = c1_replay_cover.cover_reading(FULL, None, ["2024-25"], "2026-27")
    assert out["qualifying"] == []
    assert out["first_candidate"] == "2025-26"
    assert out["verdict"].startswith("the replay half waits")


def test_a_gap_is_named_and_moves_the_candidate_to_the_next_season():
    out = c1_replay_cover.cover_reading(GAPPED, None, ["2025-26"], "2025-26")
    cell = out["shadow"]["2025-26"]
    assert cell["missing"] == [20] and cell["covered"] == 33
    assert out["qualifying"] == []
    assert out["first_candidate"] == "2026-27"
    assert "2026-27 is the first that could qualify" in out["verdict"]


def test_a_season_in_progress_with_no_gap_is_the_candidate():
    log = pd.concat([GAPPED, RUNNING], ignore_index=True)
    out = c1_replay_cover.cover_reading(log, RUNNING, ["2025-26"], "2026-27")
    assert out["first_candidate"] == "2026-27"
    assert out["snapshot"]["2026-27"]["covered"] == 4


def test_no_log_at_all_names_the_current_season_and_a_reason():
    out = c1_replay_cover.cover_reading(None, None, [], "2026-27")
    assert out["shadow"] == {} and out["snapshot"] == {}
    assert out["first_candidate"] == "2026-27"
    assert out["reason"] == ("no news shadow log and no availability "
                             "snapshots banked")


def test_main_on_an_empty_store_prints_one_line_and_exits_clean(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    assert c1_replay_cover.main() == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1 and lines[0].startswith("C1_COVER ")
    payload = json.loads(lines[0].removeprefix("C1_COVER "))
    assert payload["shadow"] == {} and payload["reason"]


def test_main_reads_a_banked_shadow_log(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    store.save(RUNNING, SHADOW_PATH)
    assert c1_replay_cover.main() == 0
    payload = json.loads(capsys.readouterr().out.strip()
                         .removeprefix("C1_COVER "))
    assert payload["shadow"]["2026-27"]["covered"] == 4
