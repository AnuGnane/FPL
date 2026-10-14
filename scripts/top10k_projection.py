"""The ``P(top-10k)`` line's projection rule, backtested on the banked weeks.

ROADMAP candidate 3's remainder and the Data-gated row W4 §5.3 ``P(top-10k)``
(holiday F-35). F-6 chose its rule before any week could test it: the 10,000th
season total at the end of gameweek ``n`` is the last banked threshold before
``n`` plus the mean weekly rise over the banked weeks before ``n``
(``league_sim.project_threshold``, read here, not edited). This replays that
choice over ``data.top_threshold.threshold_series(season)``: every banked
gameweek with at least two banked weeks before it is projected from those
weeks alone and scored against its own banked reading.

The rules:

- ``f6``: F-6's, by calling ``project_threshold`` on the weeks before ``n``;
- ``last_rise``: the last banked threshold plus the last week's rise (the
  rise between the last two banked weeks, per gameweek of the gap);
- ``median_rise``: the last banked threshold plus the median of the
  per-gameweek rises between consecutive banked weeks.

Each rise is per gameweek and multiplied by the weeks from the last banked
one to ``n``, so a missed scrape week is spanned, as F-6's slope spans it.
The line, ``TOP10K_PROJ {…}``, carries n (weeks projected), each rule's MAE
and signed bias (projected minus banked; positive is a line set too high),
and the week-by-week table.

The verdict rule, written here before the script has run on real data:
F-6's rule stays unless another rule's MAE is at least ``MAE_GAIN`` (10 %)
below F-6's over at least ``MIN_WEEKS`` (5) projected weeks, in which case
the verdict names that rule and the PR records a ruling for Anu (default:
F-6's rule stays). Fewer than ``MIN_WEEKS`` reads ``insufficient``. Fewer
than three banked gameweeks projects nothing and prints the waiting sentence.

Read-only: it writes nothing and changes no default. A missing log is an
empty series, so it prints the waiting sentence, never a traceback.

    uv run python scripts/top10k_projection.py [--season 2026-27]
"""

from __future__ import annotations

import argparse
import json
from statistics import median

from gaffer.data.top_threshold import threshold_series
from gaffer.league_sim import project_threshold

RULES = ["f6", "last_rise", "median_rise"]

MAE_GAIN = 0.10
MIN_WEEKS = 5
"""The pre-registered verdict rule (holiday F-35's default)."""

MIN_BANKED = 3
"""Two weeks to draw a rise from and one to score it on."""


def _rises(series: dict[int, int], weeks: list[int]) -> list[float]:
    return [(series[b] - series[a]) / (b - a) for a, b in zip(weeks, weeks[1:])]


def project(series: dict[int, int], gw: int) -> dict[str, float] | None:
    """Each rule's projection for the end of ``gw`` from the banked weeks
    strictly before it, or ``None`` with fewer than two such weeks."""
    weeks = sorted(int(g) for g in series if int(g) < int(gw))
    if len(weeks) < 2:
        return None
    f6 = project_threshold(series, gw)
    if f6 is None:
        return None
    last = weeks[-1]
    rises = _rises(series, weeks)
    ahead = int(gw) - last
    return {"f6": float(f6["threshold"]),
            "last_rise": float(series[last]) + rises[-1] * ahead,
            "median_rise": float(series[last]) + median(rises) * ahead}


def _verdict(n: int, mae: dict[str, float]) -> str:
    if n < MIN_WEEKS:
        return "insufficient"
    best = min((r for r in RULES if r != "f6"), key=lambda r: mae[r])
    if mae[best] <= (1 - MAE_GAIN) * mae["f6"] and mae[best] < mae["f6"]:
        return f"ruling: {best} beats f6"
    return "f6 stays"


def _r(v: float) -> float:
    return round(v, 2)


def reading(series: dict[int, int]) -> dict:
    """The ``TOP10K_PROJ`` payload over one season's banked series."""
    series = {int(g): int(t) for g, t in series.items()}
    if len(series) < MIN_BANKED:
        return {"n": 0, "banked": len(series), "rules": None, "weeks": [],
                "verdict": "waiting",
                "reason": (f"{len(series)} banked gameweek(s); a rule needs "
                           f"two to draw a rise from and a third to score "
                           f"it on")}
    weeks = []
    for gw in sorted(series):
        proj = project(series, gw)
        if proj is None:
            continue
        weeks.append({"gw": gw, "banked": series[gw],
                      **{r: _r(proj[r]) for r in RULES},
                      "_raw": proj})
    errs = {r: [w["_raw"][r] - w["banked"] for w in weeks] for r in RULES}
    n = len(weeks)
    mae = {r: sum(abs(e) for e in errs[r]) / n for r in RULES}
    bias = {r: sum(errs[r]) / n for r in RULES}
    return {"n": n, "banked": len(series),
            "rules": {r: {"mae": _r(mae[r]), "bias": _r(bias[r])}
                      for r in RULES},
            "weeks": [{k: v for k, v in w.items() if k != "_raw"}
                      for w in weeks],
            "verdict": _verdict(n, mae), "reason": None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--season", default=None,
                        help="default: the season in force")
    args = parser.parse_args(argv)
    season = args.season
    if season is None:
        from gaffer.config import config_in_force

        season = str(config_in_force().current_season)
    payload = {"season": season, **reading(threshold_series(season))}
    print(f"TOP10K_PROJ {json.dumps(payload, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
