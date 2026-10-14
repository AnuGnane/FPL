"""Collect the v20 evidence lines from the logs, shaped for the spec's §6.

v20 spec §3: "Every ``*_ARM_DONE``, ``MULTISEED_DONE``, ``V20*_HEAD`` and
``V20D_BRIER`` line is transcribed into §6 of this document and into the
arm's spec the day it prints (CONVENTIONS §4)", with the lever lines §2 names
beside them (holiday F-34). ``logs/`` is gitignored, so the transcription is
the record; this script finds the lines so the night shift pastes rather than
retypes. It only collects: no line is edited, rounded, deduplicated or
summarised (``scripts/seed_stats.py`` aggregates).

The lines, matched at the start of a line:

- tagged: ``<PREFIX>_ARM_DONE <tag> …`` and ``MULTISEED_DONE <tag> …``;
- the readings: ``V20<arm>_<NAME> …`` (``V20B_HEAD``, ``V20C_HEAD``,
  ``V20D_BRIER``, ``V20D_RUN``, ``V20D_ROW``);
- the lever lines: ``LEVER minutes cols=``, ``LEVER bonus cols=``,
  ``DC_CLIP n=`` and the harness's ``REPLAY_TEAM_MODEL p_cs`` line.

Each goes under one arm, in ``ARMS`` order:

- a tagged line by its tag's prefix (``v20c0-…`` is the harness step, so it
  is tried before ``v20c``); a tag no arm claims is ``unclaimed``;
- a reading by its own prefix (``V20B_`` is v20b);
- a lever line by the run it was printed in: the arm of the next tagged line
  or reading in the same file (a replay prints its lever lines before its
  ``ARM_DONE``, and ``scripts/v20c_head.py`` its ``DC_CLIP`` lines before
  ``V20C_HEAD``), else of the last one before it, so a lever line of a
  replay no arm claims is ``unclaimed`` too. A file with neither falls back
  to ``DC_CLIP`` → v20c and ``REPLAY_TEAM_MODEL`` → v20c0; a ``LEVER`` line
  there is ``unclaimed``, since both heads print one in every replay and the
  line alone cannot say which arm ran.

Holiday F-40: the one-line readings the holiday scripts print are collected
too, each under the script that prints it (``READINGS``), after the v20
arms and before ``unclaimed``: ``C1_BUCKETS``, ``C2_PPLAY``,
``C3_HOME_AWAY``, ``B1_STATUS_AGE``, ``DENSITY_HEAD``, ``TOP10K_PROJ``,
``WALK_HITS``/``WALK_HITS_GW``, ``PCS_WINDOW``/``PCS_WINDOWS``,
``PRESSER_GW``/``PRESSER_SERVE``, ``NEWS_SHADOW_GW``/``NEWS_SHADOW``/
``FLAG_LATENCY`` (holiday F-46) and ``BACKFILL_RANK`` (holiday F-51),
matched as a whole word at the start of a line. A reading is not a run, so
it never anchors a lever line: the v20 grouping above is the same with or
without them.

Nothing is deduplicated: a v20c replay prints ``DC_CLIP`` on every predict,
so its block is long, and the night shift trims when it transcribes. With the
clip on, the live advise log carries ``DC_CLIP`` lines too and is appended to
daily, so ``--since`` keeps it; pass the replay's own log files to leave it
out (holiday F-34's ruling: no file is skipped by name).

Files are ordered by modification time, then path, and lines keep their order
within a file. The output is one ``### <arm>`` heading per arm with lines,
then, per file, its name and modification date (UTC) and its lines verbatim
in a fenced block. ``--since YYYY-MM-DD`` keeps only files modified on or
after that UTC date. Nothing found prints nothing.

Read-only: it writes nothing.

    uv run python scripts/v20_appendix.py                 # logs/
    uv run python scripts/v20_appendix.py logs/v20b.log --since 2026-10-14
"""

from __future__ import annotations

import argparse
import re
from datetime import date, datetime, timezone
from pathlib import Path

ARMS = ["v20a", "v20b", "v20c0", "v20c", "v20d", "unclaimed"]
"""The v20 arms and ``unclaimed``, in output order (``GROUPS`` puts the
readings between them). ``v20c0`` is v20c's step zero, the harness re-baseline,
which §6.2 transcribes apart from the clip's own pair."""

READINGS: list[tuple[str, tuple[str, ...]]] = [
    ("scripts/c1_news_buckets.py", ("C1_BUCKETS",)),
    ("scripts/c2_pplay_bins.py", ("C2_PPLAY",)),
    ("scripts/c3_home_away.py", ("C3_HOME_AWAY",)),
    ("scripts/b1_status_age.py", ("B1_STATUS_AGE",)),
    ("scripts/density_head.py", ("DENSITY_HEAD",)),
    ("scripts/top10k_projection.py", ("TOP10K_PROJ",)),
    ("scripts/walk_hits.py", ("WALK_HITS", "WALK_HITS_GW")),
    ("scripts/pcs_window.py", ("PCS_WINDOW", "PCS_WINDOWS")),
    ("scripts/presser_serve.py", ("PRESSER_GW", "PRESSER_SERVE")),
    ("scripts/evaluate_lines.py", ("NEWS_SHADOW_GW", "NEWS_SHADOW",
                                   "FLAG_LATENCY")),
    ("scripts/backfill_overall_rank.py", ("BACKFILL_RANK",)),
]
"""Holiday F-40: each reading script and the prefixes it prints, in the
order its group prints."""

GROUPS = ARMS[:-1] + [script for script, _ in READINGS] + ARMS[-1:]
"""Output order: the v20 arms, the reading scripts, then ``unclaimed``."""

_READING_SCRIPT = {prefix: script for script, prefixes in READINGS
                   for prefix in prefixes}

TAG_ARMS = ["v20a", "v20b", "v20c0", "v20c", "v20d"]
"""Tag prefixes, tried in this order: ``v20c0`` before ``v20c``."""

_TAGGED = re.compile(r"^(?:[A-Z0-9]+_ARM_DONE|MULTISEED_DONE) (\S+)")
_READING = re.compile(r"^V20([A-D])_[A-Z]+\b")
_LEVER = re.compile(r"^(?:LEVER (?:minutes|bonus) cols=|DC_CLIP n=|"
                    r"REPLAY_TEAM_MODEL p_cs\b)")
_LEVER_DEFAULT = {"DC_CLIP": "v20c", "REPLAY_TEAM_MODEL": "v20c0"}

DEFAULT_DIR = Path("logs")


def tag_arm(tag: str) -> str:
    for arm in TAG_ARMS:
        if tag == arm or tag.startswith(arm + "-"):
            return arm
    return "unclaimed"


def file_lines(text: str) -> list[tuple[str, str]]:
    """``(arm, line)`` for every evidence line in one file, in file order."""
    found: list[tuple[str | None, str, str]] = []   # (arm or None, kind, line)
    for line in text.splitlines():
        if m := _TAGGED.match(line):
            found.append((tag_arm(m.group(1)), "tagged", line))
        elif m := _READING.match(line):
            found.append(("v20" + m.group(1).lower(), "reading", line))
        elif _LEVER.match(line):
            found.append((None, "lever", line))
        elif (script := _READING_SCRIPT.get(line.split(" ", 1)[0])):
            found.append((script, "holiday", line))
    anchors = [(i, arm) for i, (arm, kind, _) in enumerate(found)
               if kind in ("tagged", "reading")]
    out = []
    for i, (arm, kind, line) in enumerate(found):
        if kind == "lever":
            after = next((a for j, a in anchors if j > i), None)
            before = next((a for j, a in reversed(anchors) if j < i), None)
            arm = after or before or _LEVER_DEFAULT.get(line.split()[0],
                                                         "unclaimed")
        out.append((arm, line))
    return out


def _files(paths: list[Path]) -> list[Path]:
    """Every file named or under a named directory, once each: ``logs/`` and
    ``logs/b.log`` together, or a link and its target, are one file."""
    out, seen = [], set()
    for p in paths:
        found = ([f for f in p.rglob("*") if f.is_file()] if p.is_dir()
                 else [p] if p.is_file() else [])
        for f in found:
            key = f.resolve()
            if key not in seen:
                seen.add(key)
                out.append(f)
    return out


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def collect(paths: list[Path], since: date | None = None
            ) -> dict[str, list[tuple[Path, datetime, list[str]]]]:
    """Per arm, the files with lines for it, each with its modification time
    and those lines, in order."""
    files = []
    for f in _files(paths):
        try:
            stamp = _mtime(f)
        except OSError:
            continue
        if since is not None and stamp.date() < since:
            continue
        files.append((stamp, str(f), f))
    files.sort()
    grouped: dict[str, list[tuple[Path, datetime, list[str]]]] = {
        a: [] for a in GROUPS}
    for stamp, _, f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        per_arm: dict[str, list[str]] = {}
        for arm, line in file_lines(text):
            per_arm.setdefault(arm, []).append(line)
        for arm, lines in per_arm.items():
            grouped[arm].append((f, stamp, lines))
    return grouped


def render(grouped: dict[str, list[tuple[Path, datetime, list[str]]]]) -> str:
    blocks = []
    for arm in GROUPS:
        if not grouped.get(arm):
            continue
        parts = [f"### {arm}"]
        for f, stamp, lines in grouped[arm]:
            parts.append(f"`{f}`, modified {stamp.date().isoformat()} (UTC)")
            parts.append("```\n" + "\n".join(lines) + "\n```")
        blocks.append("\n\n".join(parts))
    return "\n\n".join(blocks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path,
                        help="log files or directories (default: logs/)")
    parser.add_argument("--since", type=date.fromisoformat, default=None,
                        help="only files modified on or after this UTC date")
    args = parser.parse_args(argv)
    out = render(collect(args.paths or [DEFAULT_DIR], args.since))
    if out:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
