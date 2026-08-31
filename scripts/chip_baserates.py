"""Print this week's chip valuations against the community's base rates.

Context for the outcome record, not a gate (spec D5). The bands below are the
numbers the FPL community has converged on over several seasons; ours are one
model's opinion of one squad in one week, and the two disagreeing is
information rather than a bug. What would be a bug is our number being outside
the *sanity* bands in ``tests/test_chip_sanity.py``, and that is a test.

    uv run python scripts/chip_baserates.py [--gw N]
"""

from __future__ import annotations

import argparse
import json

from gaffer.artifacts import REPORTS, latest_gw

BASE_RATES = {
    "bboost": [("single gameweek", 8.0, 12.0), ("double gameweek", 15.0,
                                                25.0)],
    "3xc": [("single gameweek", 6.0, 12.0), ("double gameweek", 12.0, 20.0)],
    "wildcard": [("optimal vs random, per season", 20.0, 30.0)],
    "freehit": [("double or blank gameweek", 12.0, 25.0)],
}
"""Community base rates, in expected points. Sources are forum consensus and
published season reviews rather than a dataset we hold, which is exactly why
they are printed and not asserted."""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gw", type=int, default=None)
    args = parser.parse_args()

    gw = args.gw if args.gw is not None else latest_gw()
    if gw is None:
        print("no advice on disk — run `gaffer advise` first")
        return 1
    path = REPORTS / f"gw{gw}-advice.json"
    if not path.exists():
        print(f"no {path}")
        return 1
    rows = [r for r in (json.loads(path.read_text()).get("chip_table") or [])
            if isinstance(r, dict)]
    if not rows:
        print(f"GW{gw} priced no chips (none available)")
        return 0

    print(f"Chip valuations, GW{gw} — ours against the community's bands")
    print(f"{'chip':>9}  {'gw':>3}  {'gain':>7}  {'theta':>7}  {'now':>4}  "
          f"community")
    for row in sorted(rows, key=lambda r: -float(r.get("gain", 0.0))):
        chip = str(row.get("chip"))
        theta = row.get("threshold")
        bands = "; ".join(f"{label} {low:.0f}-{high:.0f}"
                          for label, low, high in BASE_RATES.get(chip, []))
        print(f"{chip:>9}  {row.get('gw', ''):>3}  "
              f"{float(row.get('gain', 0.0)):>7.2f}  "
              f"{'—' if theta is None else f'{float(theta):>7.2f}'}  "
              f"{'yes' if row.get('play_now') else 'no':>4}  {bands}")
    print("\nThe community numbers are context, not a target. A gap is worth "
          "a sentence in the cycle's outcome section; it is not a failure.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
