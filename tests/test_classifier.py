"""The presser classifier: a subprocess that is allowed to fail.

Every test here runs a *fake* CLI — a two-line Python script printing canned
JSON. The real ``claude -p`` is never invoked from the suite (spec §7): it
costs seconds per call, needs a logged-in machine, and would make a green
suite depend on somebody's subscription.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from gaffer.data.news.classifier import (CLASSIFIER_COLS, VERDICTS, NewsText,
                                         classify_news, text_hash)

_ROWS = [{"code": 1, "verdict": "rotation_risk", "confidence": 0.8},
         {"code": 2, "verdict": "confirmed_starter", "confidence": 0.9}]


def _fake(tmp_path: Path, payload, exit_code: int = 0,
          sleep: float = 0.0) -> str:
    """A CLI that ignores its stdin and prints ``payload``."""
    script = tmp_path / "fake_cli.py"
    script.write_text(
        "import sys, time, json\n"
        "sys.stdin.read()\n"
        f"time.sleep({sleep})\n"
        f"sys.stdout.write({json.dumps(payload)!r})\n"
        f"sys.exit({exit_code})\n", encoding="utf-8")
    return f"{sys.executable} {script}"


def _texts():
    return [NewsText(code=1, text="Rested, we will see", source="fpl"),
            NewsText(code=2, text="He trained fully", source="pi")]


def test_a_clean_batch_comes_back_as_one_row_per_text(tmp_path):
    cmd = _fake(tmp_path, json.dumps({"result": json.dumps(_ROWS)}))
    out = classify_news(_texts(), cmd=cmd, cache_dir=tmp_path / "cache",
                        timeout=10)
    assert list(out.columns) == CLASSIFIER_COLS
    assert sorted(out["code"]) == [1, 2]
    assert set(out["verdict"]) <= VERDICTS


def test_a_bare_json_array_is_accepted_too(tmp_path):
    """``llm_command`` is configurable, so the wrapper shape is not
    guaranteed: a CLI that prints the array itself is read the same way."""
    cmd = _fake(tmp_path, json.dumps(_ROWS))
    out = classify_news(_texts(), cmd=cmd, cache_dir=tmp_path / "cache",
                        timeout=10)
    assert len(out) == 2


def test_a_row_with_an_unknown_verdict_is_dropped_not_guessed(tmp_path):
    rows = _ROWS + [{"code": 3, "verdict": "vibes", "confidence": 1.0}]
    cmd = _fake(tmp_path, json.dumps({"result": json.dumps(rows)}))
    out = classify_news(_texts(), cmd=cmd, cache_dir=tmp_path / "cache",
                        timeout=10)
    assert 3 not in set(out["code"])


def test_a_second_call_reads_the_cache_and_never_runs_the_cli(tmp_path):
    cache = tmp_path / "cache"
    cmd = _fake(tmp_path, json.dumps({"result": json.dumps(_ROWS)}))
    classify_news(_texts(), cmd=cmd, cache_dir=cache, timeout=10)
    dead = _fake(tmp_path, "", exit_code=1)
    again = classify_news(_texts(), cmd=dead, cache_dir=cache, timeout=10)
    assert sorted(again["code"]) == [1, 2]


def test_the_cache_key_is_the_text_not_the_player(tmp_path):
    """Twenty players carrying "Knock, assessed daily" is one call."""
    assert text_hash("a") != text_hash("b")
    assert text_hash("a") == text_hash("a")


def test_a_dead_cli_yields_an_empty_frame_and_one_line(tmp_path, capsys):
    out = classify_news(_texts(), cmd=_fake(tmp_path, "", exit_code=3),
                        cache_dir=tmp_path / "cache", timeout=10)
    assert out.empty and list(out.columns) == CLASSIFIER_COLS
    assert "classifier" in capsys.readouterr().out


def test_a_missing_binary_yields_an_empty_frame(tmp_path):
    out = classify_news(_texts(), cmd="definitely-not-a-binary --json",
                        cache_dir=tmp_path / "cache", timeout=10)
    assert out.empty


def test_a_timeout_yields_an_empty_frame(tmp_path):
    cmd = _fake(tmp_path, json.dumps(_ROWS), sleep=2.0)
    out = classify_news(_texts(), cmd=cmd, cache_dir=tmp_path / "cache",
                        timeout=1)
    assert out.empty


def test_unparseable_output_yields_an_empty_frame(tmp_path):
    out = classify_news(_texts(), cmd=_fake(tmp_path, "I'm sorry Dave"),
                        cache_dir=tmp_path / "cache", timeout=10)
    assert out.empty


def test_no_texts_at_all_runs_nothing(tmp_path):
    out = classify_news([], cmd="definitely-not-a-binary",
                        cache_dir=tmp_path / "cache", timeout=10)
    assert out.empty and list(out.columns) == CLASSIFIER_COLS


def test_the_prompt_names_every_verdict_and_every_text(tmp_path):
    from gaffer.data.news.classifier import build_prompt

    prompt = build_prompt(_texts())
    for verdict in VERDICTS:
        assert verdict in prompt
    assert "Rested, we will see" in prompt
    assert "He trained fully" in prompt
