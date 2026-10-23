"""The two `evaluate` verdicts that accrue by gameweek, as appendix lines.

ROADMAP "Data-gated" ("Accruing verdicts, not boxes: `gaffer evaluate
--news-shadow` after each `data_checked` GW") and its W2 §3.1 flag-latency
row, under v20 spec §3's rule that a reading is transcribed the day it
prints (CONVENTIONS §4; holiday F-46). Both reports already land in
``reports/evaluation.json`` (``evaluation.EVALUATION_PATH``, one key per
report, merged by ``save_evaluation``); this prints them as lines
``scripts/v20_appendix.py`` collects, so the night shift pastes rather than
reads JSON. ``gaffer evaluate`` writes the payloads; this only reads them.

The lines, with the payloads' own key names:

- ``NEWS_SHADOW_GW gw=<n> n=<rows> brier_news=<x> brier_flags=<x>``, one per
  entry of the ``news_shadow`` payload's ``by_gw``, then ``NEWS_SHADOW n=…
  brier_news=… brier_flags=…`` from its ``overall``
  (``evaluation.score_news_shadow``);
- ``FLAG_LATENCY rows=… late_flags=… missed=… histogram=<bucket>=<n>,…``
  from the ``flag_latency`` payload (``availability_eval.score_flag_latency``):
  ``late_flags`` is the length of that list, ``missed`` the per-bucket
  ``missed`` counts summed, and each histogram bucket's ``n`` its
  ``started`` plus ``missed`` (holiday F-46's ruling: the per-bucket count of
  changes, with the missed total beside it).

A missing artifact, a missing key or an empty payload (``rows: 0``, or a
flag-latency report behind its gate, ``available: False``) is not a
verdict and prints ``<PREFIX> none: run gaffer evaluate --<flag>``. Values
are printed as stored: nothing is rounded or recomputed.

Read-only: it writes nothing. ``reports/`` is machine-local, so the Mac runs
it.

    uv run python scripts/evaluate_lines.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from gaffer.evaluation import EVALUATION_PATH


def _news_shadow(payload: dict | None) -> None:
    if not payload or not payload.get("rows") or not payload.get("overall"):
        print("NEWS_SHADOW none: run gaffer evaluate --news-shadow")
        return
    for row in payload.get("by_gw", []):
        body = (f"gw={row['gw']} n={row['rows']} "
                f"brier_news={row['brier_news']} "
                f"brier_flags={row['brier_flags']}")
        print(f"NEWS_SHADOW_GW {body}")
    overall = payload["overall"]
    body = (f"n={overall['rows']} brier_news={overall['brier_news']} "
            f"brier_flags={overall['brier_flags']}")
    print(f"NEWS_SHADOW {body}")


def _flag_latency(payload: dict | None) -> None:
    if (not payload or not payload.get("available", True)
            or not payload.get("rows")):
        print("FLAG_LATENCY none: run gaffer evaluate --flag-latency")
        return
    histogram = payload.get("histogram", [])
    missed = sum(b["missed"] for b in histogram)
    buckets = ",".join(f"{b['bucket']}={b['started'] + b['missed']}"
                       for b in histogram)
    body = (f"rows={payload['rows']} "
            f"late_flags={len(payload.get('late_flags', []))} "
            f"missed={missed} histogram={buckets}")
    print(f"FLAG_LATENCY {body}")


def main(path: Path = EVALUATION_PATH) -> None:
    """Read the stored evaluation and print its ``NEWS_SHADOW`` and
    ``FLAG_LATENCY`` lines."""
    stored: dict = {}
    if path.exists():
        try:
            stored = json.loads(path.read_text())
        except ValueError as exc:
            raise SystemExit(f"{path} is not readable JSON; re-run "
                             f"`gaffer evaluate` to rebuild it ({exc})") from exc
    _news_shadow(stored.get("news_shadow"))
    _flag_latency(stored.get("flag_latency"))


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else EVALUATION_PATH)
