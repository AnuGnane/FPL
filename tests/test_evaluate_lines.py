"""scripts/evaluate_lines.py, the two accruing `evaluate` verdicts as lines
(holiday F-46).

A hand-written ``reports/evaluation.json`` with a two-gameweek news-shadow
payload and a flag-latency payload, an empty artifact, the empty payloads
each scorer returns, and a round trip through ``scripts/v20_appendix.py`` so
the night shift's collector files every line under this script.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "scripts")

import evaluate_lines
import v20_appendix as ap

FIXTURE = Path("tests/fixtures/evaluation_news_shadow.json")

FIXTURE_LINES = [
    "NEWS_SHADOW_GW gw=6 n=205 brier_news=0.1212 brier_flags=0.1302",
    "NEWS_SHADOW_GW gw=7 n=207 brier_news=0.1156 brier_flags=0.12",
    "NEWS_SHADOW n=412 brier_news=0.1184 brier_flags=0.1251",
    "FLAG_LATENCY rows=9 late_flags=2 missed=6 histogram=<1d=5,1-2d=2,7d+=2",
]

NONE_LINES = [
    "NEWS_SHADOW none: run gaffer evaluate --news-shadow",
    "FLAG_LATENCY none: run gaffer evaluate --flag-latency",
]


def _run(path, capsys):
    evaluate_lines.main(path)
    return capsys.readouterr().out.splitlines()


def test_the_fixture_prints_one_line_per_verdict(capsys):
    assert _run(FIXTURE, capsys) == FIXTURE_LINES


def test_an_artifact_without_either_key_prints_the_none_lines(tmp_path,
                                                              capsys):
    path = tmp_path / "evaluation.json"
    path.write_text("{}")
    assert _run(path, capsys) == NONE_LINES


def test_a_missing_artifact_prints_the_none_lines(tmp_path, capsys):
    assert _run(tmp_path / "evaluation.json", capsys) == NONE_LINES


def test_the_empty_payloads_the_scorers_return_print_the_none_lines(
        tmp_path, capsys):
    """``score_news_shadow`` with nothing joined returns ``rows: 0, overall:
    {}, by_gw: []``; ``score_flag_latency`` behind its gate returns
    ``available: False, rows: 0`` with a note. Neither is a verdict."""
    path = tmp_path / "evaluation.json"
    path.write_text(json.dumps({
        "news_shadow": {"run_at": "x", "git_sha": "x", "rows": 0,
                        "overall": {}, "by_gw": []},
        "flag_latency": {"kind": "flag_latency", "available": False,
                         "rows": 0, "note": "too few snapshots",
                         "histogram": [], "late_flags": [], "changes": []},
    }))
    assert _run(path, capsys) == NONE_LINES


def test_every_line_round_trips_through_the_appendix_under_this_script(
        capsys):
    """v20 spec §3 (holiday F-40, F-43): the night shift pastes what the
    collector finds, so each line must land under this script."""
    lines = _run(FIXTURE, capsys) + NONE_LINES
    text = "\n".join(lines) + "\n"
    assert ap.file_lines(text) == [("scripts/evaluate_lines.py", line)
                                   for line in lines]
