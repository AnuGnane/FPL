"""The presser/quote classifier — a short free text, read by an LLM.

Two sources say things no structured feed carries: premierinjuries' "Further
Detail" cell (a manager's quote) and the FPL bootstrap's ``news`` column. Both
are one sentence, and both routinely contain the sharpest available claim
about the imminent gameweek — "he's not ready to start", "a knock, we'll
assess" — in prose no regex is going to survive.

Three properties make this safe to run on every advise:

*Shadow-first.* ``[news] llm_classifier`` ships **false**. The verdicts are
logged whatever the flag says; they only reach the numbers when the flag is
flipped, on evidence, the same ritual Z1 got.

*Cached by text.* Twenty players carrying "Knock — assessed daily" is one
text and therefore one call, and a re-run in the same week is none. The key
carries :data:`PROMPT_VERSION`, because the entries never expire and a
rewritten question must not be answered out of the old one's cache.

*Total-failure-safe.* A missing binary, a non-zero exit, a timeout, prose
where JSON was asked for, a row naming a verdict nobody defined: every one of
them yields an empty frame and one printed line. A dead classifier leaves the
pipeline byte-identical to a classifier that was never enabled. The failure
is also *bounded*: the slate goes out in batches of :data:`BATCH_SIZE`, each
retried once, so a bad batch costs its own forty texts rather than all of
them.
"""

from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

LLM_CACHE = Path("data/raw/news/llm")
CLASSIFIER_COLS = ["code", "verdict", "confidence", "model", "text_hash",
                   "fetched_at"]

VERDICTS = {"confirmed_starter", "rotation_risk", "knock", "assess",
            "ruled_out", "irrelevant"}
"""The whole vocabulary. A row naming anything else is dropped and counted:
an open vocabulary is a mapping table nobody can write, and the mapping is
the only reason to run this at all."""

DEFAULT_TIMEOUT_S = 300
"""Seconds one batch of forty may take.

A headless CLI on a consumer subscription is not a fast API: a cold start,
a queue and forty items of reasoning are minutes, not seconds. The old two
is what a healthy call looked like on a good day, which made a timeout the
*expected* outcome under load, and a timeout is indistinguishable here from
a classifier that is simply off.
"""

BATCH_SIZE = 40
"""Texts per subprocess.

The whole squad in one call is one timeout away from no verdicts at all;
one call per text is a subprocess apiece. Forty splits a full slate into a
handful of calls, each of which fails on its own.
"""

RETRY_BACKOFF_S = 2.0
"""Seconds before a failed chunk's single retry."""

PROMPT_VERSION = 1
"""Bumped whenever :func:`build_prompt` or :data:`VERDICTS` changes.

It salts the cache key, so a changed question cannot be answered out of a
cache filled by the old one. Without it a prompt rewrite would keep serving
last week's verdicts indefinitely, and the entries never expire.
"""


@dataclass(frozen=True)
class NewsText:
    """One player's free text, and where it came from."""

    code: int
    text: str
    source: str


def text_hash(text: str) -> str:
    """The cache key: the text, and the question we asked about it.

    Squad-wide boilerplate collapses to one entry, and a player whose quote
    has not changed since Tuesday costs nothing on Friday. The
    :data:`PROMPT_VERSION` salt is what keeps that from outliving its own
    prompt: entries never expire, so an unsalted key would answer a rewritten
    question out of a cache the old one filled.
    """
    salted = f"{PROMPT_VERSION}\x00{str(text or '').strip()}"
    return hashlib.sha256(salted.encode("utf-8")).hexdigest()[:16]


def build_prompt(texts: list[NewsText]) -> str:
    """One prompt for the whole uncached batch, answered as a JSON array.

    Batched rather than one call per text because the per-call overhead is the
    cost here, not the tokens: thirty texts are a few hundred words and thirty
    subprocesses are half a minute.
    """
    # Every item's text is scraped web content — a quote off premierinjuries,
    # the bootstrap's own ``news`` string — and therefore untrusted. It is
    # pasted below instructions it may well try to countermand, which is why
    # the shipped ``llm_command`` hands the model no tools and why nothing
    # but a verdict from a closed vocabulary survives _extract_rows.
    lines = [
        "You are classifying short Fantasy Premier League team-news texts.",
        "For EACH numbered item below, decide which one verdict best fits:",
        "  confirmed_starter — the text says he will start / is fully fit",
        "  rotation_risk — fit, but the text hints he may be rested/rotated",
        "  knock — a minor problem, likely available",
        "  assess — explicitly to be assessed / a late call",
        "  ruled_out — will not feature",
        "  irrelevant — the text says nothing about his availability",
        "",
        "Reply with ONLY a JSON array, one object per item, no prose:",
        '[{"code": <the item\'s code>, "verdict": "<one of the six>",',
        '  "confidence": <0.0-1.0>}]',
        "",
        "Items:"]
    for t in texts:
        flat = " ".join(str(t.text or "").split())
        lines.append(f"- code {int(t.code)} ({t.source}): {flat}")
    return "\n".join(lines)


def _extract_rows(stdout: str) -> list[dict]:
    """The model's rows, out of whatever the CLI wrapped them in.

    ``claude -p --output-format json`` returns an envelope whose ``result`` is
    the model's own text; a different ``llm_command`` may print the array
    directly, or print the whole thing as one JSON-encoded string. All three
    are read, and anything else raises here and is caught by the one handler
    in :func:`classify_news`.
    """
    payload = json.loads(stdout)
    if isinstance(payload, str):
        payload = json.loads(payload)
    if isinstance(payload, dict):
        payload = json.loads(payload["result"])
    if not isinstance(payload, list):
        raise ValueError("classifier output was not a JSON array")
    return payload


def _cached(cache_dir: Path, key: str) -> dict | None:
    path = cache_dir / f"{key}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — a corrupt cache entry is a cache miss
        return None


def _store(cache_dir: Path, key: str, row: dict) -> None:
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / f"{key}.json").write_text(json.dumps(row),
                                               encoding="utf-8")
    except Exception:  # noqa: BLE001 — an unwritable cache is not an outage
        pass


def _run_chunk(cmd: str, chunk: list[NewsText], timeout: int) -> list[dict]:
    """One batch's rows, or ``[]``. Never raises.

    A timeout, a non-zero exit, prose where JSON was asked for and an empty
    array are all the same event — the call did not answer — and all get one
    retry after :data:`RETRY_BACKOFF_S`. Once, not until it works: the
    failures worth retrying here are a cold start and a busy queue, and a
    CLI that is not installed will not become installed on the third go.
    A chunk that fails twice is skipped, and the other chunks still land.
    """
    prompt = build_prompt(chunk)
    for attempt in range(2):
        try:
            proc = subprocess.run(shlex.split(cmd), input=prompt,
                                  capture_output=True, text=True,
                                  timeout=timeout, check=True)
            parsed = _extract_rows(proc.stdout)
            if not parsed:
                raise ValueError("classifier returned no rows")
            return parsed
        except Exception as exc:  # noqa: BLE001 — the classifier never blocks
            if attempt == 0:
                time.sleep(RETRY_BACKOFF_S)
                continue
            print("news: presser classifier unavailable — "
                  f"{len(chunk)} texts unclassified ({exc})")
    return []


def classify_news(texts: list[NewsText], *, cmd: str,
                  cache_dir: Path = LLM_CACHE,
                  timeout: int = DEFAULT_TIMEOUT_S,
                  now: datetime | None = None) -> pd.DataFrame:
    """``[code, verdict, confidence, model, text_hash, fetched_at]``.

    Never raises, whatever the CLI does. An empty frame is the
    classifier-absent path, which is the shipped behaviour anyway.
    """
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    cache_dir = Path(cache_dir)
    model = shlex.split(cmd)[0] if cmd.strip() else ""
    rows: list[dict] = []
    pending: list[NewsText] = []
    for t in texts:
        key = text_hash(t.text)
        hit = _cached(cache_dir, key)
        if hit is None:
            pending.append(t)
        else:
            rows.append({"code": int(t.code), "verdict": hit["verdict"],
                         "confidence": float(hit.get("confidence", 0.0)),
                         "model": hit.get("model", model), "text_hash": key,
                         "fetched_at": stamp})

    dropped = 0
    # One subprocess per BATCH_SIZE texts. A full slate is a couple of
    # hundred, and putting them in one call makes a single timeout the
    # difference between every verdict and none; chunked, a bad batch costs
    # its own forty and the rest still land.
    for start in range(0, len(pending), BATCH_SIZE):
        chunk = pending[start:start + BATCH_SIZE]
        by_code = {int(t.code): t for t in chunk}
        for row in _run_chunk(cmd, chunk, timeout):
            try:
                code = int(row["code"])
                verdict = str(row["verdict"])
                confidence = float(row.get("confidence", 0.0))
            except Exception:  # noqa: BLE001 — one bad row, not a bad batch
                dropped += 1
                continue
            if verdict not in VERDICTS or code not in by_code:
                dropped += 1
                continue
            key = text_hash(by_code[code].text)
            _store(cache_dir, key, {"verdict": verdict,
                                    "confidence": confidence, "model": model,
                                    "fetched_at": stamp})
            rows.append({"code": code, "verdict": verdict,
                         "confidence": confidence, "model": model,
                         "text_hash": key, "fetched_at": stamp})
    if dropped:
        print(f"news: presser classifier dropped {dropped} malformed rows")

    if not rows:
        return pd.DataFrame(columns=CLASSIFIER_COLS)
    out = pd.DataFrame(rows)[CLASSIFIER_COLS]
    return out.drop_duplicates(subset=["code"]).reset_index(drop=True)
