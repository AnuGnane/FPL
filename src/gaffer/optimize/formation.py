"""The starting-eleven rule, in one place (v18d §2).

``XI_BOUNDS`` was spelled twice — here in the MILP and again in
``backtest`` — and ``backtest._formation_legal`` was reached for privately by
``live_gw`` and ``review``. One table, one predicate, three callers.
"""

from __future__ import annotations

from collections import Counter

XI_BOUNDS = {"GKP": (1, 1), "DEF": (3, 5), "MID": (2, 5), "FWD": (1, 3)}
"""Per-position ``(min, max)`` in a legal starting eleven."""


def formation_legal(positions: list[str]) -> bool:
    """Eleven names whose positions fit :data:`XI_BOUNDS`."""
    c = Counter(positions)
    return (len(positions) == 11
            and all(lo <= c.get(p, 0) <= hi
                    for p, (lo, hi) in XI_BOUNDS.items()))
