"""Aggregate banked replay reports into one multi-seed reading.

``scripts/v7b_replay.py --seed-bases`` prints this line for a trio it drove
itself. This reads the same numbers back off reports already on disk, so three
single-seed runs banked weeks apart — every v7b report is one — can still be
read as one measurement without spending another replay.

Usage::

    uv run python scripts/seed_stats.py reports/v7b_q1b-heur.json \\
        reports/v7b_q1c-heur.json reports/v7b_q2-ctrl-heur.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def read_report(path: str | Path) -> tuple[int, int | None]:
    """``(total, seed_base)`` from one replay report.

    The base is ``None`` for a report written before ``--seed-base`` was
    recorded; the total is the number the aggregate is about either way.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    base = payload.get("config", {}).get("seed_base")
    return int(payload["total"]), (int(base) if base is not None else None)


def aggregate(totals: list[int], seed_bases: list[int | None]) -> dict:
    """The ``MULTISEED_DONE`` payload — identical keys, identical arithmetic.

    Deliberately a copy of ``v7b_replay.multiseed_summary`` rather than an
    import of it: importing that module pulls in ``gaffer.backtest`` and
    lightgbm to average three integers, and this script exists to be cheap.
    ``tests/test_seed_stats.py`` asserts the two agree.
    """
    values = [int(t) for t in totals]
    return {"totals": values,
            "mean": round(sum(values) / len(values), 1),
            "spread": max(values) - min(values),
            "range": [min(values), max(values)],
            "seed_bases": [int(b) if b is not None else None
                           for b in seed_bases]}


def main(argv: list[str]) -> dict:
    """Print one line per report, then the aggregate JSON."""
    if not argv:
        raise SystemExit("usage: seed_stats.py <report.json> [report.json ...]")
    totals: list[int] = []
    bases: list[int | None] = []
    for path in argv:
        total, base = read_report(path)
        totals.append(total)
        bases.append(base)
        print(f"{path}: total={total} seed_base={base}")
    out = aggregate(totals, bases)
    print(json.dumps(out))
    return out


if __name__ == "__main__":
    main(sys.argv[1:])
