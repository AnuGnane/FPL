"""Aggregate banked replay reports into one multi-seed reading.

``scripts/v7b_replay.py --seed-bases`` prints this line for a trio it drove
itself. This reads the same numbers back off reports already on disk, so three
single-seed runs banked weeks apart — every v7b report is one — can still be
read as one measurement without spending another replay.

Only across one arm: the reports' config echoes must differ in nothing but
``seed_base`` and ``tag``, or the script refuses (exit 2) rather than print a
"spread" that is really an arm gap.

Usage::

    uv run python scripts/seed_stats.py reports/v7b_q1b-heur.json \\
        reports/v7b_q1c-heur.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


SEED_FIELDS = ("seed_base", "tag")
"""The only two config fields a multi-seed trio is allowed to differ in.

Everything else — the arm, the chips flag, the priors, the minutes head, the
frame, ``n``, the noise asset — defines *which measurement* the run is, not
which draw of it. See :func:`config_mismatch`.
"""


def read_report(path: str | Path) -> tuple[int, int | None, dict | None]:
    """``(total, seed_base, config)`` from one replay report.

    The base and the config are ``None`` for a report written before the config
    echo was recorded; the total is the number the aggregate is about either
    way.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    config = payload.get("config")
    base = (config or {}).get("seed_base")
    return (int(payload["total"]),
            (int(base) if base is not None else None),
            config)


def config_mismatch(paths: list[str], configs: list[dict | None]) -> str | None:
    """One line naming the fields that differ, or ``None`` if the arm is one.

    v7b banked ``q2-ctrl-heur`` (chips off, priors off) alongside two chips-on
    heuristic runs, and averaging the three read out a "seed spread" of 115
    points that was mostly the arm gap between a control and its treatment. A
    spread is only a seed spread when nothing but the seed moved.

    A report carrying no config echo is *unknown*, not *matching*: it might be
    any arm, and "probably the same" is exactly the assumption that produced
    the 115.
    """
    if len(paths) < 2:
        return None
    if any(c is None for c in configs) and not all(c is None for c in configs):
        unknown = [p for p, c in zip(paths, configs) if c is None]
        return (f"config echo missing from {', '.join(unknown)} — an unknown "
                "arm cannot be averaged with a known one")
    if configs[0] is None:
        return None
    fields = sorted({k for c in configs for k in c} - set(SEED_FIELDS))
    differing = [f for f in fields
                 if len({json.dumps(c.get(f), sort_keys=True)
                         for c in configs}) > 1]
    if not differing:
        return None
    return (f"refusing to aggregate: {', '.join(differing)} differ across "
            f"{', '.join(paths)} — these are different arms, not different "
            "seeds of one arm")


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
    """Print one line per report, then the aggregate JSON.

    Refuses with exit 2, and without printing an aggregate, when the reports
    were not all run on the same arm: a number that reads as a seed spread but
    is really an arm gap is worse than no number.
    """
    if not argv:
        raise SystemExit("usage: seed_stats.py <report.json> [report.json ...]")
    totals: list[int] = []
    bases: list[int | None] = []
    configs: list[dict | None] = []
    for path in argv:
        try:
            total, base, config = read_report(path)
        except FileNotFoundError:
            print(f"seed_stats.py: no such report: {path}")
            raise SystemExit(2) from None
        totals.append(total)
        bases.append(base)
        configs.append(config)
        print(f"{path}: total={total} seed_base={base}")
    complaint = config_mismatch(list(argv), configs)
    if complaint is not None:
        print(complaint)
        raise SystemExit(2)
    out = aggregate(totals, bases)
    print(json.dumps(out))
    return out


if __name__ == "__main__":
    main(sys.argv[1:])
