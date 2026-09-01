"""Derive ``data/chip_scenarios.toml`` from the published fixture list.

The seam ``optimize/chip_policy.py`` opened in v4c and nothing has written to
since. It lives under ``data/`` rather than ``optimize/`` for two reasons: this
is a data producer rather than an optimizer, and ``optimize/**`` is protected
this cycle.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from gaffer.data.fixtures import season_outlook
from gaffer.optimize.chip_policy import CHIP_SCENARIOS_PATH


def write_chip_scenarios(fixtures: pd.DataFrame | None,
                         code_of: dict[int, int] | None = None,
                         path: Path | str | None = None) -> int:
    """Derive ``data/chip_scenarios.toml`` from the published fixture list.

    Returns the number of ``[dgw]`` entries written; ``0`` covers both "no
    doubles, no file" and "no doubles, file emptied".

    **Only scheduled doubles.** A gameweek in which some team plays twice, in
    the fixture list as published, at probability ``1.0`` — spec §F2b's "no
    speculative entries". This does not guess at rearrangements, which is what
    the Crellin-style projections v4c was waiting for would do, and which is
    still not this cycle's business.

    **Empty detection never creates the file** (plan A11): today's real list
    has ten fixtures in every one of thirty-eight gameweeks, so on every
    machine as things stand this writes nothing and ``load_chip_scenarios``
    keeps returning ``{}`` exactly as it does today. An *existing* file is
    rewritten with an empty ``[dgw]`` instead — identical in effect to absence
    (``chip_policy.py:110-112``) and the only way a reverted rearrangement
    stops standing.

    Never raises. This runs inside ``run_data_refresh``'s body, and a chip
    planning convenience that can fail the weekly data refresh is a bad trade
    however useful it is.
    """
    target = Path(path) if path is not None else CHIP_SCENARIOS_PATH
    try:
        weeks = season_outlook(fixtures, code_of) if fixtures is not None \
            else []
        doubles = [w["gw"] for w in weeks if w["doubles"]]
        if not doubles and not target.exists():
            # Never a file for nothing: absence is the honest state, and it is
            # also the state every shipped test and every clone expects.
            return 0
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines = [
            "# Derived, not hand-written. Delete it freely.",
            "#",
            "# Written by gaffer.data.chip_scenarios.write_chip_scenarios,",
            f"# inside the refresh-data job, at {stamp}. One entry per",
            "# *scheduled* double gameweek — a week in which some team plays",
            "# twice in the published fixture list — at probability 1.0,",
            "# because a fixture that is already scheduled is a fact rather",
            "# than a scenario. Unannounced rearrangements are not projected",
            "# here and never have been.",
            "",
            "[dgw]",
        ]
        lines += [f"{gw} = 1.0" for gw in sorted(doubles)]
        _atomic_write(target, "\n".join(lines) + "\n")
        return len(doubles)
    except Exception as exc:  # noqa: BLE001 — never fails the data refresh
        print(f"chip_scenarios: not written ({exc})")
        return 0


def _atomic_write(target: Path, text: str) -> None:
    """Write whole, replace in one step, and never share a temp name.

    ``field.py:100-107``'s reasoning: two writers sharing one ``.tmp`` each
    unlink the other's file and the loser's ``os.replace`` raises
    ``FileNotFoundError``. A nightly job and a manual refresh are exactly two
    writers.
    """
    tmp = target.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(text)
    os.replace(tmp, target)
