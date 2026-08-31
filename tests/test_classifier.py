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
import pytest

from gaffer.data.news.classifier import (CLASSIFIER_COLS, RETRY_BACKOFF_S,
                                         VERDICTS, NewsText, classify_news,
                                         text_hash)

_SHIPPED_BACKOFF_S = RETRY_BACKOFF_S

_ROWS = [{"code": 1, "verdict": "rotation_risk", "confidence": 0.8},
         {"code": 2, "verdict": "confirmed_starter", "confidence": 0.9}]


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    """The retry's two-second wait is real behaviour and a dead two seconds
    per failing test. Its value is pinned once, below; everywhere else the
    sleep is zeroed so the failure paths stay cheap to exercise."""
    from gaffer.data.news import classifier as cl

    monkeypatch.setattr(cl, "RETRY_BACKOFF_S", 0.0)


def test_the_backoff_between_the_two_attempts_is_two_seconds():
    # Captured at import, before the autouse fixture can zero it.
    assert _SHIPPED_BACKOFF_S == 2.0


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


# --- chunking, retry, and the cache salt -----------------------------------

def _echoing(tmp_path: Path, log: Path, fail_codes=()) -> str:
    """A CLI that answers whatever codes it was handed, and logs each call.

    ``fail_codes`` names codes whose *batch* exits non-zero, which is how a
    single bad chunk is staged without touching the others.
    """
    script = tmp_path / "echo_cli.py"
    script.write_text(
        "import sys, re, json, pathlib\n"
        "data = sys.stdin.read()\n"
        "codes = [int(c) for c in re.findall(r'- code (\\d+)', data)]\n"
        f"log = pathlib.Path({str(log)!r})\n"
        "with log.open('a') as fh:\n"
        "    fh.write(','.join(str(c) for c in codes) + '\\n')\n"
        f"bad = set({list(fail_codes)!r})\n"
        "if bad & set(codes):\n"
        "    sys.exit(1)\n"
        "sys.stdout.write(json.dumps([{'code': c, 'verdict': 'irrelevant',\n"
        "                              'confidence': 0.5} for c in codes]))\n",
        encoding="utf-8")
    return f"{sys.executable} {script}"


def _many(n: int, offset: int = 0):
    return [NewsText(code=offset + i, text=f"text {offset + i}", source="pi")
            for i in range(n)]


def test_a_long_slate_is_split_into_batches(tmp_path):
    """91 texts is three calls, not one. A whole squad in a single prompt
    makes one timeout the difference between every verdict and none."""
    from gaffer.data.news.classifier import BATCH_SIZE

    assert BATCH_SIZE == 40
    log = tmp_path / "calls.log"
    cmd = _echoing(tmp_path, log)
    out = classify_news(_many(91), cmd=cmd, cache_dir=tmp_path / "cache",
                        timeout=30)
    calls = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(calls) == 3
    assert [len(c.split(",")) for c in calls] == [40, 40, 11]
    assert len(out) == 91


def test_a_failing_chunk_is_retried_once_and_then_skipped(tmp_path):
    """The other chunks still land. A batch that will not answer twice is
    a batch of forty unclassified texts, not an outage."""
    log = tmp_path / "calls.log"
    # Code 45 sits in the second batch of forty.
    cmd = _echoing(tmp_path, log, fail_codes=(45,))
    out = classify_news(_many(91), cmd=cmd, cache_dir=tmp_path / "cache",
                        timeout=30)
    calls = log.read_text(encoding="utf-8").strip().splitlines()
    # Three chunks, one of them attempted twice.
    assert len(calls) == 4
    assert sorted(out["code"]) == list(range(0, 40)) + list(range(80, 91))


def test_a_chunk_that_answers_on_the_retry_still_lands(tmp_path):
    script = tmp_path / "flaky_cli.py"
    flag = tmp_path / "seen"
    script.write_text(
        "import sys, re, json, pathlib\n"
        "data = sys.stdin.read()\n"
        f"flag = pathlib.Path({str(flag)!r})\n"
        "if not flag.exists():\n"
        "    flag.write_text('x')\n"
        "    sys.exit(1)\n"
        "codes = [int(c) for c in re.findall(r'- code (\\d+)', data)]\n"
        "sys.stdout.write(json.dumps([{'code': c, 'verdict': 'knock',\n"
        "                              'confidence': 0.4} for c in codes]))\n",
        encoding="utf-8")
    out = classify_news(_texts(), cmd=f"{sys.executable} {script}",
                        cache_dir=tmp_path / "cache", timeout=30)
    assert sorted(out["code"]) == [1, 2]


def test_an_empty_array_is_a_failed_chunk_not_a_verdict(tmp_path):
    """A CLI that answers ``[]`` has not classified anything, and treating
    that as success would cache nothing and report a clean run."""
    out = classify_news(_texts(), cmd=_fake(tmp_path, json.dumps([])),
                        cache_dir=tmp_path / "cache", timeout=10)
    assert out.empty


def test_the_cache_key_changes_when_the_prompt_version_does(tmp_path,
                                                            monkeypatch):
    """Cache entries never expire, so a rewritten prompt served out of the
    old cache would answer a question nobody asked."""
    from gaffer.data.news import classifier as cl

    before = cl.text_hash("Knock, assessed daily")
    monkeypatch.setattr(cl, "PROMPT_VERSION", cl.PROMPT_VERSION + 1)
    assert cl.text_hash("Knock, assessed daily") != before

    cache = tmp_path / "cache"
    cmd = _fake(tmp_path, json.dumps({"result": json.dumps(_ROWS)}))
    classify_news(_texts(), cmd=cmd, cache_dir=cache, timeout=10)
    monkeypatch.setattr(cl, "PROMPT_VERSION", cl.PROMPT_VERSION + 1)
    again = classify_news(_texts(), cmd=_fake(tmp_path, "", exit_code=1),
                          cache_dir=cache, timeout=10)
    assert again.empty


def test_a_cache_entry_records_when_it_was_written(tmp_path):
    cache = tmp_path / "cache"
    cmd = _fake(tmp_path, json.dumps({"result": json.dumps(_ROWS)}))
    classify_news(_texts(), cmd=cmd, cache_dir=cache, timeout=10)
    entry = json.loads(next(cache.glob("*.json")).read_text(encoding="utf-8"))
    assert entry["fetched_at"]
    assert entry["verdict"] in VERDICTS


def test_the_prompt_names_every_verdict_and_every_text(tmp_path):
    from gaffer.data.news.classifier import build_prompt

    prompt = build_prompt(_texts())
    for verdict in VERDICTS:
        assert verdict in prompt
    assert "Rested, we will see" in prompt
    assert "He trained fully" in prompt
